"""The evasion matrix at a glance (D-047, D-050): what each notice moved, against the placebo notice.

Three panels share the rows (one per notice arm). Panels 1 and 2 show the move of each screen's
statistic towards passing that screen, the reported primary first (read from screens.json, so a
stage-one switch of the primary is reflected); panel 3 shows the fall in Delta, with the
pre-registered "kept" band shaded. In the statistic panels a filled marker is the statistic that arm
disclosed to the agents and a hollow marker one they were not told about; Delta is never disclosed
and is drawn as a square. All values are paired differences per prefix, with the run's intervals
(evasion_matrix.csv).
"""
import argparse
import json
import yaml
from figures.common import setup, save, plt, pd

INK, MUTED, BAND, MARK = '#0b0b0b', '#52514e', '#f0efec', '#2a78d6'  # dataviz reference palette, light
LABELS = {'STAT_PLACEBO': 'Statistic published, no screen', 'OVERSIGHT': 'Oversight announced',
          'SCREEN_VAR': 'Variance screen disclosed', 'SCREEN_LEVEL': 'Level screen disclosed'}
ROWS = ('STAT_PLACEBO', 'OVERSIGHT', 'SCREEN_VAR', 'SCREEN_LEVEL')


def panels(root):
    """(title, statistic, sign, band) per panel; sign turns a raw difference into 'towards passing'."""
    s = yaml.safe_load((root/'resolved_config.yaml').read_text())['analysis']['screens']
    reported = root/'screens.json'
    primary = json.loads(reported.read_text())['primary'] if reported.exists() else s['primary']
    out = []
    for arm in [primary]+[a for a in s['disclosed'] if a != primary]:
        spec = s['disclosed'][arm]
        sign = 1 if spec['flagged'] == 'below' else -1
        out.append((f"{spec['statistic']}: move towards passing\nthe {LABELS.get(arm, arm).split(' ')[0].lower()} screen"
                    + (' (primary)' if arm == primary else ''), spec['statistic'], sign, None))
    out.append(('Delta: fall against the placebo\n(shaded: pre-registered "kept" band)', 'delta', -1, s['delta_margin']))
    return out, s


def plot(run):
    root, label = setup(run)
    m = pd.read_csv(root/'evasion_matrix.csv')
    spec, s = panels(root)
    arms = [a for a in ROWS if a in set(m.arm)]
    fig, axes = plt.subplots(1, len(spec), figsize=(3.4*len(spec), 0.62*len(arms)+1.9), sharey=True, squeeze=False)
    for ax, (title, stat, sign, band) in zip(axes[0], spec):
        if band: ax.axvspan(-band, band, color=BAND, zorder=0)
        ax.axvline(0, color=MUTED, lw=.8, zorder=1)
        for y, arm in enumerate(arms):
            r = m[(m.arm == arm) & (m.statistic == stat) & (m.versus == s['control'])]
            if r.empty: continue
            r = r.iloc[0]; x = sign*r.mean_difference
            lo, hi = sorted((sign*r.low, sign*r.high))
            ax.plot([lo, hi], [y, y], color=MARK, lw=1.6, solid_capstyle='round', zorder=2)
            marker = 's' if stat == 'delta' else 'o'
            filled = stat == 'delta' or bool(r.disclosed_to_agents)
            ax.plot([x], [y], marker, ms=7, color=MARK, markerfacecolor=MARK if filled else 'white', markeredgewidth=1.6, zorder=3)
        ax.set_title(title, fontsize=9, color=INK, loc='left')
        ax.tick_params(colors=MUTED, labelsize=8.5); ax.grid(axis='x', color=BAND, lw=.6)
        for side in ('left', 'bottom'): ax.spines[side].set_color(MUTED)
    axes[0][0].set_yticks(range(len(arms)), [LABELS.get(a, a) for a in arms], color=INK)
    axes[0][0].invert_yaxis()
    fig.suptitle(f"{label} — paired change against the placebo notice (95% intervals).\nStatistic panels: filled = "
                 "disclosed in that arm, hollow = undisclosed. Delta (square) is never disclosed.",
                 fontsize=9, color=INK, x=.01, ha='left')
    save(fig, root, 'screens')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--run-dir', required=True); plot(p.parse_args().run_dir)
