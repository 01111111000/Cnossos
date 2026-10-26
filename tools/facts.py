"""Facts table for the report: every number the prose may use, with the file it comes from.

Reported numerical claims must be supported by this table or another identified result file.
"""
import argparse
import json
from pathlib import Path
import pandas as pd


def fmt(x, digits=3):
    return 'NA' if x is None or (isinstance(x,float) and x!=x) else f'{x:.{digits}f}'


def facts(run_dir):
    run = Path(run_dir); v = json.loads((run/'verdict.json').read_text())
    meta = json.loads((run/'metadata.json').read_text())
    s = pd.read_csv(run/'summary.csv').set_index('arm') if (run/'summary.csv').exists() else pd.DataFrame()
    prefixes = pd.read_csv(run/'prefixes.csv')
    ident_path = run/'identification.csv'
    ident = pd.read_csv(ident_path) if ident_path.exists() and ident_path.stat().st_size > 1 else pd.DataFrame()
    rows = []
    add = lambda label, value, source: rows.append((label, value, source))
    if meta.get('synthetic'): add('WARNING', 'SYNTHETIC VALIDATION RUN — not evidence', 'metadata.json')
    add('Provider / model', f"{meta.get('provider')} / {meta.get('model_id')}", 'metadata.json')
    add('Run date (UTC)', meta.get('date'), 'metadata.json')
    add('Git SHA (dirty)', f"{meta.get('git_sha')} ({meta.get('git_dirty')})", 'metadata.json')
    add('Prefixes attempted', str(v['attempted_prefixes']), 'verdict.json')
    if meta.get('alt_model_id'): add('Alternate provider / model (SWAP_OTHER newcomer)', f"{meta.get('alt_provider')} / {meta.get('alt_model_id')}", 'metadata.json')
    if 'swaps' in v:
        sw = v['swaps']; ci3 = lambda d: f"{fmt(d['mean'])} [{fmt(d['low'])}, {fmt(d['high'])}]"
        add('Carrier reading (pre-registered, D-053)', f"{sw['carrier']['reading']} — {sw['carrier']['reading_text']}", 'verdict.json:swaps')
        add('Carrier reading: arm readings it combines', str(sw['carrier']['from_arms']), 'verdict.json:swaps')
        add('Interval method / confidence', f"{sw['interval_method']} / {sw['confidence']}", 'verdict.json:swaps')
        add('Margins: Delta / competitive band / incumbent price', f"±{sw['delta_margin']} / below {sw['competitive_delta']} / ±{fmt(sw['price_margin'])}", 'verdict.json:swaps')
        for arm, r in sw['arms'].items():
            add(f'{arm}: reading (vs {sw["control"]})', f"{r['reading']} — {r['reading_text']}", 'verdict.json:swaps')
            if r.get('n_prefixes', 0) == 0: continue
            add(f'{arm}: prefixes analysed', str(r['n_prefixes']), 'verdict.json:swaps')
            add(f'{arm}: baseline final-window Delta [CI]', ci3(r['baseline_delta_final']), 'verdict.json:swaps')
            add(f'{arm}: final-window Delta [CI]', ci3(r['arm_delta_final']), 'verdict.json:swaps')
            add(f'{arm}: early-window Delta [CI]', ci3(r['arm_delta_early']), 'verdict.json:swaps')
            add(f'{arm}: Delta drop vs baseline, final window [CI] (margin ±{sw["delta_margin"]})', ci3(r['delta_drop_final']), 'verdict.json:swaps')
            add(f'{arm}: Delta drop vs baseline, early window [CI]', ci3(r['delta_drop_early']), 'verdict.json:swaps')
            add(f'{arm}: incumbent price reading (question 1.2)', f"{r['incumbent_price_reading']} — {r['incumbent_price_reading_text']}", 'verdict.json:swaps')
            add(f'{arm}: incumbent price drop vs its baseline [CI]', ci3(r['incumbent_price_drop']), 'verdict.json:swaps')
            add(f"{arm}: newcomer price drop vs the replaced firm's baseline [CI]", ci3(r['newcomer_price_drop']), 'verdict.json:swaps')
            add(f'{arm}: share of branch periods the newcomer priced below the incumbent', fmt(r['newcomer_undercut_share'], 2), 'verdict.json:swaps')
            add(f'{arm}: share of prefixes back within the margin of baseline during the branch; median period',
                f"{fmt(r['reformed_within_branch_share'], 2)}; {fmt(r['median_reformation_period'], 1)}", 'verdict.json:swaps')
        add('Excluded incomplete (prefix, arm, reason) cells', str(sw['excluded_incomplete_cells']), 'verdict.json:swaps')
    if 'screens' in v:
        sc = v['screens']; ci3 = lambda d: f"{fmt(d['mean'])} [{fmt(d['low'])}, {fmt(d['high'])}]"
        add('Primary reading (pre-registered, D-047, D-050)', f"{sc['primary']}: {sc['reading']} — {sc['reading_text']}", 'verdict.json:screens')
        if sc.get('primary_override'):
            o = sc['primary_override']
            add('Primary switched at stage one (D-047 contingency, D-050)',
                f"configured {o['configured']}, reported {o['used']}; stage-one record {o['positive_control']} (SHA-256 {o['positive_control_sha256']})",
                'verdict.json:screens')
        add('Interval method / confidence', f"{sc['interval_method']} / {sc['confidence']}", 'verdict.json:screens')
        for arm, r in sc['readings'].items():
            tag = ' (primary)' if r['primary'] else ' (secondary)'
            add(f'{arm}{tag}: reading', f"{r['reading']} — {r['reading_text']}", 'verdict.json:screens')
            add(f'{arm}: prefixes analysed', str(r['n_prefixes']), 'verdict.json:screens')
            add(f"{arm}: control ({r['control']}) Delta [CI]", ci3(r['control_delta']), 'verdict.json:screens')
            add(f'{arm}: treated Delta [CI]', ci3(r['treated_delta']), 'verdict.json:screens')
            add(f"{arm}: Delta drop vs {r['control']} [CI] (margin ±{r['delta_margin']})", ci3(r['delta_drop']), 'verdict.json:screens')
            add(f"{arm}: disclosed statistic {r['statistic']}, control pass margin [CI] (threshold {r['threshold']}, flagged {r['flagged']})",
                ci3(r['control_pass_margin']), 'verdict.json:screens')
            add(f"{arm}: treated pair pass margin [CI] (smaller of the two firms; above 0 = both pass)", ci3(r['treated_pass_margin']), 'verdict.json:screens')
            add(f"{arm}: shift of {r['statistic']} towards passing [CI] (margin ±{r['statistic_margin']})", ci3(r['shift_towards_passing']), 'verdict.json:screens')
            if r.get('excluded_prefixes'):
                add(f'{arm}: prefixes excluded, with reasons', str(r['excluded_prefixes']), 'verdict.json:screens')
            if 'shift_beyond_oversight' in r:
                add(f"{arm}: shift beyond the generic oversight notice ({r['shift_beyond_oversight']['arm']}) [CI]", ci3(r['shift_beyond_oversight']), 'verdict.json:screens')
            if 'shift_beyond_salience_control' in r:
                add(f"{arm}: shift beyond the statistic published without a screen ({r['shift_beyond_salience_control']['arm']}) [CI]",
                    ci3(r['shift_beyond_salience_control']), 'verdict.json:screens')
            for name, sp in (r.get('specificity') or {}).items():
                add(f"{arm}: specificity against {sp['versus']} ({name}, D-051)", f"{sp['reading']} — {sp['reading_text']}", 'verdict.json:screens')
            if 'just_passing_share' in r:
                j = r['just_passing_share']
                add(f"{arm}: share of firms just passing (band {j['band']}), control / treated; treated minus control [CI] (descriptive)",
                    f"{fmt(j['control'],2)} / {fmt(j['treated'],2)}; {ci3(j['treated_minus_control'])}", 'verdict.json:screens')
            if 'consumer_harm_removed' in r:
                add(f'{arm}: consumer harm removed [CI]', ci3(r['consumer_harm_removed']), 'verdict.json:screens')
        add('Excluded incomplete (prefix, arm) cells', str(sc['excluded_incomplete_cells']), 'verdict.json:screens')
        add('Missing (prefix, arm) cells', str(sc.get('missing_cells', [])), 'verdict.json:screens')
        if sc.get('notes_mentions'):
            add('Share of final-window notes using a monitoring word (descriptive; baseline has no notice)',
                ', '.join(f'{a} {fmt(x,2)}' for a, x in sc['notes_mentions'].items()), 'verdict.json:screens')
        matrix_path = run/'evasion_matrix.csv'
        if matrix_path.exists():
            m = pd.read_csv(matrix_path)
            shown = ['delta','consumer_harm','movement_ratio','cost_corr','markup','price_index','follow_corr',
                     'pass_margin_variance','pass_margin_level']
            for r in m[m.statistic.isin(shown)].itertuples():
                add(f'Evasion matrix: {r.arm} minus {r.versus}, {r.statistic}' + (' (disclosed)' if r.disclosed_to_agents else ''),
                    f'{fmt(r.mean_difference)} [{fmt(r.low)}, {fmt(r.high)}]', 'evasion_matrix.csv')
    if 'primary' in v:
        p = v['primary']
        add('Primary status', p['status'], 'verdict.json:primary')
        add(f"Primary removal ({p['arm']}) [95% CI]", f"{fmt(p['removal'])} [{fmt(p['removal_low'])}, {fmt(p['removal_high'])}]", 'verdict.json:primary')
        add('Primary reading (pre-registered)', p['reading_text'], 'verdict.json:primary')
        add('Primary prefixes analysed / excluded as incomplete', f"{p['n_prefixes']} / {p['excluded_incomplete_prefixes']}", 'verdict.json:primary')
        add('Interval method', p['interval_method'], 'verdict.json:primary')
        add('Primary paired SD', fmt(p.get('removal_sd')), 'verdict.json:primary')
        add('Baseline Delta [95% CI]', f"{fmt(p['baseline_delta'])} [{fmt(p['baseline_delta_low'])}, {fmt(p['baseline_delta_high'])}]", 'verdict.json:primary')
        ci = lambda d: f"{fmt(d.get('mean', d.get('removal')))} [{fmt(d['low'])}, {fmt(d['high'])}]"
        if 'sham_removal' in p:
            add('SHAM removal [CI]', ci(p['sham_removal']), 'verdict.json:primary')
            add(f"{p['arm']} removal beyond SHAM [CI]", ci(p['removal_beyond_sham']), 'verdict.json:primary')
        if 'consumer_harm_removed' in p:
            add(f"Consumer harm removed by {p['arm']} [CI]", ci(p['consumer_harm_removed']), 'verdict.json:primary')
        if 'excluding_carried' in p:
            e = p['excluding_carried']
            add(f"Removal excluding prefixes with carried decisions (n={e['n']})", ci(e), 'verdict.json:primary')
        if 'high_stratum' in p:
            h = p['high_stratum']; add(f"High-stratum removal (n={h['n']})", ci(h), 'verdict.json:primary')
    if 'secondary_error' in v:
        add('Secondary analyses', 'NOT AVAILABLE: '+v['secondary_error'], 'verdict.json')
    if 'verdict' in v:
        add('Ranking verdict', f"{v['verdict']}; winner={v['winner']}; top set={v['top_set']}", 'verdict.json')
    order=['baseline','R1','R2','R3','R4','OVERSIGHT','NOREGRET','SHAM','UNDERCUT','UNDERCUT_R2']
    for arm in sorted(s.index,key=lambda a: order.index(a) if a in order else len(order)):
        r = s.loc[arm]
        add(f'{arm}: Delta [CI]', f"{fmt(r.delta)} [{fmt(r.delta_low)}, {fmt(r.delta_high)}]", 'summary.csv')
        if arm != 'baseline':
            add(f'{arm}: removal [CI]', f"{fmt(r.removal)} [{fmt(r.removal_low)}, {fmt(r.removal_high)}]", 'summary.csv')
        if arm != 'baseline' and 'consumer_harm_removed' in r:
            add(f'{arm}: consumer harm removed [CI]', f"{fmt(r.consumer_harm_removed)} [{fmt(r.consumer_harm_removed_low)}, {fmt(r.consumer_harm_removed_high)}]", 'summary.csv')
            add(f'{arm}: change in total quantity [CI]', f"{fmt(r.quantity_change,2)} [{fmt(r.quantity_change_low,2)}, {fmt(r.quantity_change_high,2)}]", 'summary.csv')
        if isinstance(r.get('cost_status'), str):
            add(f'{arm}: competence cost [CI], status', f"{fmt(r.cost)} [{fmt(r.cost_low)}, {fmt(r.cost_high)}], {r.cost_status}", 'summary.csv')
    for arm, b in v.get('benchmarks', {}).items():
        add(f"{arm} removal minus {b['versus']} removal [CI]", f"{fmt(b['difference'])} [{fmt(b['low'])}, {fmt(b['high'])}]", 'verdict.json:benchmarks')
    if 'noregret' in v:
        nr = v['noregret']; ci2 = lambda d: f"{fmt(d['mean'])} [{fmt(d['low'])}, {fmt(d['high'])}]"
        span = lambda d: f"mean {fmt(d['mean'])} (range {fmt(d['min'])} to {fmt(d['max'])})"
        add('NOREGRET: question 1.2 reading (pre-registered, D-043)', f"{nr['reading']}: {nr['reading_text']}", 'verdict.json:noregret')
        add('NOREGRET: remaining LLM firm price drop vs its own baseline continuation [CI]', ci2(nr['llm_price_drop']), 'verdict.json:noregret')
        add('NOREGRET: margin for "kept its price" (price units)', fmt(nr['survival_margin_price']), 'verdict.json:noregret')
        add('NOREGRET: prefixes analysed / excluded as incomplete', f"{nr['n_prefixes']} / {nr['excluded_incomplete_prefixes']}", 'verdict.json:noregret')
        add('NOREGRET learner (descriptive): share of branch periods priced below the LLM firm', span(nr['learner_undercut_share']), 'verdict.json:noregret')
        add('NOREGRET learner (descriptive): realized external regret per period (payoff-scale units)', span(nr['external_regret_per_period']), 'verdict.json:noregret')
        add('NOREGRET learner (descriptive): realized swap regret per period (payoff-scale units)', span(nr['swap_regret_per_period']), 'verdict.json:noregret')
    if 'noregret_error' in v:
        add('NOREGRET diagnostics', 'NOT AVAILABLE: '+v['noregret_error'], 'verdict.json')
    for probe, d in v.get('probes', {}).items():
        add(f'{probe}: punishment signatures (descriptive)', f"{round(d['signature_rate']*d['n'])} of {d['n']} prefixes; matched-cut rate {fmt(d['matched_cut_rate'],2)}", 'verdict.json:probes')
    if v.get('placebo_matched_cut_rate') is not None:
        add(f"Placebo matched-cut rate ({v.get('placebo_arm','SHAM')} vs baseline)", fmt(v['placebo_matched_cut_rate'],2), 'verdict.json')
    if v.get('undercut_minus_raise_matched_cut_rate') is not None:
        add('Matched-cut rate, UNDERCUT minus RAISE (descriptive, D-048)', fmt(v['undercut_minus_raise_matched_cut_rate'],2), 'verdict.json')
    for name, d in (v.get('paired_probe_comparisons') or {}).items():
        add(f'Paired probe comparison (D-050): {name} [CI]', f"{fmt(d['mean'],2)} [{fmt(d['low'],2)}, {fmt(d['high'],2)}] (n={d['n']})", 'verdict.json:paired_probe_comparisons')
    if 'collusion_flag' in v:
        add('Behavioural screen flag (descriptive)' + (f" — {v['collusion_flag_rule']}" if v.get('collusion_flag_rule') else ''),
            str(v.get('collusion_flag')), 'verdict.json')
    if 'in_screen_flag' in v:
        add(f"In-screen punishment flag — {v['in_screen_flag_rule']}", str(v['in_screen_flag']), 'verdict.json')
    if 'in_swap_flag' in v:
        add(f"Punishment flag with the newcomer (SWAP_OTHER) — {v['in_swap_flag_rule']}", str(v['in_swap_flag']), 'verdict.json')
    if v.get('excluded_probe_cells'):
        add('Probe cells excluded as incomplete', str(v['excluded_probe_cells']), 'verdict.json')
    add('High-price stratum prefixes', f"{int(prefixes.high_stratum.sum())} of {len(prefixes)}", 'prefixes.csv')
    lines = ['| Fact | Value | Source |', '| --- | --- | --- |']
    lines += [f'| {a} | {b} | `{run.name}/{c}` |' for a, b, c in rows]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--run-dir', required=True); a = p.parse_args()
    table = facts(a.run_dir); (Path(a.run_dir)/'facts.md').write_text(table); print(table)
