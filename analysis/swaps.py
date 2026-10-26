"""Replacement design (D-053): does a formed tacit cartel survive the replacement of one member?

Each swap arm forks a prefix's history at T and hands one firm (`swapped_firm` in prefixes.csv) to a
newcomer: a fresh copy of the same model with the firm's records but not its notes (SWAP_SAME), the
same with no records either (SWAP_BLIND), another model (SWAP_OTHER), or a no-regret learner
(NOREGRET, D-040). The incumbent plays on unchanged and is told nothing. Every arm is compared
with the baseline continuation of the same prefix, paired, with the run's bootstrap interval.

Pre-registered readings per arm, checked in order (PROTOCOL.md §6):
  INSUFFICIENT_PREFIXES; BASELINE_NOT_SUPRACOMPETITIVE; RE_FORMS (the early-window Delta drop has a
  lower bound above delta_margin and the final-window drop lies inside ±delta_margin); SURVIVES (final drop inside
  ±delta_margin and the arm's final Delta has a lower bound above the feasibility minimum); ESCALATION
  (final drop upper bound below 0); COLLAPSES (final drop lower bound above 0 and the arm's final Delta
  has an upper bound below `competitive_delta`); EROSION (final drop lower bound above 0, otherwise);
  NOT_DISCRIMINATING.
The incumbent's own final-window price answers question 1.2 as in D-043: PRICE_KEPT / PRICE_DROPPED /
PRICE_ROSE / NOT_DISCRIMINATING, with a margin of `price_margin_fraction` of (p^M - p^N).
The carrier reading combines the three LLM-newcomer arms: where does the cartel live?
"""
import numpy as np
import pandas as pd

SWAP_READINGS = {
    'INSUFFICIENT_PREFIXES': 'Fewer than two complete prefixes.',
    'BASELINE_NOT_SUPRACOMPETITIVE': 'The baseline continuation is not shown to price above the competitive level; nothing to replace.',
    'RE_FORMS': 'The Delta fell by more than the margin in the first window after the swap and was back, within the margin of baseline, in the final window.',
    'SURVIVES': 'The final-window Delta stayed within the margin of the baseline continuation, and above the competitive level.',
    'ESCALATION': 'The final-window Delta rose above the baseline continuation.',
    'COLLAPSES': 'The final-window Delta fell below baseline and is not shown to exceed the competitive band.',
    'EROSION': 'The final-window Delta fell below baseline but stayed, or may have stayed, above the competitive band.',
    'NOT_DISCRIMINATING': 'The intervals neither fit inside the margin nor exclude zero.',
}
PRICE_READINGS = {
    'INSUFFICIENT_PREFIXES': 'Fewer than two complete prefixes.',
    'PRICE_KEPT': "The incumbent's final-window price stayed within the margin of its baseline price.",
    'PRICE_DROPPED': "The incumbent's final-window price fell below its baseline price.",
    'PRICE_ROSE': "The incumbent's final-window price rose above its baseline price.",
    'NOT_DISCRIMINATING': 'The interval neither fits inside the margin nor excludes zero.',
}
HOLDS = ('SURVIVES', 'RE_FORMS', 'ESCALATION')   # the high price is there in the final window
CARRIER_READINGS = {
    'NO_CARTEL': 'No cartel to carry: the baseline continuation is not supra-competitive.',
    'PRIVATE_NOTES': 'A fresh copy of the same model with the records but not the notes did not hold the price: the cartel lives in the private notes.',
    'PUBLIC_RECORDS': 'A fresh copy held the price only when shown the records: the cartel lives in the public price history.',
    'MODEL_SPECIFIC': 'Any fresh copy of the same model held the price; another model did not: what carries the cartel is the model, not what it is shown. Whether the other model colludes at all in self-play is read from the mirror run.',
    'ROBUST': 'Every newcomer held the price: the incumbent and the public history re-form the cartel with any cooperative partner.',
    'UNRESOLVED': 'The arm readings do not fit one of the pre-registered patterns.',
}
CARRIER_ARMS = ('SWAP_SAME', 'SWAP_BLIND', 'SWAP_OTHER')


def swap_reading(n, baseline_delta, arm_delta, drop_final, drop_early, delta_margin, competitive_delta, feasibility_min=0.):
    if n < 2 or drop_final.get('low') is None: return 'INSUFFICIENT_PREFIXES'
    if not baseline_delta['low'] > feasibility_min: return 'BASELINE_NOT_SUPRACOMPETITIVE'
    inside = drop_final['low'] > -delta_margin and drop_final['high'] < delta_margin
    if inside and drop_early.get('low') is not None and drop_early['low'] > delta_margin: return 'RE_FORMS'
    if inside and arm_delta['low'] > feasibility_min: return 'SURVIVES'
    if drop_final['high'] < 0: return 'ESCALATION'
    if drop_final['low'] > 0:
        return 'COLLAPSES' if arm_delta['high'] < competitive_delta else 'EROSION'
    return 'NOT_DISCRIMINATING'


def price_reading(n, drop, margin):
    if n < 2 or drop.get('low') is None: return 'INSUFFICIENT_PREFIXES'
    if drop['low'] > -margin and drop['high'] < margin: return 'PRICE_KEPT'
    if drop['low'] > 0: return 'PRICE_DROPPED'
    if drop['high'] < 0: return 'PRICE_ROSE'
    return 'NOT_DISCRIMINATING'


def carrier_reading(readings):
    """readings: {arm: reading} for the three LLM-newcomer arms (missing arms count as unknown)."""
    r = {arm: readings.get(arm) for arm in CARRIER_ARMS}
    if any(x == 'BASELINE_NOT_SUPRACOMPETITIVE' for x in r.values()): return 'NO_CARTEL'
    if any(x is None or x in ('INSUFFICIENT_PREFIXES', 'NOT_DISCRIMINATING') for x in r.values()): return 'UNRESOLVED'
    held = {arm: x in HOLDS for arm, x in r.items()}
    if not held['SWAP_SAME']: return 'PRIVATE_NOTES'
    if not held['SWAP_BLIND']: return 'PUBLIC_RECORDS'
    if not held['SWAP_OTHER']: return 'MODEL_SPECIFIC'
    return 'ROBUST'


def newcomer_firm(baseline_rows, arm_rows, prefix_record):
    """The firm whose agent changed at the fork: recorded for swap arms, read from the agent labels otherwise."""
    kinds_b = baseline_rows.groupby('firm').agent_kind.first(); kinds_a = arm_rows.groupby('firm').agent_kind.first()
    changed = [int(f) for f in (0, 1) if f in kinds_a and f in kinds_b and kinds_a[f] != kinds_b[f]]
    if len(changed) == 1: return changed[0]
    if 'swapped_firm' in prefix_record and not pd.isna(prefix_record['swapped_firm']): return int(prefix_record['swapped_firm'])
    raise ValueError(f"Cannot identify the replaced firm in prefix {prefix_record.get('prefix_id')}: agent labels {dict(kinds_a)} vs {dict(kinds_b)}")


def swap_statistics(trajectories, prefixes, c):
    """One row per (prefix, swap arm): windowed Deltas and prices of the arm and of the baseline
    continuation, and the re-formation period (the first branch period from which every remaining period's
    Delta is within the margin of the baseline's). Incomplete cells are listed, not dropped silently."""
    e = c['experiment']; w = c['analysis']['swaps']; W, B = e['window'], e['branch_periods']
    control = w['control']; margin = w['delta_margin']
    early = list(range(0, W)); final = list(range(B - W, B))
    b = trajectories[trajectories.phase == 'branch']
    rows = []; incomplete = []
    for pr in prefixes.to_dict('records'):
        if not pr.get('included', True): continue
        pid = int(pr['prefix_id']); g = b[b.prefix_id == pid]
        base = g[g.arm == control]
        for arm in w['arms']:
            x = g[g.arm == arm]
            if x.empty or base.empty: incomplete.append((pid, arm, 'missing cell')); continue
            paths = {}
            ok = True
            for label, part in (('base', base), ('arm', x)):
                p = part.pivot(index='relative_period', columns='firm', values='price').reindex(index=range(B), columns=[0, 1])
                d = part.groupby('relative_period').delta.mean().reindex(range(B))
                if p.isna().any().any() or d.isna().any(): ok = False
                paths[label] = (p, d)
            if not ok: incomplete.append((pid, arm, 'incomplete cell')); continue
            k = newcomer_firm(base, x, pr); inc = 1 - k
            (pb, db), (pa, da) = paths['base'], paths['arm']
            # Re-formation period: the first branch period from which every remaining period's market Delta
            # lies within the margin of the baseline's (descriptive; None if never).
            within = (da - db).abs() <= margin
            reformed = None
            for start in range(B):
                if bool(within[start:].all()): reformed = start; break
            rows.append({'prefix_id': pid, 'arm': arm, 'newcomer_firm': k, 'incumbent_firm': inc,
                         'baseline_delta_final': float(db[final].mean()), 'arm_delta_final': float(da[final].mean()),
                         'baseline_delta_early': float(db[early].mean()), 'arm_delta_early': float(da[early].mean()),
                         'drop_final': float(db[final].mean() - da[final].mean()), 'drop_early': float(db[early].mean() - da[early].mean()),
                         'incumbent_price_baseline': float(pb[inc][final].mean()), 'incumbent_price_arm': float(pa[inc][final].mean()),
                         'incumbent_price_drop': float(pb[inc][final].mean() - pa[inc][final].mean()),
                         'newcomer_price_baseline_firm': float(pb[k][final].mean()), 'newcomer_price_arm': float(pa[k][final].mean()),
                         'newcomer_price_drop': float(pb[k][final].mean() - pa[k][final].mean()),
                         'newcomer_undercut_share': float((pa[k] < pa[inc]).mean()),
                         'reformed_at': reformed})
    return pd.DataFrame(rows), incomplete


def swap_analysis(trajectories, prefixes, c):
    """All replacement readings. Returns (statistics, result)."""
    from analysis.pipeline import bootstrap_mean
    from env.market import Market
    a = c['analysis']; w = a['swaps']; feas = a.get('feasibility_min_delta', 0.)
    market = Market.from_config(c['market'])
    price_margin = float(w.get('price_margin_fraction', 0.1)) * float(np.mean(np.asarray(market.monopoly) - np.asarray(market.nash)))
    stats, incomplete = swap_statistics(trajectories, prefixes, c)
    out = {'control': w['control'], 'arms': {}, 'delta_margin': w['delta_margin'], 'competitive_delta': w['competitive_delta'],
           'price_margin': price_margin, 'price_margin_fraction_of_nash_to_monopoly_gap': w.get('price_margin_fraction', 0.1),
           'interval_method': a.get('interval_method', 'percentile'), 'confidence': a['confidence'],
           'excluded_incomplete_cells': [list(x) for x in incomplete]}
    for arm in w['arms']:
        s = stats[stats.arm == arm]
        n = int(len(s))
        if n == 0:
            out['arms'][arm] = {'n_prefixes': 0, 'reading': 'INSUFFICIENT_PREFIXES', 'reading_text': SWAP_READINGS['INSUFFICIENT_PREFIXES']}
            continue
        base = bootstrap_mean(s.baseline_delta_final, a); arm_delta = bootstrap_mean(s.arm_delta_final, a)
        drop_final = bootstrap_mean(s.drop_final, a); drop_early = bootstrap_mean(s.drop_early, a)
        inc_drop = bootstrap_mean(s.incumbent_price_drop, a); new_drop = bootstrap_mean(s.newcomer_price_drop, a)
        reading = swap_reading(n, base, arm_delta, drop_final, drop_early, w['delta_margin'], w['competitive_delta'], feas)
        price = price_reading(n, inc_drop, price_margin)
        reformed = s.reformed_at.dropna()
        out['arms'][arm] = {
            'n_prefixes': n, 'reading': reading, 'reading_text': SWAP_READINGS[reading],
            'baseline_delta_final': base, 'arm_delta_final': arm_delta,
            'delta_drop_final': drop_final, 'delta_drop_early': drop_early,
            'arm_delta_early': bootstrap_mean(s.arm_delta_early, a),
            'incumbent_price_reading': price, 'incumbent_price_reading_text': PRICE_READINGS[price],
            'incumbent_price_drop': inc_drop, 'newcomer_price_drop': new_drop,
            'newcomer_undercut_share': float(s.newcomer_undercut_share.mean()),
            'reformed_within_branch_share': float(len(reformed) / n),
            'median_reformation_period': float(reformed.median()) if len(reformed) else None,
            'newcomer_firms': {int(r.prefix_id): int(r.newcomer_firm) for r in s.itertuples()}}
    readings = {arm: v['reading'] for arm, v in out['arms'].items()}
    carrier = carrier_reading(readings)
    out['carrier'] = {'reading': carrier, 'reading_text': CARRIER_READINGS[carrier], 'from_arms': {arm: readings.get(arm) for arm in CARRIER_ARMS}}
    out['interpretation'] = ('Each arm is paired with the baseline continuation of the same prefix. "Holds" means SURVIVES, '
                             'RE_FORMS or ESCALATION. The readings describe prices and profits; they say nothing about intent. '
                             'The carrier reading is a pre-registered mapping of the three LLM-newcomer readings (D-053).')
    return stats, out
