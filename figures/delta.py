import argparse
import numpy as np
from figures.common import setup,save,plt,pd


def plot(run):
    root,label=setup(run); d=pd.read_csv(root/'summary.csv')
    fig,ax=plt.subplots(figsize=(7,4))
    ax.errorbar(d.arm,d.delta,yerr=np.maximum(0,np.vstack([d.delta-d.delta_low,d.delta_high-d.delta])),fmt='o',capsize=4)
    ax.axhline(0,color='gray',lw=.6); ax.set(ylabel='Delta',title=label+' — Delta by arm')
    save(fig,root,'delta')


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--run-dir',required=True); plot(p.parse_args().run_dir)
