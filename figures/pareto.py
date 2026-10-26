import argparse
from figures.common import setup,save,plt,pd
import yaml


def plot(run):
    root,label=setup(run); d=pd.read_csv(root/'summary.csv'); d=d[d.arm.isin(['R1','R2','R3','R4'])]
    c=yaml.safe_load((root/'resolved_config.yaml').read_text()); fig,ax=plt.subplots(figsize=(7,4))
    metric='share_removed' if c['analysis'].get('ranking_metric','share')=='share' else 'removal'
    low,high=('share_low','share_high') if metric=='share_removed' else ('removal_low','removal_high')
    for marker,r in zip(['o','s','^','D'],d.itertuples()):
        y=getattr(r,metric)
        ax.errorbar(r.cost,y,xerr=[[max(0,r.cost-r.cost_low)],[max(0,r.cost_high-r.cost)]],
                    yerr=[[max(0,y-getattr(r,low))],[max(0,getattr(r,high)-y)]],fmt=marker,capsize=3,label=r.arm)
    ax.legend(title='Restriction',loc='upper right')
    ax.axvline(c['analysis']['tolerance'],color='gray',ls='--',lw=.8)
    ax.axhline(0,color='gray',lw=.6)
    ax.set(xlabel='Competence cost (added mean normalized regret per period)',
           ylabel='Share removed' if metric=='share_removed' else 'Delta removed (baseline minus arm)',
           title=label+' — Removal and competence cost')
    save(fig,root,'pareto')


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--run-dir',required=True); plot(p.parse_args().run_dir)
