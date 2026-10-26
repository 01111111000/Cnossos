"""Primary contrast (D-026): paired Delta removal by R2, one point per prefix."""
import argparse
import json
import numpy as np
from figures.common import setup,save,plt,pd


def plot(run):
    root,label=setup(run); verdict=json.loads((root/'verdict.json').read_text())
    if 'primary' not in verdict: raise ValueError('No pre-registered primary contrast in verdict.json')
    pr=verdict['primary']; arm=pr['arm']
    import yaml
    from analysis.pipeline import final_window
    c=yaml.safe_load((root/'resolved_config.yaml').read_text())
    last=final_window(pd.read_csv(root/'trajectories.csv'),c)
    last=last[~last.prefix_id.isin(pr['excluded_incomplete_prefixes'])]
    d=last[last.arm.isin(['baseline',arm])].groupby(['prefix_id','arm']).delta.mean().unstack()
    base=d['baseline']; treated=d[arm]
    fig,(ax1,ax2)=plt.subplots(1,2,figsize=(9,4),gridspec_kw={'width_ratios':[1.3,1]})
    for i in base.index:
        ax1.plot([0,1],[base[i],treated[i]],color='0.6',lw=.8,marker='o',ms=3)
    ax1.plot([0,1],[base.mean(),treated.mean()],color='C0',lw=2.2,marker='o',label='Mean')
    ax1.set(xticks=[0,1],xticklabels=['Baseline',arm],xlim=(-.3,1.3),ylabel='Delta (final window)',
            title='Paired outcome per prefix')
    ax1.axhline(0,color='gray',lw=.6); ax1.axhline(1,color='gray',lw=.6,ls=':')
    removal=(base-treated).to_numpy()
    ax2.scatter(np.zeros_like(removal)+np.linspace(-.08,.08,len(removal)),removal,color='0.5',s=12)
    ax2.errorbar([0],[pr['removal']],yerr=[[pr['removal']-pr['removal_low']],[pr['removal_high']-pr['removal']]],
                 fmt='o',color='C0',capsize=5,lw=2)
    ax2.axhline(0,color='gray',lw=.6)
    ax2.set(xticks=[],xlim=(-.5,.5),ylabel='Delta removed (baseline minus '+arm+')',
            title=f"{pr['reading']}  (n={pr['n_prefixes']})")
    fig.suptitle(label+' — Primary contrast',fontsize=10)
    save(fig,root,'primary')


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--run-dir',required=True); plot(p.parse_args().run_dir)
