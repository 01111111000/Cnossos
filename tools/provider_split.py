"""Exploratory provider split (D-060, D-062): not pre-registered, for the report's appendix only.

Part B of stage two was finished with the SWAP_OTHER newcomer served by vLLM on Modal instead of
Cerebras, so the serving stack changes with the prefix number. This table gives SWAP_OTHER's Delta
drop, the newcomer's and the incumbent's prices and the in-swap probe outcomes separately for the
Cerebras-served and the Modal-served prefixes. The stack of each prefix comes from the merged run's
metadata (prefix_sources, source_metadata.endpoint_override) and is checked against the endpoint
recorded on each newcomer call in the source runs' calls.jsonl, where present.
Reads swap_statistics.csv and identification.csv written by `make analyze`; writes
provider_split.json and provider_split.md next to them.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
import pandas as pd
import yaml
from analysis.pipeline import bootstrap_mean
from run.fork import prefix_plans

OTHER = ('SWAP_OTHER', 'SWAP_OTHER_UNDERCUT', 'SWAP_OTHER_RAISE')
CEREBRAS, MODAL = 'cerebras', 'modal-vllm'


def stacks(run):
    """prefix -> {source, stack, host} from the merge's provenance."""
    meta = json.loads((run/'metadata.json').read_text())
    by_source = dict(zip(meta['merged_from'], meta['source_metadata']))
    out = {}
    for pid, src in meta['prefix_sources'].items():
        o = by_source[src].get('endpoint_override')
        out[int(pid)] = {'source': src, 'stack': MODAL if o else CEREBRAS, 'host': o['host'] if o else 'api.cerebras.ai'}
    return out


def newcomer_hosts(prefixes, c):
    """Endpoint that answered each prefix's SWAP_OTHER-family newcomer calls, read from the source runs."""
    swapped = {p['prefix_id']: p['undercut_actor'] for p in prefix_plans(c, True)}
    seen = {}
    for src in sorted({v['source'] for v in prefixes.values()}):
        f = Path(src)/'calls.jsonl'
        if not f.exists(): continue
        for line in f.read_text().splitlines():
            if not line.strip(): continue
            d = json.loads(line); pid = int(d.get('prefix_id', -1))
            if pid not in prefixes or prefixes[pid]['source'] != src: continue
            if d.get('phase') != 'branch' or d.get('arm') not in OTHER or int(d.get('firm', -1)) != swapped[pid]: continue
            if d.get('forced') or 'carried_previous' not in d: continue  # a forced probe row is not a call
            u = d.get('usage') or {}
            host = u.get('endpoint_host') or ('api.cerebras.ai' if str(u.get('model', '')).startswith('gpt-oss') else 'no reply')
            seen.setdefault(pid, Counter())[host] += 1
    return {pid: dict(n) for pid, n in sorted(seen.items())}


def split(run_dir):
    run = Path(run_dir); c = yaml.safe_load((run/'resolved_config.yaml').read_text()); a = c['analysis']
    prefixes = stacks(run)
    sw = pd.read_csv(run/'swap_statistics.csv'); sw = sw[sw.arm == 'SWAP_OTHER'].set_index('prefix_id')
    ident = pd.read_csv(run/'identification.csv')
    groups = {CEREBRAS: [p for p, v in prefixes.items() if v['stack'] == CEREBRAS],
              MODAL: [p for p, v in prefixes.items() if v['stack'] == MODAL], 'all': sorted(prefixes)}
    table = {}
    for name, ids in groups.items():
        ids = [p for p in ids if p in sw.index]
        row = {'prefixes': sorted(ids)}
        for col in ('baseline_delta_final', 'arm_delta_final', 'drop_final', 'drop_early', 'newcomer_price_arm',
                    'newcomer_price_drop', 'incumbent_price_drop'):
            row[col] = bootstrap_mean(sw.loc[ids, col].to_numpy(), a)
        row['newcomer_undercut_share'] = float(sw.loc[ids, 'newcomer_undercut_share'].mean()) if ids else None
        for probe in ('SWAP_OTHER_UNDERCUT', 'SWAP_OTHER_RAISE'):
            p = ident[(ident.probe == probe) & ident.prefix_id.isin(ids)]
            row[probe] = {'n': int(len(p)), 'signature_rate': float(p.punishment_signature.mean()) if len(p) else None,
                          'matched_cut_rate': float(p.matched_cut.mean()) if len(p) else None}
            if probe == 'SWAP_OTHER_RAISE' and len(p): row[probe]['matched_raise_rate'] = float(p.matched_raise.astype(float).mean())
        table[name] = row
    hosts = newcomer_hosts(prefixes, c)
    mismatch = sorted(p for p, h in hosts.items() if set(h) != {prefixes[p]['host']})
    return {'label': 'EXPLORATORY (D-060, D-062): not pre-registered; serving stack confounded with prefix number',
            'interval': f"{a.get('interval_method')} bootstrap, {a['confidence']}, {a['bootstrap_resamples']} resamples, seed {a['bootstrap_seed']}, within each group",
            'stack_by_prefix': {str(p): v['stack'] for p, v in sorted(prefixes.items())},
            'newcomer_calls_by_host': {str(p): h for p, h in hosts.items()}, 'host_mismatches': mismatch, 'groups': table}


def markdown(s):
    f = lambda x: 'NA' if x is None else f'{x:.3f}'
    ci = lambda d: f"{f(d['mean'])} [{f(d['low'])}, {f(d['high'])}]" if d['low'] is not None else f(d['mean'])
    names = [g for g in (CEREBRAS, MODAL, 'all') if s['groups'][g]['prefixes']]
    lines = [f"**{s['label']}.** Intervals: {s['interval']}.", '',
             '| SWAP_OTHER (newcomer: gpt-oss-120b) | ' + ' | '.join(names) + ' |', '| --- |' + ' --- |'*len(names)]
    g = s['groups']
    rows = [('Prefixes (n)', lambda r: f"{len(r['prefixes'])}: {','.join(map(str, r['prefixes']))}"),
            ('Baseline final-window Delta', lambda r: ci(r['baseline_delta_final'])),
            ('SWAP_OTHER final-window Delta', lambda r: ci(r['arm_delta_final'])),
            ('Delta drop vs baseline, final window', lambda r: ci(r['drop_final'])),
            ('Delta drop vs baseline, early window', lambda r: ci(r['drop_early'])),
            ('Newcomer final-window price', lambda r: ci(r['newcomer_price_arm'])),
            ("Newcomer price drop vs the replaced firm's baseline", lambda r: ci(r['newcomer_price_drop'])),
            ('Incumbent price drop vs its baseline', lambda r: ci(r['incumbent_price_drop'])),
            ('Share of branch periods the newcomer priced below the incumbent', lambda r: f(r['newcomer_undercut_share'])),
            ('SWAP_OTHER_UNDERCUT: signature rate; matched-cut rate', lambda r: f"{f(r['SWAP_OTHER_UNDERCUT']['signature_rate'])}; {f(r['SWAP_OTHER_UNDERCUT']['matched_cut_rate'])}"),
            ('SWAP_OTHER_RAISE: signature rate; matched-cut rate; matched-raise rate', lambda r: f"{f(r['SWAP_OTHER_RAISE']['signature_rate'])}; {f(r['SWAP_OTHER_RAISE']['matched_cut_rate'])}; {f(r['SWAP_OTHER_RAISE'].get('matched_raise_rate'))}")]
    for label, fn in rows: lines.append(f'| {label} | ' + ' | '.join(fn(g[n]) for n in names) + ' |')
    lines += ['', f"Newcomer calls by endpoint, per prefix: {json.dumps(s['newcomer_calls_by_host'])}",
              f"Prefixes whose newcomer calls disagree with the recorded stack: {s['host_mismatches'] or 'none'}"]
    return '\n'.join(lines)+'\n'


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--run-dir', required=True); args = p.parse_args()
    s = split(args.run_dir); run = Path(args.run_dir)
    (run/'provider_split.json').write_text(json.dumps(s, indent=2)+'\n', encoding='utf-8')
    (run/'provider_split.md').write_text(markdown(s), encoding='utf-8')
    print(markdown(s))
