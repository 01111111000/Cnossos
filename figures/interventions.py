"""Track 1.5 at a glance: collusion removed and consumer harm removed, per intervention.

One row per intervention, the same matched histories for all of them. Hollow markers are
interventions without a demonstrated competence cost bound (benchmarks and controls).
"""
import argparse
from figures.common import setup, save, plt, pd

ORDER = ['R1', 'R2', 'R3', 'R4', 'OVERSIGHT', 'NOREGRET', 'SHAM']
LABELS = {'R1': 'R1 last period only', 'R2': 'R2 rival prices hidden', 'R3': 'R3 no notes',
          'R4': 'R4 rival prices delayed', 'OVERSIGHT': 'Oversight notice',
          'NOREGRET': 'No-regret participant', 'SHAM': 'SHAM (control)'}


def plot(run):
    root, label = setup(run)
    s = pd.read_csv(root/'summary.csv').set_index('arm')
    arms = [a for a in ORDER if a in s.index]
    panels = [('removal', 'Delta removed (baseline minus arm)')]
    if 'consumer_harm_removed' in s:
        panels.append(('consumer_harm_removed', 'Consumer harm removed'))
    fig, axes = plt.subplots(1, len(panels), figsize=(5.2*len(panels), 0.55*len(arms)+1.6), sharey=True, squeeze=False)
    for ax, (field, title) in zip(axes[0], panels):
        for y, arm in enumerate(arms):
            r = s.loc[arm]; x = r[field]; lo = r[field+'_low']; hi = r[field+'_high']
            certified = isinstance(r.get('cost_status'), str) and r.cost_status == 'certified_eligible'
            ax.errorbar([x], [y], xerr=[[max(0, x-lo)], [max(0, hi-x)]], fmt='o', capsize=3, color='C0' if arm != 'SHAM' else '0.5',
                        markerfacecolor='C0' if certified else 'white')
        ax.axvline(0, color='gray', lw=.6)
        ax.set(title=title, yticks=range(len(arms)), yticklabels=[LABELS.get(a, a) for a in arms])
    axes[0][0].invert_yaxis()  # the y axis is shared: invert it once
    fig.suptitle(label+' — Interventions on matched histories (95% intervals; filled = cost certified)', fontsize=10)
    save(fig, root, 'interventions')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--run-dir', required=True); plot(p.parse_args().run_dir)
