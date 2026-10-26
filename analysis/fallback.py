"""Fallback question F1 (D-033): does an undercutting-salient framing lower Delta?

Compares two prefix-only runs launched at the same time (`make fallback`):
config/fallback_p1.yaml (P1-like framing) and config/fallback_undercut.yaml
(undercutting-salient framing), same seed and settings. It does not need the main run.
Unit of analysis: one prefix, its mean Delta over the last W prefix periods. Independent
groups, bootstrap interval for the difference in means.
Prediction (S1, S4): Delta(P1-like) - Delta(P2-like) > 0.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from analysis.pipeline import interval
from run.common import write_json


def prefix_deltas(run_dir):
    run_dir=Path(run_dir); c=yaml.safe_load((run_dir/'resolved_config.yaml').read_text())
    tr=pd.read_csv(run_dir/'trajectories.csv'); w=c['experiment']['window']
    pre=tr[tr.phase=='prefix']
    last=pre[pre.period>=c['experiment']['max_prefix']-w]
    counts=last.groupby(['prefix_id','firm']).size()
    if (counts!=w).any() or last.prefix_id.nunique()!=c['experiment']['prefixes']:
        raise ValueError(f'Incomplete prefix windows in {run_dir}')
    return last.groupby('prefix_id').delta.mean(), c


def compare(p1_dir, p2_dir, out=None):
    d1,c1=prefix_deltas(p1_dir); d2,c2=prefix_deltas(p2_dir)
    strip=lambda e:{k:v for k,v in e.items() if k not in ('prefix_only','workers')}
    for key in ('market','observations'):
        if c1[key]!=c2[key]: raise ValueError(f'F1 runs differ in {key}; only the prompt may differ')
    if strip(c1['experiment'])!=strip(c2['experiment']): raise ValueError('F1 runs differ in experiment settings')
    if {k:v for k,v in c1['llm'].items() if k!='prompt_dir'}!={k:v for k,v in c2['llm'].items() if k!='prompt_dir'}:
        raise ValueError('F1 runs differ in model settings; only the prompt may differ')
    if c1['llm'].get('prompt_dir')==c2['llm'].get('prompt_dir'): raise ValueError('F1 runs use the same prompts')
    a=c1['analysis']; rng=np.random.default_rng(a['bootstrap_seed']); B=a['bootstrap_resamples']
    x=d1.to_numpy(); y=d2.to_numpy()
    boot=x[rng.integers(0,len(x),size=(B,len(x)))].mean(axis=1)-y[rng.integers(0,len(y),size=(B,len(y)))].mean(axis=1)
    # Expansion uses the smaller group size: conservative for two independent samples [A].
    lo,hi=interval(boot,a['confidence'],min(len(x),len(y)),a.get('interval_method','percentile'))
    diff=float(x.mean()-y.mean())
    status='SUPPORTED' if lo>0 else ('OPPOSITE_DIRECTION' if hi<0 else 'NOT_SUPPORTED')
    result={'question':'F1','status':status,'difference':diff,'low':float(lo),'high':float(hi),
            'p1_like_delta':float(x.mean()),'undercut_delta':float(y.mean()),
            'n_p1_like':len(x),'n_undercut':len(y),'confidence':a['confidence'],
            'p1_run':str(p1_dir),'undercut_run':str(p2_dir)}
    if out: write_json(Path(out),result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--p1-run',required=True); p.add_argument('--undercut-run',required=True)
    p.add_argument('--output'); a=p.parse_args()
    print(json.dumps(compare(a.p1_run,a.undercut_run,a.output),indent=2))
