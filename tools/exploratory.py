"""Exploratory checks for the report's Appendix B (not pre-registered).

1. Frozen histories: both firms still at the opening price in every period of the pre-fork window and of the
   baseline continuation (here 2.5, Delta -0.551; histories 6, 7 and 22 of main-20261024d). The
   pre-registered readings (analysis.swaps, analysis.pipeline: the same code, margins and bootstrap as
   `make analyze`) are recomputed with those histories excluded. As a check, the same code on all
   histories must reproduce verdict.json.
2. Price paths: the mean price of the newcomer's seat and of the incumbent per branch period, in each
   replacement arm and in the baseline continuation of the same seats, over all histories and over the
   non-frozen ones.
Writes exploratory.json, exploratory.md, price_paths.csv and price_paths.png/.pdf in the run directory.
Usage: python -m tools.exploratory --run-dir results/main-20261024d
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from analysis.pipeline import identify, noregret_diagnostics
from analysis.swaps import swap_analysis
from env.market import Market
from figures.common import plt, save
from run.common import jsonable

LABELS = {'SWAP_SAME': 'same model, records', 'SWAP_BLIND': 'same model, nothing shown',
          'SWAP_OTHER': 'other model, records', 'NOREGRET': 'no-regret learner'}
SEAT_COLOR = {'newcomer': '#d6552a', 'incumbent': '#2a78d6'}


def frozen_histories(tr, c):
    """Histories still at the opening price (the most common period-0 price; 2.5 in main-20261024d) for both
    firms in every period of the pre-fork window and of the baseline continuation. A history that converged
    to another constant price (history 20 holds 1.9, near the monopoly price) is not frozen."""
    W = c['experiment']['window']; out = {}
    pre_all = tr[tr.phase == 'prefix']; opening = float(pre_all[pre_all.period == 0].price.round(6).mode()[0])
    for pid, g in tr.groupby('prefix_id'):
        pre = g[g.phase == 'prefix']; window = pre[pre.period > pre.period.max() - W]
        base = g[(g.phase == 'branch') & (g.arm == c['analysis']['swaps']['control'])]
        if (pd.concat([window.price, base.price]).round(6) == opening).all():
            out[int(pid)] = {'price': opening, 'prefix_phase_share_at_price': float((pre.price.round(6) == opening).mean())}
    return out


def readings(tr, prefixes, c):
    """The pre-registered readings for a set of histories, by the analysis's own functions."""
    _, swaps = swap_analysis(tr, prefixes, c)
    _, noregret = noregret_diagnostics(tr, c)
    _, _, ident = identify(tr, None, prefixes, c)
    return {'n': int(len(prefixes)), 'swaps': swaps, 'noregret': noregret,
            'collusion_flag': ident.get('collusion_flag'), 'in_swap_flag': ident.get('in_swap_flag'), 'probes': ident.get('probes')}


def price_paths(tr, stats, c, keep):
    """Mean price per branch period of the newcomer's seat and the incumbent, per arm and in the baseline."""
    control = c['analysis']['swaps']['control']; br = tr[(tr.phase == 'branch') & tr.prefix_id.isin(keep)]
    rows = []
    for arm in c['analysis']['swaps']['arms']:
        seats = stats[(stats.arm == arm) & stats.prefix_id.isin(keep)][['prefix_id', 'newcomer_firm', 'incumbent_firm']]
        for source in (arm, control):
            g = br[br.arm == source].merge(seats, on='prefix_id')
            for seat in ('newcomer', 'incumbent'):
                s = g[g.firm == g[f'{seat}_firm']].groupby('relative_period').price.agg(['mean', 'count'])
                rows += [{'arm': arm, 'continuation': 'arm' if source == arm else 'baseline', 'seat': seat,
                          'relative_period': int(t), 'mean_price': float(r['mean']), 'n': int(r['count'])} for t, r in s.iterrows()]
    return pd.DataFrame(rows)


def figure(paths, c, market, root, frozen):
    B, W = c['experiment']['branch_periods'], c['experiment']['window']; arms = list(c['analysis']['swaps']['arms'])
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.4), sharex=True, sharey=True)
    p = paths[paths.set == 'all']
    for ax, arm in zip(axes.flat, arms):
        for seat in ('newcomer', 'incumbent'):
            for cont, ls in (('arm', '-'), ('baseline', '--')):
                s = p[(p.arm == arm) & (p.seat == seat) & (p.continuation == cont)].set_index('relative_period').mean_price
                ax.plot(s.index, s.values, color=SEAT_COLOR[seat], ls=ls, lw=1.5 if cont == 'arm' else 1.0,
                        label=f"{seat}{'' if cont == 'arm' else ' (baseline seat)'}")
        for y, name in ((float(np.mean(market.nash)), 'Nash'), (float(np.mean(market.monopoly)), 'monopoly')):
            ax.axhline(y, color='#52514e', lw=0.6, ls=':'); ax.text(B - 0.5, y, f' {name}', va='center', fontsize=8, color='#52514e')
        ax.axvspan(B - W - 0.5, B - 0.5, color='#f0efec', zorder=0); ax.set_title(f'{arm}: {LABELS.get(arm, arm)}', fontsize=10)
    for ax in axes[1]: ax.set_xlabel('branch period (0 = first period after the swap)'); ax.set_xticks(range(0, B, 5))
    for ax in axes[:, 0]: ax.set_ylabel('mean price')
    axes[0, 0].legend(fontsize=8, frameon=False)
    fig.suptitle(f'Exploratory: mean price paths, all {p.n.max()} histories (frozen: {sorted(frozen) or "none"}); final window shaded', fontsize=10)
    save(fig, root, 'price_paths')


def markdown(s):
    f = lambda d: 'NA' if not d or d.get('mean') is None else (f"{d['mean']:.3f} [{d['low']:.3f}, {d['high']:.3f}]" if d.get('low') is not None else f"{d['mean']:.3f}")
    a, x = s['all'], s['excluding_frozen']
    lines = [f"**EXPLORATORY (not pre-registered).** Frozen histories (both firms still at the opening price over the pre-fork window and the baseline continuation): "
             + ', '.join(f"{k} (price {v['price']}, {v['prefix_phase_share_at_price']:.1%} of prefix-phase prices)" for k, v in s['frozen'].items())
             + f". Readings by the pre-registered code; the full-set readings equal verdict.json: {'yes' if s['full_set_matches_verdict'] else 'NO'}.", '',
             f"| | All histories (n = {a['n']}) | Frozen excluded (n = {x['n']}) |", '| --- | --- | --- |',
             f"| Carrier reading | {a['swaps']['carrier']['reading']} | {x['swaps']['carrier']['reading']} |"]
    for arm in a['swaps']['arms']:
        ra, rx = a['swaps']['arms'][arm], x['swaps']['arms'][arm]
        lines += [f"| {arm}: reading | {ra['reading']} | {rx['reading']} |",
                  f"| {arm}: Delta drop, final window | {f(ra['delta_drop_final'])} | {f(rx['delta_drop_final'])} |",
                  f"| {arm}: arm Delta, final window | {f(ra['arm_delta_final'])} | {f(rx['arm_delta_final'])} |",
                  f"| {arm}: incumbent price reading | {ra['incumbent_price_reading']} | {rx['incumbent_price_reading']} |"]
    arm0 = next(iter(a['swaps']['arms']))
    lines += [f"| Baseline Delta, final window | {f(a['swaps']['arms'][arm0]['baseline_delta_final'])} | {f(x['swaps']['arms'][arm0]['baseline_delta_final'])} |",
              f"| NOREGRET question 1.2 | {a['noregret']['reading']} | {x['noregret']['reading']} |",
              f"| collusion_flag; in_swap_flag | {a['collusion_flag']}; {a['in_swap_flag']} | {x['collusion_flag']}; {x['in_swap_flag']} |",
              '', '| Final-window mean price (all histories) | newcomer seat | incumbent | baseline: newcomer seat | baseline: incumbent |', '| --- | --- | --- | --- | --- |']
    for arm, r in s['final_window_prices'].items():
        lines.append(f"| {arm} | {r['arm']['newcomer']:.3f} | {r['arm']['incumbent']:.3f} | {r['baseline']['newcomer']:.3f} | {r['baseline']['incumbent']:.3f} |")
    return '\n'.join(lines)+'\n'


def main(run_dir):
    root = Path(run_dir); c = yaml.safe_load((root/'resolved_config.yaml').read_text())
    tr = pd.read_csv(root/'trajectories.csv'); prefixes = pd.read_csv(root/'prefixes.csv')
    frozen = frozen_histories(tr, c); keep = [p for p in prefixes.prefix_id if int(p) not in frozen]
    full = readings(tr, prefixes, c)
    verdict = json.loads((root/'verdict.json').read_text())
    norm = lambda x: json.dumps(json.loads(json.dumps(x, default=jsonable)), sort_keys=True)  # as write_json stores it
    matches = norm(full['swaps']) == norm(verdict['swaps'])
    sub = readings(tr[tr.prefix_id.isin(keep)], prefixes[prefixes.prefix_id.isin(keep)].reset_index(drop=True), c)
    stats, _ = swap_analysis(tr, prefixes, c)
    paths = pd.concat([price_paths(tr, stats, c, list(prefixes.prefix_id)).assign(set='all'),
                       price_paths(tr, stats, c, keep).assign(set='non_frozen')], ignore_index=True)
    paths.to_csv(root/'price_paths.csv', index=False)
    W, B = c['experiment']['window'], c['experiment']['branch_periods']
    fw = paths[(paths.set == 'all') & (paths.relative_period >= B - W)].groupby(['arm', 'continuation', 'seat']).mean_price.mean()
    final_prices = {arm: {cont: {seat: float(fw[(arm, cont, seat)]) for seat in ('newcomer', 'incumbent')} for cont in ('arm', 'baseline')}
                    for arm in c['analysis']['swaps']['arms']}
    figure(paths, c, Market.from_config(c['market']), root, frozen)
    s = {'label': 'EXPLORATORY: not pre-registered (report Appendix B)', 'frozen': {str(k): v for k, v in frozen.items()},
         'full_set_matches_verdict': matches, 'all': full, 'excluding_frozen': sub, 'final_window_prices': final_prices}
    (root/'exploratory.json').write_text(json.dumps(s, indent=2, default=jsonable)+'\n', encoding='utf-8')
    (root/'exploratory.md').write_text(markdown(s), encoding='utf-8')
    print(markdown(s))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--run-dir', required=True); main(p.parse_args().run_dir)
