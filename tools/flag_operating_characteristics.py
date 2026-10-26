"""Operating characteristics of the probe flags (D-051), in a stylised simulation.

The no-punishment simulation checks false positives; added punishment periods check sensitivity.
The output is summarised in the screen-design protocol, §8.

By default there is no punishment anywhere: every fork is a common cost-plus path plus independent
decision noise. With k punishment periods, the observer answers each forced undercut (never a forced
raise) by pricing at the static Nash price for k periods, then returns to the path; the forced firm
returns to the path after its forced period. That gives the power of the same flags.
The forced prices are run.fork.forced_price, profits come from the market, SCREEN_VAR_UNDERCUT and
SCREEN_VAR_RAISE share SCREEN_VAR's first periods, and the flags are those of analysis.pipeline.identify.
This is a generator for checking the rule, not a model of LLM agents.
Reports how often the raw D-050 in-screen criterion (signature rate >= 0.5), the D-051 in-screen
flag and the baseline "cartel" flag fire. Run from the repository root:
    python3 -m tools.flag_operating_characteristics [runs] [resamples] [sigmas, comma-separated] [punishment periods]
"""
import sys
import numpy as np, pandas as pd
from run.common import load_config
from run.fork import forced_price
from env.market import Market
from analysis.pipeline import identify

runs=int(sys.argv[1]) if len(sys.argv)>1 else 40
PUNISH=int(sys.argv[4]) if len(sys.argv)>4 else 0
c=load_config('config/main.yaml')
if len(sys.argv)>2: c['analysis']['bootstrap_resamples']=int(sys.argv[2])
m0=Market.from_config(c['market']); grid=c['market']['cost_process']['grid']
B,W,T=c['experiment']['branch_periods'],c['experiment']['window'],100; s=B-W; n=24


def one(rng,sigma):
    rows=[]; prefixes=[]
    for pid in range(n):
        cost=rng.choice(grid,T+B); actor=int(rng.integers(2)); obs=1-actor
        last={}
        for t in range(T):
            p=[cost[t]+.8+rng.normal(0,sigma) for f in (0,1)]
            pi=m0.at_cost(cost[t]).profits(np.array(p))
            for f in (0,1):
                rows.append(dict(prefix_id=pid,arm='prefix',phase='prefix',period=t,relative_period=-1,firm=f,
                                 price=p[f],profit=float(pi[f]),delta=.7,br_price=np.nan))
            last=p
        def fork(arm,forced_at=None,parent=None):
            path={}
            for b in range(B):
                if parent is not None and b<s: p=[parent[(b,0)],parent[(b,1)]]
                else: p=[cost[T+b]+.8+rng.normal(0,sigma) for f in (0,1)]
                if forced_at is not None and b==forced_at:
                    previous=last if b==0 else [path[(b-1,0)],path[(b-1,1)]]
                    p[actor]=forced_price(m0.at_cost(cost[T+b]),arm,actor,previous)
                if PUNISH and forced_at is not None and 'UNDERCUT' in arm and forced_at<b<=forced_at+PUNISH:
                    p[obs]=float(m0.at_cost(cost[T+b]).nash[obs])+rng.normal(0,sigma)
                path[(b,0)],path[(b,1)]=p
            for b in range(B):
                mb=m0.at_cost(cost[T+b]); p=np.array([path[(b,0)],path[(b,1)]]); pi=mb.profits(p)
                for f in (0,1):
                    rows.append(dict(prefix_id=pid,arm=arm,phase='branch',period=T+b,relative_period=b,firm=f,
                                     price=p[f],profit=float(pi[f]),delta=.7,br_price=mb.best_response(f,p[1-f])))
            return path
        fork('baseline'); fork('PLACEBO')
        fork('UNDERCUT',0); fork('RAISE',0)
        sv=fork('SCREEN_VAR'); fork('SCREEN_VAR_UNDERCUT',s,parent=sv); fork('SCREEN_VAR_RAISE',s,parent=sv)
        prefixes.append(dict(prefix_id=pid,included=True,undercut_actor=actor))
    _,_,res=identify(pd.DataFrame(rows),None,pd.DataFrame(prefixes),c)
    return res


print(f'runs per sigma: {runs}; bootstrap resamples: {c["analysis"]["bootstrap_resamples"]}; prefixes: {n}; punishment periods: {PUNISH}')
sigmas=[float(x) for x in sys.argv[3].split(',')] if len(sys.argv)>3 else [0.02,0.05,0.10]
for sigma in sigmas:
    rng=np.random.default_rng(11); out=[]
    for rep in range(runs):
        r=one(rng,sigma); pc=r['paired_probe_comparisons']
        out.append(dict(inscreen_rate=r['probes']['SCREEN_VAR_UNDERCUT']['signature_rate'],
                        in_screen_flag=r['in_screen_flag'],collusion_flag=r['collusion_flag'],
                        sig_low=pc['screen_var_undercut_minus_screen_var_raise_signature']['low'],
                        plc_low=pc['screen_var_undercut_minus_placebo_matched_cut']['low'],
                        gain_high=pc['screen_var_undercut_deviation_gain']['high']))
    d=pd.DataFrame(out)
    print(f"sigma={sigma}: in-screen signature rate mean {d.inscreen_rate.mean():.2f}; "
          f"raw D-050 criterion (rate >= 0.5) met in {(d.inscreen_rate>=.5).mean():.2f} of runs; "
          f"D-051 in-screen flag in {d.in_screen_flag.mean():.2f}; baseline cartel flag in {d.collusion_flag.mean():.2f}; "
          f"conditions met: signature vs raise {(d.sig_low>0).mean():.2f}, vs placebo {(d.plc_low>0).mean():.2f}, "
          f"gain < 0 {(d.gain_high<0).mean():.2f}")
