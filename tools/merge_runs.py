"""Assemble one analysable run from the per-prefix parts of several run directories (D-036).

Use after a run stopped part-way (outage, circuit breaker, spend cap): rerun only the
missing prefixes with `--prefix-ids`, same config and seed, into a new run directory,
then merge. Only complete prefixes are taken; the configs must match except for
`experiment.prefix_ids` and `experiment.workers`; a prefix may come from one run only.
A stage-one record (`positive_control.json`) in any source run is carried over, so that the
analysis of the merged run is checked against it (D-051); two different records refuse to merge.
"""
import argparse
import json
from pathlib import Path
import pandas as pd
import yaml
from run.common import write_json, competence_enabled
from run.fork import arms, competence_arms

IGNORED = ('prefix_ids', 'workers')


def comparable(c):
    c = json.loads(json.dumps(c)); [c['experiment'].pop(k, None) for k in IGNORED]; return c


def complete_prefixes(run, c):
    parts = Path(run)/'parts'; e = c['experiment']; found = {}
    for f in sorted(parts.glob('prefix_p*.json')):
        record = json.loads(f.read_text()); pid = int(record['prefix_id'])
        tr = pd.read_csv(parts/f'trajectories_p{pid}.csv')
        branch = tr[tr.phase=='branch']
        ok = (tr.phase=='prefix').sum()==2*e['max_prefix'] and all(
            (branch.arm==arm).sum()==2*e['branch_periods'] for arm in arms(c))
        if not competence_enabled(c):
            if ok: found[pid] = (record, tr, None)  # the screen design runs no competence tasks (D-046)
            continue
        comp = [parts/f'competence_p{pid}_f{firm}_{arm}.csv' for firm in range(2) for arm in competence_arms(c)]
        ok = ok and all(p.exists() and len(pd.read_csv(p))==c['competence']['periods'] for p in comp)
        if ok: found[pid] = (record, tr, pd.concat([pd.read_csv(p) for p in comp], ignore_index=True))
    return found


def merge(runs, output):
    output = Path(output)
    if output.exists() and any(output.iterdir()): raise FileExistsError(f'Will not overwrite run {output}')
    configs = [yaml.safe_load((Path(r)/'resolved_config.yaml').read_text()) for r in runs]
    if any(comparable(x) != comparable(configs[0]) for x in configs[1:]):
        raise ValueError('Runs differ in configuration beyond prefix_ids/workers; they cannot be merged')
    c = configs[0]; c['experiment']['prefix_ids'] = None; taken = {}; sources = {}
    for run, cc in zip(runs, configs):
        for pid, unit in complete_prefixes(run, cc).items():
            if pid in taken: raise ValueError(f'Prefix {pid} is complete in two runs; choose one explicitly')
            taken[pid] = unit; sources[pid] = str(run)
    missing = sorted(set(range(c['experiment']['prefixes'])) - set(taken))
    output.mkdir(parents=True, exist_ok=True)
    order = sorted(taken)
    pd.DataFrame([taken[p][0] for p in order]).to_csv(output/'prefixes.csv', index=False)
    pd.concat([taken[p][1] for p in order], ignore_index=True).to_csv(output/'trajectories.csv', index=False)
    if competence_enabled(c):
        pd.concat([taken[p][2] for p in order], ignore_index=True).to_csv(output/'competence.csv', index=False)
    (output/'resolved_config.yaml').write_text(yaml.safe_dump(c, sort_keys=True))
    metas = [json.loads((Path(r)/'metadata.json').read_text()) for r in runs]
    records = {(Path(r)/'positive_control.json').read_text() for r in runs if (Path(r)/'positive_control.json').exists()}
    if len(records) > 1: raise ValueError('The source runs carry different stage-one records; merge refused (D-051)')
    if records: (output/'positive_control.json').write_text(records.pop())
    write_json(output/'metadata.json', {**metas[0], 'merged_from': [str(r) for r in runs],
               'source_metadata': metas, 'prefix_sources': sources, 'missing_prefixes': missing})
    return {'prefixes': order, 'missing': missing, 'sources': sources}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--runs', nargs='+', required=True); p.add_argument('--output', required=True)
    a = p.parse_args(); print(json.dumps(merge(a.runs, a.output), indent=2))
