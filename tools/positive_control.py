"""Stage-one positive-control check (D-046, D-047, amended by D-050, D-051, D-053). Reads the baseline arm only.

The sprint's guidance is to start with a few seeds and expand only once the positive control
works (COMPETITION.md). The main run therefore plays the `stage_one.prefixes` of its design section
(`analysis.screens` or `analysis.swaps`) first. This tool reads their prefix phase and their
`baseline` continuation, and nothing from any treatment or probe arm, so no treatment effect is seen
before the remaining prefixes are run. In the replacement design (D-053) there is no screen to bind:
the check is the supra-competitive gate alone, and PROCEED carries no primary.

Pre-registered rules (D-050, D-051), with the thresholds in the config so that they are in its hash.
The final gates are projected to the full run from the baseline continuation, with N =
experiment.prefixes and z the multiplier of the run's own interval method at that N:
1. STOP_RUN_FALLBACK if the mean final-window Delta of the baseline continuation is below
   `min_baseline_delta` (0.10 [A]), or if the projected lower bound of the final supra-competitive
   gate (D-047 rule 2), mean - z * SD / sqrt(N), is not above `analysis.feasibility_min_delta`:
   there is no collusion to screen (fallback F1, D-033).
2. Otherwise each disclosed screen's final gate (D-047 rule 3: the upper bound of the control's
   mean pair pass margin below 0) is projected: mean + z * SD / sqrt(N). The screen is expected to
   bind if the projection is below 0.
3. PROCEED with the configured primary if it is expected to bind; otherwise PROCEED with the
   first other disclosed screen that is (recorded as a decision entry before stage two); otherwise
   STOP_SCREENS_NOT_BINDING: neither screen would find the collusion, so F1 runs instead.
The record carries the run's design hash (tools.positive_control.design_hash), which the analysis
checks before it accepts the record (D-051).

`--require-proceed` re-checks a saved record against the run and fails unless it says PROCEED;
`make stage2` runs it first.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from scipy.stats import norm, t as student_t
from run.common import write_json

DEFAULTS = {'prefixes': 6, 'min_baseline_delta': 0.10}


def gate_multiplier(c, n):
    """z such that mean ± z·SD/sqrt(n), with the ddof=1 SD, approximates the final gate's bootstrap
    bound at n prefixes. The bootstrap SD of a mean is the ddof=0 SD over sqrt(n), so the
    expanded-percentile bound (S6: quantile sqrt(n/(n-1)) t_{n-1}) is t_{n-1} in ddof=1 units, and
    the plain percentile bound is the normal quantile times sqrt((n-1)/n) (D-051)."""
    a=c['analysis']; q=(1-a['confidence'])/2
    if a.get('interval_method','percentile')=='expanded_percentile':
        return float(student_t.ppf(1-q,n-1))
    return float(norm.ppf(1-q)*np.sqrt((n-1)/n))


def design_hash(c):
    """Hash of a run's design: its resolved config without the settings that legitimately differ
    between stages, resumed runs and the replication (prefix subset, workers, master seed, purpose),
    and without the review flags and the budget section, which change neither what is played nor
    how it is analysed (so a spend cap raised for the replication keeps the main run's record valid)."""
    d=json.loads(json.dumps(c,sort_keys=True))
    for k in ('prefix_ids','workers','seed'): d['experiment'].pop(k,None)
    for k in ('purpose','review','budget'): d.pop(k,None)
    return hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()


def baseline_windows(base, c):
    """Per prefix, the final-window Delta of the baseline continuation and the pre-fork window's mean Delta,
    without the screen statistics (the replacement design has no cost columns). Returns (stats, incomplete)."""
    e=c['experiment']; W,B=e['window'],e['branch_periods']; win=list(range(B-W,B)); rows=[]; incomplete=[]
    cost=float(np.mean(c['market']['costs'])); b=base[base.phase=='branch']
    for pid,g in b.groupby('prefix_id'):
        d=g.groupby('relative_period').delta.mean().reindex(range(B))
        if d.isna().any() or g[g.relative_period.isin(win)].price.isna().any(): incomplete.append((int(pid),'baseline')); continue
        rows.append({'prefix_id':int(pid),'arm':'baseline','delta':float(d[win].mean()),'movement_ratio':np.nan,
                     'markup':float((g[g.relative_period.isin(win)].price-cost).mean())})
    return pd.DataFrame(rows,columns=['prefix_id','arm','delta','movement_ratio','markup']),incomplete


def check(run_dir):
    run=Path(run_dir); c=yaml.safe_load((run/'resolved_config.yaml').read_text())
    s=c['analysis'].get('screens'); d=s or c['analysis'].get('swaps'); e=c['experiment']
    if not d: raise ValueError('No staged design (analysis.screens or analysis.swaps) in this run')
    rules={**DEFAULTS,**(d.get('stage_one') or {})}
    tr=pd.read_csv(run/'trajectories.csv')
    base=tr[(tr.phase=='prefix')|((tr.phase=='branch')&(tr.arm=='baseline'))]
    if s:
        from analysis.screens import branch_statistics, screen_kind
        stats,incomplete=branch_statistics(base,c)
    else:
        stats,incomplete=baseline_windows(base,c)
    if stats.empty: raise ValueError('No complete baseline continuation in this run')
    w=e['window']; pre=base[base.phase=='prefix']; pre=pre[pre.period>=pre.period.max()+1-w]
    n_final=int(e['prefixes']); z=gate_multiplier(c,n_final)
    gates={}
    for arm,spec in (s['disclosed'].items() if s else ()):
        margins=stats[f'pass_margin_{screen_kind(spec)}'].dropna(); k=len(margins)
        sd=float(margins.std(ddof=1)) if k>1 else None
        projected=float(margins.mean()+z*sd/np.sqrt(n_final)) if k>1 else None
        gates[arm]={'prefixes':int(k),'mean_pair_pass_margin':float(margins.mean()) if k else None,
                    'sd':sd,'share_of_prefixes_flagged':float((margins<0).mean()) if k else None,
                    'projected_upper_bound':projected,'expected_to_bind':projected is not None and projected<0}
    mean_delta=float(stats.delta.mean()); k=len(stats)
    delta_sd=float(stats.delta.std(ddof=1)) if k>1 else None
    delta_low=mean_delta-z*delta_sd/np.sqrt(n_final) if k>1 else None
    feasible=delta_low is not None and delta_low>c['analysis'].get('feasibility_min_delta',0.)
    primary=d.get('primary')
    if mean_delta<rules['min_baseline_delta'] or not feasible: status='STOP_RUN_FALLBACK'
    elif not s: status='PROCEED'                       # D-053: nothing to bind; the Delta gate is the whole check
    elif gates[primary]['expected_to_bind']: status='PROCEED'
    else:
        other=next((arm for arm in s['disclosed'] if arm!=primary and gates[arm]['expected_to_bind']),None)
        status,primary=('PROCEED',other) if other else ('STOP_SCREENS_NOT_BINDING',primary)
    return {'run':str(run),'status':status,'prefixes':sorted(int(x) for x in stats.prefix_id),
            'incomplete_cells':[list(x) for x in incomplete],
            'baseline_final_window_delta':{'mean':mean_delta,'sd':delta_sd,'projected_lower_bound':delta_low,
                                           'by_prefix':{int(r.prefix_id):round(float(r.delta),3) for r in stats.itertuples()}},
            'pre_fork_delta_by_prefix':{int(k):round(float(v),3) for k,v in pre.groupby('prefix_id').delta.mean().items()},
            'gates':gates,'gate_projection':{'full_run_prefixes':n_final,'multiplier':z},
            'baseline_movement_ratio':float(stats.movement_ratio.mean()) if stats.movement_ratio.notna().any() else None,
            'baseline_markup':float(stats.markup.mean()),
            'min_baseline_delta':rules['min_baseline_delta'],
            'primary_for_stage_two':primary if status=='PROCEED' else None,
            'primary_changed':bool(s) and status=='PROCEED' and primary!=s['primary'],
            'design_hash':design_hash(c),
            'note':'Baseline arm and prefix phase only; no notice or probe arm was read.'}


def require_proceed(run_dir):
    """The saved record must match a fresh check of the same run and say PROCEED (D-050)."""
    path=Path(run_dir)/'positive_control.json'
    if not path.exists(): raise SystemExit(f'No stage-one record at {path}: run `make positive-control` first')
    saved=json.loads(path.read_text()); fresh=json.loads(json.dumps(check(run_dir),default=float))
    saved.pop('run',None); fresh.pop('run',None)
    if saved!=fresh: raise SystemExit(f'{path} does not match a fresh check of the run; it was edited or the run changed')
    if saved['status']!='PROCEED': raise SystemExit(f"Stage one says {saved['status']}: do not run stage two (RUNBOOK)")
    return saved


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--run-dir',required=True)
    p.add_argument('--require-proceed',action='store_true',help='check the saved record instead of writing it')
    a=p.parse_args()
    if a.require_proceed:
        r=require_proceed(a.run_dir); print(f"Stage one: PROCEED, primary {r['primary_for_stage_two']}"); sys.exit(0)
    result=check(a.run_dir); write_json(Path(a.run_dir)/'positive_control.json',result)
    print(json.dumps(result,indent=2))
