"""The replacement design at a glance (D-053): what happened to the market's Delta after one agent was swapped.

Left: the mean Delta path across prefixes, the last W pre-fork periods and the B branch periods, one line
per arm; the fork is the vertical rule, the final window is shaded. Right: each arm's final-window Delta
drop against the baseline continuation, paired per prefix, with the run's interval (swaps.json) and the
pre-registered "kept" band. Readings are printed next to each arm. Mean paths are descriptive; the
readings come from the paired intervals.
"""
import argparse
import json
import yaml
from figures.common import setup, save, plt, pd

INK, MUTED, BAND = '#0b0b0b', '#52514e', '#f0efec'
PALETTE = {'baseline': '#0b0b0b', 'SWAP_SAME': '#2a78d6', 'SWAP_BLIND': '#7a9ad9', 'SWAP_OTHER': '#d6552a',
           'NOREGRET': '#4f9a4f'}
LABELS = {'baseline': 'baseline (no swap)', 'SWAP_SAME': 'same model, notes wiped', 'SWAP_BLIND': 'same model, nothing shown',
          'SWAP_OTHER': 'other model', 'NOREGRET': 'no-regret learner'}


def plot(run):
    root, label = setup(run)
    c = yaml.safe_load((root/'resolved_config.yaml').read_text()); w = c['analysis']['swaps']; e = c['experiment']
    sw = json.loads((root/'swaps.json').read_text())
    tr = pd.read_csv(root/'trajectories.csv')
    W, B = e['window'], e['branch_periods']
    arms = [w['control']] + [a for a in w['arms'] if a in sw['arms']]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={'width_ratios': [3, 2]})
    pre = tr[tr.phase == 'prefix']; fork = int(pre.period.max()) + 1
    pre_path = pre[pre.period >= fork - W].groupby('period').delta.mean()
    x_pre = pre_path.index - fork
    ax1.plot(x_pre, pre_path.values, color=INK, lw=1.2, label='_nolegend_')
    br = tr[tr.phase == 'branch']
    for arm in arms:
        g = br[br.arm == arm].groupby('relative_period').delta.mean().reindex(range(B))
        ax1.plot(g.index, g.values, color=PALETTE.get(arm, MUTED), lw=1.6 if arm == w['control'] else 1.3,
                 ls='-' if arm == w['control'] else '--', label=LABELS.get(arm, arm))
    ax1.axvline(-0.5, color=MUTED, lw=0.8); ax1.axvspan(B - W - 0.5, B - 0.5, color=BAND, zorder=0)
    ax1.axhline(0, color=MUTED, lw=0.6, ls=':'); ax1.axhline(1, color=MUTED, lw=0.6, ls=':')
    ax1.set_xlabel('branch period (0 = first period after the swap)'); ax1.set_ylabel('Delta (0 = Nash, 1 = joint monopoly)')
    ax1.set_title('Mean Delta path across prefixes', loc='left'); ax1.legend(frameon=False, fontsize=8)
    rows = [(a, sw['arms'][a]) for a in arms if a != w['control']]
    y = list(range(len(rows)))[::-1]
    ax2.axvspan(-w['delta_margin'], w['delta_margin'], color=BAND, zorder=0)
    for yi, (arm, r) in zip(y, rows):
        d = r.get('delta_drop_final')
        if d and d.get('low') is not None:
            ax2.plot([d['low'], d['high']], [yi, yi], color=PALETTE.get(arm, MUTED), lw=2)
            ax2.plot([d['mean']], [yi], 'o', color=PALETTE.get(arm, MUTED))
        ax2.text(1.02, yi, r['reading'], transform=ax2.get_yaxis_transform(), fontsize=8, va='center', color=INK)
    ax2.set_yticks(y); ax2.set_yticklabels([LABELS.get(a, a) for a, _ in rows], fontsize=8)
    ax2.axvline(0, color=MUTED, lw=0.6)
    ax2.set_xlabel('final-window Delta drop vs baseline (paired; shaded: "kept" band)')
    ax2.set_title('Readings', loc='left')
    fig.suptitle(f"Replacement design — {label}; carrier reading: {sw['carrier']['reading']}", fontsize=10, x=0.01, ha='left')
    save(fig, root, 'swaps')
    return root/'swaps.png'


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--run-dir', required=True)
    print(plot(p.parse_args().run_dir))
