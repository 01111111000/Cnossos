from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd


def setup(run):
    root=Path(run); meta=json.loads((root/'metadata.json').read_text())
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    label='SYNTHETIC VALIDATION ONLY' if meta['synthetic'] else 'Experimental run'
    return root,label


def save(fig,root,name):
    fig.tight_layout(); fig.savefig(root/(name+'.png'),dpi=160); fig.savefig(root/(name+'.pdf')); plt.close(fig)
