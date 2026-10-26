"""Prefix-cluster paired estimands. Diagnostic evidence is separate from verdicts.

With `ranking_metric: removal` (D-027) the primary quantity for restriction r in prefix i is
D_ir = Delta_baseline,i - Delta_r,i: the paired drop in the Calvano index, whose
denominator (pi^M - pi^N) is fixed by the market, not by a noisy continuation (D-027). `share` keeps the original per-prefix ratio for backward comparison.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from scipy.stats import norm, t as student_t
from run.common import write_json

RESTRICTIONS=['R1','R2','R3','R4']


def summarize(trajectories, competence, c):
    from run.fork import arms, competence_arms
    a=c['analysis']; metric=a.get('ranking_metric','share')
    if trajectories.empty or competence is None or competence.empty:
        raise ValueError('No included prefixes with competence data')
    branches=trajectories[trajectories.phase=='branch']
    last=branches[branches.relative_period >= c['experiment']['branch_periods']-c['experiment']['window']]
    # Each cell must contain W outcomes for both firms, with no duplicates.
    if last.duplicated(['prefix_id','arm','period','firm']).any(): raise ValueError('Duplicate branch outcomes')
    counts_f=last.groupby(['prefix_id','arm','firm']).size()
    if set(last.firm.unique())!={0,1} or (counts_f!=c['experiment']['window']).any():
        raise ValueError('Incomplete firm windows')
    counts=last.groupby(['prefix_id','arm']).size()
    if (counts!=2*c['experiment']['window']).any(): raise ValueError('Incomplete final windows')
    delta=last.groupby(['prefix_id','arm']).delta.mean().unstack()
    expected=arms(c)
    if any(x not in delta for x in expected) or delta[expected].isna().any().any():
        raise ValueError('Unpaired or missing branches')
    expected_comp=competence_arms(c)
    counts_c=competence.groupby(['prefix_id','arm','firm']).size()
    if (counts_c!=c['competence']['periods']).any() or competence.duplicated(['prefix_id','arm','firm','period']).any():
        raise ValueError('Incomplete or duplicate competence trajectory')
    firm_counts=competence.groupby(['prefix_id','arm']).firm.nunique()
    if set(competence.firm.unique())!={0,1} or (firm_counts!=2).any():
        raise ValueError('Incomplete competence firm pairs')
    aggregate=a.get('cost_aggregation','sum')
    regret=competence.groupby(['prefix_id','arm','firm']).regret.agg(aggregate).groupby(['prefix_id','arm']).mean().unstack()
    if set(regret.index)!=set(delta.index) or any(x not in regret for x in expected_comp) or regret[expected_comp].isna().any().any():
        raise ValueError('Unpaired competence tasks')
    valid=delta.baseline>a['min_continuation_delta']
    dropped=delta.index[~valid].tolist()
    if metric=='share':
        if dropped and a['invalid_share_policy']=='error': raise ValueError('Invalid share denominator')
        delta=delta.loc[valid]; regret=regret.loc[delta.index]
    if len(delta)<2: raise ValueError('At least two valid independent prefixes required for bootstrap')
    shares=delta.rsub(delta.baseline,axis=0).div(delta.baseline.where(valid.loc[delta.index]),axis=0)
    costs=regret.sub(regret.baseline,axis=0)
    if not np.isfinite(delta.to_numpy()).all() or not np.isfinite(costs.to_numpy()).all():
        raise ValueError('Nonfinite paired metrics')
    return delta,shares,costs,dropped


def expanded_alpha(confidence, n):
    """alpha'/2 of the expanded percentile interval [L: SOURCES.md S6, §1.1 and §5.3]:
    Phi(-sqrt(n/(n-1)) * t_{alpha/2, n-1}), which corrects the percentile interval's
    narrowness in small samples (S6 Table 5: 0.0086 at n = 10 for a nominal 0.025)."""
    if n is None or n<2: raise ValueError('expanded_percentile needs n >= 2')
    q=(1-confidence)/2
    return float(norm.cdf(-np.sqrt(n/(n-1))*student_t.ppf(1-q,n-1)))


def interval(samples, confidence=.95, n=None, method='percentile'):
    """Two-sided bootstrap percentile interval, or Hesterberg's expanded percentile interval."""
    q=(1-confidence)/2
    if method=='expanded_percentile': q=expanded_alpha(confidence,n)
    elif method!='percentile': raise ValueError(f'Unknown interval method {method}')
    return np.quantile(samples,[q,1-q],axis=0)


def bootstrap_mean(values, a):
    """Mean of independent per-prefix values with the configured bootstrap interval."""
    x=np.asarray(values,dtype=float); m=len(x)
    if m<2: return {'n':m,'mean':float(x.mean()) if m else None,'low':None,'high':None}
    idx=np.random.default_rng(a['bootstrap_seed']).integers(0,m,size=(a['bootstrap_resamples'],m))
    lo,hi=interval(x[idx].mean(axis=1),a['confidence'],m,a.get('interval_method','percentile'))
    return {'n':m,'mean':float(x.mean()),'low':float(lo),'high':float(hi)}


def ranking_arms(c):
    """Candidates for the Track 1.5 ranking (D-031, extended by D-039)."""
    return list(c['analysis'].get('ranking_arms') or RESTRICTIONS)


def market_outcomes(trajectories, c):
    """Per prefix and arm, final-window means of the market-level outcomes (D-038)."""
    last=final_window(trajectories,c)
    fields=[f for f in ('consumer_harm','welfare_loss','total_quantity') if f in last]
    return {f:last.groupby(['prefix_id','arm'])[f].mean().unstack() for f in fields}


def infer(delta, shares, costs, c, outcomes=None):
    a=c['analysis']; n=len(delta); metric=a.get('ranking_metric','share'); ranked=ranking_arms(c)
    rng=np.random.default_rng(a['bootstrap_seed'])
    indices=rng.integers(0,n,size=(a['bootstrap_resamples'],n))
    def boots(frame): return frame.to_numpy()[indices].mean(axis=1)
    removal=delta.rsub(delta.baseline,axis=0)
    d_boot,r_boot,c_boot=boots(delta),boots(removal),boots(costs)
    if metric=='share':
        s_boot=boots(shares); share_point=shares.mean()
    else:
        # Pooled share of baseline excess removed: a ratio of paired means, never of noisy per-prefix ratios.
        base_boot=d_boot[:,delta.columns.get_loc('baseline')][:,None]
        with np.errstate(divide='ignore',invalid='ignore'): s_boot=r_boot/base_boot
        share_point=removal.mean()/delta.baseline.mean()
    m_boot=s_boot if metric=='share' else r_boot
    m_frame=shares if metric=='share' else removal
    method=a.get('interval_method','percentile')
    ci=lambda x,conf: interval(x,conf,n,method)
    d_ci,r_ci,s_ci,m_ci=(ci(x,a['confidence']) for x in (d_boot,r_boot,s_boot,m_boot))
    c_ci=ci(c_boot,a['confidence'])
    e_ci=ci(c_boot,a.get('eligibility_confidence',a['confidence']))
    # Positivity screen across the ranked arms is family-adjusted like the contrasts.
    pos_conf=1-(1-a['confidence'])/len(ranked) if a['contrast_adjustment']=='bonferroni' else a['confidence']
    p_ci=ci(m_boot,pos_conf)
    rows=[]
    for arm in delta.columns:
        j=delta.columns.get_loc(arm); k=costs.columns.get_loc(arm) if arm in costs else None
        cost=float(costs[arm].mean()) if k is not None else None
        upper=float(e_ci[1,k]) if k is not None else None
        lower=float(e_ci[0,k]) if k is not None else None
        if k is None or arm not in ranked: status=None
        elif upper<=a['tolerance']: status='certified_eligible'
        elif lower>a['tolerance']: status='demonstrated_excessive'
        else: status='unresolved'
        # Eligibility is the cost criterion only; demonstrated removal is a separate test (below).
        eligible=arm in ranked and ((cost if a['eligibility']=='point' else upper)<=a['tolerance'])
        removes=bool(p_ci[0,j]>0) if arm in ranked else None
        rows.append({'arm':arm,'n_prefixes':n,'delta':float(delta[arm].mean()),
            'delta_low':d_ci[0,j],'delta_high':d_ci[1,j],
            'removal':float(removal[arm].mean()),'removal_low':r_ci[0,j],'removal_high':r_ci[1,j],
            'removal_sd':float(removal[arm].std(ddof=1)) if n>1 else None,
            'share_removed':float(share_point[arm]),'share_low':s_ci[0,j],'share_high':s_ci[1,j],
            'cost':cost,'cost_low':None if k is None else c_ci[0,k],'cost_high':None if k is None else c_ci[1,k],
            'cost_eligibility_upper':upper,'cost_status':status,'eligible':eligible,
            'demonstrated_removal':removes,'removal_screen_low':float(p_ci[0,j])})
    summary=pd.DataFrame(rows)
    if outcomes:
        # Legitimate-performance side of "least cost" in the organisers' sense: consumers and volume (D-038).
        for field,frame in outcomes.items():
            frame=frame.loc[delta.index,delta.columns]
            change=frame.rsub(frame.baseline,axis=0) if field!='total_quantity' else frame.sub(frame.baseline,axis=0)
            label={'consumer_harm':'consumer_harm_removed','welfare_loss':'welfare_loss_removed',
                   'total_quantity':'quantity_change'}[field]
            point=change.mean(); bounds=ci(boots(change),a['confidence'])
            summary[field]=frame.mean().values
            summary[label]=point.values; summary[label+'_low']=bounds[0]; summary[label+'_high']=bounds[1]
    eligible=summary.loc[summary.eligible,'arm'].tolist()
    comparisons=[]
    family=len(ranked)*(len(ranked)-1)//2
    confidence=1-(1-a['confidence'])/family if a['contrast_adjustment']=='bonferroni' else a['confidence']
    for x in ranked:
        for y in ranked:
            if x==y: continue
            xb=m_frame.columns.get_loc(x); yb=m_frame.columns.get_loc(y)
            lo,hi=ci(m_boot[:,xb]-m_boot[:,yb],confidence)
            comparisons.append({'arm':x,'other':y,'metric':metric,'difference':float((m_frame[x]-m_frame[y]).mean()),
                                'low':lo,'high':hi,'confidence':confidence})
    comparisons=pd.DataFrame(comparisons)
    winner=None; top=[]
    removing=summary.loc[summary.demonstrated_removal.fillna(False).astype(bool),'arm'].tolist()
    if not eligible: verdict='NO_ELIGIBLE_ARM'
    else:
        best=max(eligible,key=lambda arm:m_frame[arm].mean())
        pairs=comparisons[(comparisons.arm==best)&comparisons.other.isin(eligible)]
        decisive=bool((pairs.low>0).all())
        if len(eligible)==1: decisive=a['singleton_policy']=='winner'
        if a['require_positive_removal'] and best not in removing:
            # The best cost-eligible arm is not shown to remove anything: no winner, no top set.
            verdict='NO_DEMONSTRATED_REMOVAL'; top=[]
        elif decisive: verdict='WINNER'; winner=best; top=[best]
        else:
            verdict='TOP_SET'; top=[best]+pairs.loc[(pairs.low<=0)&(pairs.high>=0),'other'].tolist()
    benchmarks={}
    for arm in a.get('benchmark_arms') or []:
        # D-040: market-structure benchmarks are compared with the primary restriction, not ranked.
        if arm not in delta or a.get('primary_arm') not in delta: continue
        diff=removal[arm]-removal[a['primary_arm']]
        lo,hi=ci(r_boot[:,delta.columns.get_loc(arm)]-r_boot[:,delta.columns.get_loc(a['primary_arm'])],a['confidence'])
        benchmarks[arm]={'removal':float(removal[arm].mean()),'versus':a['primary_arm'],
                         'difference':float(diff.mean()),'low':float(lo),'high':float(hi)}
    result={'verdict':verdict,'winner':winner,'top_set':sorted(top),'eligible':sorted(eligible),
            'demonstrated_removal':sorted(removing),'ranked_arms':ranked,
            'n_prefixes':n,'contrast_adjustment':a['contrast_adjustment'],'ranking_metric':metric,
            'interval_method':method}
    if benchmarks: result['benchmarks']=benchmarks
    return summary,comparisons,result


READINGS={
    'BASELINE_NOT_SUPRACOMPETITIVE':'No supra-competitive baseline at T: the restriction question is moot; run fallback F1.',
    'SUPPORTED_BEYOND_SHAM':'Hiding rival prices lowered Delta by more than an information-preserving column removal: '
                            'coordination through the explicit rival-price display.',
    'SUPPORTED_NOT_BEYOND_SHAM':'Delta fell, but not distinguishably more than when an information-preserving column '
                                'was removed: a display-change effect cannot be ruled out.',
    'NOT_SUPPORTED':'Not discriminating: parallel pricing, or coordination monitored through own sales or notes. '
                    'Read together with the UNDERCUT_R2 probe.',
    'OPPOSITE_DIRECTION':'Hiding rival prices raised Delta.'}


def final_window(trajectories, c):
    b=trajectories[trajectories.phase=='branch']; e=c['experiment']
    return b[b.relative_period >= e['branch_periods']-e['window']]


def primary_from_trajectories(trajectories, prefixes, c):
    """Pre-registered primary contrast (D-026, amended by D-037), from trajectories alone.

    Needs only the baseline and primary-arm windows (SHAM if present), so a failure in any
    other arm or in the competence tasks cannot block it (review finding 6).
    """
    a=c['analysis']; arm=a['primary_arm']; w=c['experiment']['window']
    method=a.get('interval_method','percentile'); conf=a['confidence']
    last=final_window(trajectories,c)
    wanted=['baseline',arm]+(['SHAM'] if (last.arm=='SHAM').any() else [])
    last=last[last.arm.isin(wanted)]
    counts=last.groupby(['prefix_id','arm','firm']).size().unstack(['arm','firm'])
    complete=counts.index[(counts.reindex(columns=pd.MultiIndex.from_product([wanted,[0,1]])).fillna(0)==w).all(axis=1)]
    excluded=sorted(set(int(x) for x in prefixes.prefix_id[prefixes.included.astype(bool)]) - set(int(x) for x in complete))
    last=last[last.prefix_id.isin(complete)]
    d=last.groupby(['prefix_id','arm']).delta.mean().unstack()[wanted]
    n=len(d)
    if n<2: raise ValueError('At least two complete prefixes are needed for the primary contrast')
    rng=np.random.default_rng(a['bootstrap_seed']); idx=rng.integers(0,n,size=(a['bootstrap_resamples'],n))
    def est(values, sub=None):
        x=np.asarray(values,dtype=float)
        if sub is not None: x=x[sub]
        m=len(x)
        if m<2: return {'n':m,'mean':float(x.mean()) if m else None,'low':None,'high':None}
        bi=idx if sub is None else np.random.default_rng(a['bootstrap_seed']).integers(0,m,size=(a['bootstrap_resamples'],m))
        lo,hi=interval(x[bi].mean(axis=1),conf,m,method)
        return {'n':m,'mean':float(x.mean()),'low':float(lo),'high':float(hi),'sd':float(x.std(ddof=1))}
    removal=(d.baseline-d[arm]).to_numpy(); base=est(d.baseline); rem=est(removal)
    harm=None
    if 'consumer_harm' in last:
        h=last.groupby(['prefix_id','arm']).consumer_harm.mean().unstack()[['baseline',arm]]
        harm=est((h.baseline-h[arm]).to_numpy())
    feasible=bool(base['low']>a.get('feasibility_min_delta',0.))
    if not feasible: status='BASELINE_NOT_SUPRACOMPETITIVE'
    elif rem['low']>0: status='SUPPORTED'
    elif rem['high']<0: status='OPPOSITE_DIRECTION'
    else: status='NOT_SUPPORTED'
    out={'arm':arm,'status':status,'removal':rem['mean'],'removal_low':rem['low'],'removal_high':rem['high'],
         'removal_sd':rem['sd'],'n_prefixes':n,'excluded_incomplete_prefixes':excluded,
         'baseline_delta':base['mean'],'baseline_delta_low':base['low'],'baseline_delta_high':base['high'],
         'treated_delta':float(d[arm].mean()),'feasibility_min_delta':a.get('feasibility_min_delta',0.),
         'confidence':conf,'interval_method':method}
    reading=status
    if harm is not None:
        out['consumer_harm_removed']={k:harm[k] for k in ('mean','low','high')}
    if 'SHAM' in d:
        sham=est((d.baseline-d.SHAM).to_numpy()); beyond=est((d.SHAM-d[arm]).to_numpy())
        out['sham_removal']={k:sham[k] for k in ('mean','low','high')}
        out['removal_beyond_sham']={k:beyond[k] for k in ('mean','low','high')}
        if status=='SUPPORTED': reading='SUPPORTED_BEYOND_SHAM' if beyond['low']>0 else 'SUPPORTED_NOT_BEYOND_SHAM'
    if 'carried' in last:
        dirty=set(last.loc[last.carried.astype(bool) & last.arm.isin(['baseline',arm]),'prefix_id'])
        keep=np.array([pid not in dirty for pid in d.index])
        clean=est(removal,keep)
        out['excluding_carried']={'n':clean['n'],'removal':clean['mean'],'low':clean['low'],'high':clean['high'],
                                  'prefixes_with_carried_decisions':sorted(int(x) for x in dirty)}
    if 'high_stratum' in prefixes:
        high=set(prefixes.prefix_id[prefixes.high_stratum.astype(bool)])
        sub=est(removal,np.array([pid in high for pid in d.index]))
        out['high_stratum']={'n':sub['n'],'removal':sub['mean'],'low':sub['low'],'high':sub['high'],
                             'stratum_threshold':c['experiment'].get('stratum_threshold')}
    out['reading']=reading; out['reading_text']=READINGS[reading]
    out['interpretation']='Paired drop in the Calvano index caused by imposing the restriction at the fork; not evidence about intent.'
    return out


NOREGRET_READINGS={
    'INSUFFICIENT_PREFIXES':'Fewer than two complete prefixes: no interval, no reading.',
    'BASELINE_NOT_SUPRACOMPETITIVE':'No supra-competitive baseline in these prefixes: question 1.2 is moot.',
    'PRICE_KEPT':'The remaining LLM firm kept its price: the whole interval of its price drop lies inside the '
                 'pre-registered margin. The high price survived the replacement for the length of the branch.',
    'PRICE_DROPPED':'The remaining LLM firm priced below its own baseline continuation once its rival was replaced.',
    'PRICE_ROSE':'The remaining LLM firm priced above its own baseline continuation once its rival was replaced.',
    'NOT_DISCRIMINATING':'Neither a drop nor its absence was shown: the interval crosses 0 and leaves the margin.'}


def noregret_reading(n, baseline, drop, margin, feasibility_min):
    """Pre-registered reading of question 1.2 (D-043). An interval inside (-margin, margin) is
    read as 'kept' before significance is considered: a drop smaller than the margin does not
    break the high price in any sense the question cares about."""
    if n<2 or drop['low'] is None: return 'INSUFFICIENT_PREFIXES'
    if not baseline['low']>feasibility_min: return 'BASELINE_NOT_SUPRACOMPETITIVE'
    if drop['low']>-margin and drop['high']<margin: return 'PRICE_KEPT'
    if drop['low']>0: return 'PRICE_DROPPED'
    if drop['high']<0: return 'PRICE_ROSE'
    return 'NOT_DISCRIMINATING'


def noregret_diagnostics(trajectories, c):
    """D-040 as amended by D-043, from trajectories alone; returns (table, summary) or (None, None).

    Question 1.2 of the sprint: does the remaining LLM firm keep its price once its rival is
    replaced by the no-regret learner? Its final-window price is paired with the same firm in
    the baseline continuation; a positive drop means it priced lower. Only the price answers
    1.2: the firm's Delta also falls mechanically when the learner undercuts it, so it is
    reported per prefix but not summarized.
    The learner's realized external regret and undercut share (SOURCES.md S7 §4.7) and its swap
    regret (S11 Def. 3.2), per period over the branch and in units of its payoff scale, are
    descriptive. A prefix whose NOREGRET branch or baseline window is incomplete is excluded
    and listed, as in the primary; mislabelled data still raises.
    """
    from agents.noregret import price_grid, payoff_scale, realized_regret
    from env.market import Market
    branches=trajectories[trajectories.phase=='branch']
    played=branches[branches.arm=='NOREGRET']
    if played.empty: return None,None
    market=Market.from_config(c['market']); a=c['analysis']; e=c['experiment']
    w,periods=e['window'],e['branch_periods']
    last=final_window(trajectories,c); rows=[]; excluded=[]
    for pid in sorted(int(x) for x in branches.prefix_id.unique()):
        g=played[played.prefix_id==pid]
        if g.empty: excluded.append(pid); continue
        learners=g.loc[g.agent_kind=='NoRegret:hedge','firm'].unique()
        if len(learners)!=1: raise ValueError(f'Prefix {pid}: expected one no-regret firm, found {list(learners)}')
        k=int(learners[0]); llm=1-k
        path=g.pivot(index='relative_period',columns='firm',values='price').reindex(index=range(periods),columns=[0,1])
        window=last[last.prefix_id==pid]
        side=lambda arm,firm: window[(window.arm==arm)&(window.firm==firm)]
        base,base_k,kept,learner=side('baseline',llm),side('baseline',k),side('NOREGRET',llm),side('NOREGRET',k)
        parts=(base,base_k,kept,learner)
        if path.isna().any().any() or any(len(p)!=w or p[['price','delta']].isna().any().any() for p in parts):
            excluded.append(pid); continue
        grid=price_grid(c['noregret'],market,k); scale=payoff_scale(market,k,grid)
        regret=realized_regret(market,k,grid,path[k].to_numpy(),path[llm].to_numpy(),scale)
        rows.append({'prefix_id':pid,'learner_firm':k,'llm_firm':llm,
            'baseline_delta':float(pd.concat([base.delta,base_k.delta]).mean()),
            'llm_price_baseline':float(base.price.mean()),'llm_price_noregret':float(kept.price.mean()),
            'llm_price_drop':float(base.price.mean()-kept.price.mean()),
            'llm_delta_baseline':float(base.delta.mean()),'llm_delta_noregret':float(kept.delta.mean()),
            'learner_price':float(learner.price.mean()),'learner_delta':float(learner.delta.mean()),
            'learner_undercut_share':float((path[k]<path[llm]).mean()),'branch_periods':regret['periods'],
            'payoff_scale':scale,'external_regret_per_period':regret['external']/regret['periods'],
            'swap_regret_per_period':regret['swap']/regret['periods']})
    table=pd.DataFrame(rows,columns=['prefix_id','learner_firm','llm_firm','baseline_delta','llm_price_baseline',
        'llm_price_noregret','llm_price_drop','llm_delta_baseline','llm_delta_noregret','learner_price','learner_delta',
        'learner_undercut_share','branch_periods','payoff_scale','external_regret_per_period','swap_regret_per_period'])
    def spread(col):
        if table.empty: return {'mean':None,'min':None,'max':None}
        return {'mean':float(table[col].mean()),'min':float(table[col].min()),'max':float(table[col].max())}
    fraction=float(a.get('noregret_survival_margin',0.1))
    margin=fraction*float(np.mean(np.asarray(market.monopoly)-np.asarray(market.nash)))
    baseline=bootstrap_mean(table.baseline_delta,a); drop=bootstrap_mean(table.llm_price_drop,a)
    reading=noregret_reading(len(table),baseline,drop,margin,a.get('feasibility_min_delta',0.))
    summary={'n_prefixes':int(len(table)),'excluded_incomplete_prefixes':excluded,
             'baseline_delta':baseline,'llm_price_drop':drop,
             'survival_margin_price':margin,'survival_margin_fraction_of_nash_to_monopoly_gap':fraction,
             'reading':reading,'reading_text':NOREGRET_READINGS[reading],
             'learner_undercut_share':spread('learner_undercut_share'),
             'external_regret_per_period':spread('external_regret_per_period'),
             'swap_regret_per_period':spread('swap_regret_per_period'),
             'regret_units':'per period, as a fraction of the learner payoff scale (its largest one-period grid profit)',
             'interpretation':'Question 1.2 is answered by the remaining LLM firm\'s price only; its Delta also falls '
                              'mechanically when it is undercut. Learner regret and undercut share are descriptive, '
                              'path-conditioned diagnostics, not policy regret against a responsive rival.'}
    return table,summary


# The run-level flag of each nested undercut probe (D-051: under the screen; D-053: with the newcomer).
NESTED_FLAG_NAMES={'SCREEN_VAR_UNDERCUT':'in_screen_flag','SWAP_OTHER_UNDERCUT':'in_swap_flag'}


def identify(trajectories, competence, prefixes, c):
    """Descriptive punishment probes. UNDERCUT is compared with the baseline continuation and
    UNDERCUT_R2 with the R2 continuation (D-037). The same matched-cut test applied to the
    placebo arm versus baseline, with no forced action, gives an empirical false-positive rate
    (SHAM in the D-023..D-043 design, PLACEBO in the screen design, D-048). RAISE, the mirror
    image of the undercut, asks whether a cut follows any jolt rather than a price cut (D-048).
    The nested probes (D-050, D-051) force the same undercut or raise inside SCREEN_VAR, at the first
    period of the final window, and are compared with SCREEN_VAR's own continuation from that state.

    With a cost process (D-050, D-051), and so only in the screen design:
    - recovery is measured against the matched continuation in the same period, since costs move
      prices by up to 10%;
    - each probe also gets the forced firm's deviation gain: its profit summed over the forced period
      and the recovery horizon, minus the same sum in the matched continuation (S22 §4.5's test of
      whether the tested deviation pays);
    - a run-level flag, baseline or in-screen, needs signatures in at least the required share of
      prefixes, and paired lower bounds above 0 for undercut minus raise signatures and for undercut
      minus placebo matched cuts, and a paired upper bound below 0 for the undercut's deviation gain.
    A (prefix, probe) cell with missing periods is excluded and listed, not fatal. The D-023..D-043
    design, which has neither costs nor RAISE, is computed exactly as before."""
    from env.costs import enabled as costs_enabled
    from run.fork import UNDERCUT_ARMS, RAISE_ARMS, NESTED_PROBES, UPWARD_PROBES, nested_start
    ids=c['identification']; records=[]; responses=[]; placebo={}; excluded=[]
    m=ids['punishment_margin']; placebo_arm=ids.get('placebo_arm','SHAM'); H=ids['recovery_horizon']
    matched=costs_enabled(c); probes={**UNDERCUT_ARMS,**RAISE_ARMS,**NESTED_PROBES}; start=nested_start(c)
    for pr in prefixes.to_dict('records'):
        if not pr['included']: continue
        pid=pr['prefix_id']; tr=trajectories[trajectories.prefix_id==pid]
        pre=tr[tr.phase=='prefix'].groupby('firm').tail(c['experiment']['window'])
        actor=int(pr['undercut_actor']); observer=1-actor
        pre_price=float(pre[pre.firm==observer].price.mean())
        before=tr[(tr.phase=='prefix')&(tr.firm==actor)].sort_values('period').iloc[-1].price
        task=competence[(competence.prefix_id==pid)&(competence.arm=='baseline')&(~competence.shock)] if competence is not None else pd.DataFrame()
        price_gap=float(pre.price.mean()-task.price.mean()) if len(task) else float('nan')
        side=lambda arm,firm: tr[(tr.arm==arm)&(tr.firm==firm)].set_index('relative_period')
        if (tr.arm==placebo_arm).any():
            try:
                placebo[pid]=bool(side(placebo_arm,observer).loc[1,'price'] < side('baseline',observer).loc[1,'price']-m)
            except KeyError:
                excluded.append([int(pid),placebo_arm])
        for probe_arm,cont_arm in probes.items():
            if not (tr.arm==probe_arm).any(): continue
            s=start if probe_arm in NESTED_PROBES else 0  # the forced period
            cont=side(cont_arm,observer); probe=side(probe_arm,observer); own_probe=side(probe_arm,actor)
            raised=probe_arm in UPWARD_PROBES
            try:
                prior=before if s==0 else side(cont_arm,actor).loc[s-1,'price']
                actual_deviation=bool(own_probe.loc[s,'price'] > prior+m) if raised else bool(own_probe.loc[s,'price'] < prior-m)
                deeper=bool(probe.loc[s+1,'price'] < probe.loc[s+1,'br_price']-m)
                matched_cut=bool(probe.loc[s+1,'price'] < cont.loc[s+1,'price']-m)
                if matched:
                    span=range(s,s+H+1); own_cont=side(cont_arm,actor)
                    if any(t not in own_probe.index or t not in own_cont.index for t in span): raise KeyError(s+H)
                    gain=float(own_probe.loc[list(span),'profit'].sum()-own_cont.loc[list(span),'profit'].sum())
            except KeyError:
                excluded.append([int(pid),probe_arm]); continue
            recovered=False; width=ids['recovery_window']
            for t in range(2,ids['recovery_horizon']-width+2):
                vals=probe.loc[s+t:s+t+width-1,'price']
                reference=cont.loc[s+t:s+t+width-1,'price'] if matched else pre_price
                band=ids['recovery_fraction']*(np.abs(reference).clip(lower=1e-12) if matched else max(abs(pre_price),1e-12))
                if len(vals)==width and (np.abs(vals-reference)<=band).all(): recovered=True; break
            # Harrington (S5): retaliation may be a return to competitive prices, so undershooting
            # the static best response is reported but not required unless configured (D-029).
            signature=actual_deviation and matched_cut and recovered and (deeper or not ids.get('require_deeper_than_br',True))
            record={'prefix_id':pid,'probe':probe_arm,'continuation':cont_arm,'observer':observer,'pre_price':pre_price,
                    'competence_pre_shock_price':float(task.price.mean()) if len(task) else float('nan'),
                    'prefix_price_gap':price_gap,'high_delta':bool(pre.delta.mean()>=ids['high_delta']),
                    'actual_downward_deviation':actual_deviation,'deeper_than_br':deeper,
                    'matched_cut':matched_cut,'recovered':recovered,'punishment_signature':signature}
            if matched: record.update(forced_period=s,recovery_reference='matched continuation',deviation_gain=gain)
            if raised:
                # Same test after an upward jolt: a "signature" here is a cut that is not a reply to a cut.
                record['actual_upward_deviation']=record.pop('actual_downward_deviation')
                record['matched_raise']=bool(probe.loc[s+1,'price'] > cont.loc[s+1,'price']+m)
            records.append(record)
            for t in probe.index:
                if t<s: continue
                responses.append({'prefix_id':pid,'probe':probe_arm,'relative_period':int(t),'observer':observer,
                    'undercut_price':probe.loc[t,'price'],'continuation_price':cont.loc[t,'price'],
                    'best_response':probe.loc[t,'br_price'],'pre_price':pre_price})
    checks=pd.DataFrame(records); summary={}
    for probe_arm in probes:
        sub=checks[checks.probe==probe_arm] if not checks.empty else checks
        if sub.empty: continue
        if probe_arm in RAISE_ARMS or probe_arm in NESTED_PROBES:
            summary[probe_arm]={'signature_rate':float(sub.punishment_signature.mean()),
                                'matched_cut_rate':float(sub.matched_cut.mean()),'n':int(len(sub)),'flag':None}
            if probe_arm in UPWARD_PROBES: summary[probe_arm]['matched_raise_rate']=float(sub.matched_raise.mean())
            if probe_arm in NESTED_PROBES: summary[probe_arm].update(continuation=probes[probe_arm],forced_period=start)
            continue
        qualified=sub.punishment_signature & sub.high_delta
        if ids['require_competence_gap']: qualified &= sub.prefix_price_gap>ids['competence_price_gap']
        summary[probe_arm]={'signature_rate':float(sub.punishment_signature.mean()),
                            'matched_cut_rate':float(sub.matched_cut.mean()),'n':int(len(sub)),
                            'flag':bool(qualified.mean()>=ids['required_signature_fraction'])}
    result={'collusion_flag':summary.get('UNDERCUT',{}).get('flag',False),'probes':summary,
            'placebo_matched_cut_rate':float(np.mean(list(placebo.values()))) if placebo else None,
            'interpretation':'Descriptive joint behavioural screen; not proof of intent or a confirmatory test. '
                             f'Compare matched_cut_rate with placebo_matched_cut_rate ({placebo_arm} vs baseline, no forced action).'}
    if 'placebo_arm' in ids: result['placebo_arm']=placebo_arm
    if excluded: result['excluded_probe_cells']=excluded
    if 'UNDERCUT' in summary and 'RAISE' in summary:
        # D-048: a cut that follows a forced raise as often as a forced undercut is not specific punishment.
        result['undercut_minus_raise_matched_cut_rate']=summary['UNDERCUT']['matched_cut_rate']-summary['RAISE']['matched_cut_rate']
        # D-050, D-051: the comparisons that carry "cartel" are paired by prefix and get intervals.
        a=c['analysis']; fields=['matched_cut','punishment_signature']+(['deviation_gain'] if matched else [])
        wide=checks.pivot(index='prefix_id',columns='probe',values=fields).astype(float)
        has=lambda probe: probe in wide['matched_cut']
        paired=lambda field,x,y: bootstrap_mean((wide[field][x]-wide[field][y]).dropna(),a)
        ref=pd.Series(placebo,dtype=float)
        versus_placebo=lambda x: bootstrap_mean((wide['matched_cut'][x]-ref.reindex(wide.index)).dropna(),a)
        comparisons={}
        # Each nested undercut probe is paired with the nested raise of the same parent (D-051, D-053).
        nested_pairs=[(d,d[:-len('UNDERCUT')]+'RAISE') for d in NESTED_PROBES if d.endswith('UNDERCUT')]
        pairs=[('UNDERCUT','RAISE','undercut')]+[(d,u,d.lower()) for d,u in nested_pairs if u in NESTED_PROBES]
        for down,up,label in pairs:
            if not has(down): continue
            if has(up):
                comparisons[f'{label}_minus_{up.lower()}_signature']=paired('punishment_signature',down,up)
                comparisons[f'{label}_minus_{up.lower()}_matched_cut']=paired('matched_cut',down,up)
            if placebo: comparisons[f'{label}_minus_placebo_matched_cut']=versus_placebo(down)
            if matched: comparisons[f'{label}_deviation_gain']=bootstrap_mean(wide['deviation_gain'][down].dropna(),a)
        for down,up,label in pairs[1:]:
            if has(down):
                comparisons[f'{label}_minus_undercut_signature']=paired('punishment_signature',down,'UNDERCUT')
                comparisons[f'{label}_minus_undercut_matched_cut']=paired('matched_cut',down,'UNDERCUT')
        result['paired_probe_comparisons']=comparisons
        low=lambda k: (comparisons.get(k) or {}).get('low')
        high=lambda k: (comparisons.get(k) or {}).get('high')
        def flag(label, up, share_ok):
            # Signatures, specific to cuts, beyond the placebo (when a placebo arm was run), and a deviation
            # that did not pay (S22; with a cost process, D-051). A design without a placebo arm (D-053) has
            # the first two conditions only, and says so in its rule.
            return bool(share_ok and (low(f'{label}_minus_{up}_signature') or -1)>0
                        and (not placebo or (low(f'{label}_minus_placebo_matched_cut') or -1)>0)
                        and (not matched or (high(f'{label}_deviation_gain') if high(f'{label}_deviation_gain') is not None else 1)<0))
        result['collusion_flag']=flag('undercut','raise',result['collusion_flag'])
        rule=('at least the required share of {who}; lower bounds above 0 for {x} minus {y} signatures'
              +(' and for {x} minus placebo matched cuts' if placebo else '')
              +('; an upper bound below 0 for the {x} deviation gain' if matched else '')+'; all paired by prefix')
        result['collusion_flag_rule']=('D-050, D-051: ' if placebo else 'D-050, D-053: ')+rule.format(
            who='prefixes with both a high pre-fork Delta and an UNDERCUT signature',x='UNDERCUT',y='RAISE')
        for down,up,label in pairs[1:]:
            if down not in summary: continue
            name=NESTED_FLAG_NAMES.get(down,f'{label}_flag')
            share=summary[down]['signature_rate']>=ids['required_signature_fraction']
            result[name]=flag(label,up.lower(),share)
            result[name+'_rule']=('D-051: ' if down=='SCREEN_VAR_UNDERCUT' else 'D-053: ')+rule.format(who=f'prefixes with a {down} signature',x=down,y=up)
    return checks,pd.DataFrame(responses),result


def staged_design(c):
    """The design section that carries a stage-one rule: analysis.screens (D-046) or analysis.swaps (D-053)."""
    a=c['analysis']
    return a.get('screens') or a.get('swaps') or None


def stage_one_primary(c, out, primary=None, positive_control=None):
    """The primary screen to report, checked against the stage-one record (D-047, D-050, D-051, D-053).

    The record is `positive_control.json` in the run directory (`make stage2` and `merge_runs` put it
    there) or the file given. A live staged run cannot be analysed without one. A record is accepted
    only if its design hash matches the run's. A run that holds only the stage-one prefixes is never
    analysed: its treatment arms stay unread until stage two. In the screen design, `primary` relabels
    which disclosed screen is the primary reading. It is accepted only when the record says PROCEED
    and names the same screen; the record's SHA-256 is written down. Without `primary`, a record that
    switched the primary stops the analysis. Returns the override, or None."""
    import hashlib
    from tools.positive_control import design_hash
    s=c['analysis'].get('screens'); d=staged_design(c); out=Path(out)
    path=Path(positive_control) if positive_control else out/'positive_control.json'
    record=json.loads(path.read_text()) if path.exists() else None
    if not d:
        if primary is not None: raise ValueError(f'--primary must name a disclosed screen of this run, not {primary}')
        return None
    meta=json.loads((out/'metadata.json').read_text()) if (out/'metadata.json').exists() else {}
    if record is None and d.get('stage_one') and meta.get('synthetic') is False:
        raise ValueError(f'A live staged run needs its stage-one record ({path}); for the replication, '
                         'pass the main run\'s with --positive-control (D-051)')
    if record is not None:
        if record.get('design_hash')!=design_hash(c):
            raise ValueError(f'The stage-one record {path} is for a different design (D-051)')
        ran=set(int(x) for x in pd.read_csv(out/'prefixes.csv').prefix_id) if (out/'prefixes.csv').exists() else set()
        first=int((d.get('stage_one') or {}).get('prefixes',0)); total=int(c['experiment']['prefixes'])
        # The stage-one run, or a merge or resume of its parts only, holds no prefix beyond stage one.
        stage_one_only=(ran==set(record.get('prefixes',[])) and c['experiment'].get('prefix_ids')) or \
                       (2<=first<total and ran<=set(range(first)))
        if ran and stage_one_only:
            raise ValueError('This is the stage-one run: its treatment arms are not analysed before stage two (D-051)')
    if not s:
        if primary is not None: raise ValueError(f'--primary must name a disclosed screen of this run, not {primary}')
        return None
    if primary is None:
        if record and record.get('primary_for_stage_two') not in (None,s['primary']):
            raise ValueError(f"Stage one selected {record['primary_for_stage_two']} as the primary ({path}); "
                             f"pass --primary {record['primary_for_stage_two']} (D-050)")
        return None
    if primary not in s['disclosed']:
        raise ValueError(f'--primary must name a disclosed screen of this run, not {primary}')
    if record is None:
        raise ValueError(f'--primary needs the stage-one record {path} (D-050)')
    if record.get('status')!='PROCEED' or record.get('primary_for_stage_two')!=primary:
        raise ValueError(f"The stage-one record says {record.get('status')} with primary "
                         f"{record.get('primary_for_stage_two')}, not PROCEED with {primary} (D-050)")
    if primary==s['primary']: return None
    override={'configured':s['primary'],'used':primary,'rule':'D-047 stage-one contingency (D-050)',
              'positive_control':str(path),'positive_control_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    s['primary']=primary
    return override


def analyze(out, primary=None, positive_control=None):
    """Primary first, written on its own; then the secondary analyses, which may fail without
    taking the primary with them. `primary` and `positive_control`: see stage_one_primary."""
    out=Path(out); c=yaml.safe_load((out/'resolved_config.yaml').read_text())
    override=stage_one_primary(c,out,primary,positive_control)
    tr=pd.read_csv(out/'trajectories.csv'); prefixes=pd.read_csv(out/'prefixes.csv')
    gate=c['experiment'].get('fork_rule','gate')=='gate'
    verdict={'attempted_prefixes':len(prefixes),'fork_rule':c['experiment'].get('fork_rule','gate'),
             'failed_gates':int((~prefixes.gate_passed.astype(bool)).sum()) if gate else 0}
    if c['analysis'].get('swaps'):
        # D-053: the replacement readings are the primary of the replacement design; written before anything else.
        from analysis.swaps import swap_analysis
        stats,swaps=swap_analysis(tr,prefixes,c)
        stats.to_csv(out/'swap_statistics.csv',index=False)
        write_json(out/'swaps.json',swaps); verdict['swaps']=swaps
    if c['analysis'].get('screens'):
        # D-047: the screen readings are the primary of the screen design; written before anything else.
        from analysis.screens import screen_analysis
        stats,matrix,screens=screen_analysis(tr,c)
        if override: screens['primary_override']=override
        stats.to_csv(out/'screen_statistics.csv',index=False); matrix.to_csv(out/'evasion_matrix.csv',index=False)
        write_json(out/'screens.json',screens); verdict['screens']=screens
    if c['analysis'].get('primary_arm'):
        verdict['primary']=primary_from_trajectories(tr,prefixes,c)
        write_json(out/'primary.json',verdict['primary'])
    try:
        # D-040 diagnostics also come from trajectories alone, so competence failures cannot block them.
        table,noregret=noregret_diagnostics(tr,c)
        if table is not None:
            table.to_csv(out/'noregret.csv',index=False); verdict['noregret']=noregret
    except (KeyError,ValueError) as exc:
        verdict['noregret_error']=f'{type(exc).__name__}: {exc}'
    from run.common import competence_enabled
    if not competence_enabled(c):
        # D-046: no restriction is ranked, so there are no competence tasks; the probes need none.
        try:
            checks,responses,identification=identify(tr,None,prefixes,c)
            checks.to_csv(out/'identification.csv',index=False); responses.to_csv(out/'undercut_response.csv',index=False)
            verdict.update(identification)
        except (KeyError,ValueError) as exc:
            verdict['identification_error']=f'{type(exc).__name__}: {exc}'
        write_json(out/'verdict.json',verdict)
        return verdict
    try:
        comp=pd.read_csv(out/'competence.csv')
        delta,shares,costs,dropped=summarize(tr,comp,c)
        summary,pairs,ranking=infer(delta,shares,costs,c,market_outcomes(tr,c))
    except (FileNotFoundError,ValueError,pd.errors.EmptyDataError) as exc:
        verdict['secondary_error']=f'{type(exc).__name__}: {exc}'
        write_json(out/'verdict.json',verdict)
        return verdict
    checks,responses,identification=identify(tr,comp,prefixes,c)
    summary.to_csv(out/'summary.csv',index=False); pairs.to_csv(out/'contrasts.csv',index=False)
    checks.to_csv(out/'identification.csv',index=False); responses.to_csv(out/'undercut_response.csv',index=False)
    paired=pd.concat({'delta':delta,'share':shares,'cost':costs},axis=1)
    paired.columns=['_'.join(x) for x in paired.columns]; paired.to_csv(out/'paired_metrics.csv')
    verdict.update(ranking); verdict.update(identification, excluded_share_prefixes=dropped)
    write_json(out/'verdict.json',verdict)
    return verdict


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--run-dir',required=True)
    p.add_argument('--primary',default=None,help='D-047 stage-one contingency only: the disclosed screen to label primary')
    p.add_argument('--positive-control',default=None,help='stage-one record (default: <run-dir>/positive_control.json)')
    a=p.parse_args(); print(json.dumps(analyze(a.run_dir,a.primary,a.positive_control),indent=2))
