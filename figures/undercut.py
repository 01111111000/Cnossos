import argparse
from figures.common import setup,save,plt,pd


def plot(run):
    root,label=setup(run); raw=pd.read_csv(root/'undercut_response.csv')
    if 'probe' not in raw: raw['probe']='UNDERCUT'
    probes=list(dict.fromkeys(raw.probe))
    fig,axes=plt.subplots(1,len(probes),figsize=(7*len(probes),4),squeeze=False,sharey=True)
    for ax,probe in zip(axes[0],probes):
        d=raw[raw.probe==probe].groupby('relative_period').mean(numeric_only=True)
        for field,name in [('undercut_price','Observer after forced undercut'),('continuation_price','Matched continuation'),('best_response','Static best response'),('pre_price','Pre-fork price')]:
            ax.plot(d.index,d[field],label=name)
        ax.set_title(probe+(' (rival prices hidden)' if probe=='UNDERCUT_R2' else ''))
        ax.set(xlabel='Periods since forced action (0)')
        from matplotlib.ticker import MaxNLocator
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    axes[0][0].set_ylabel('Mean observer price'); axes[0][0].legend(fontsize=8)
    fig.suptitle(label+' — Undercut response',fontsize=10); save(fig,root,'undercut')


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--run-dir',required=True); plot(p.parse_args().run_dir)
