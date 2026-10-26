"""Provider qualification for the Friday smoke (D-024). Reads a run's calls.jsonl only.

A decision is one (prefix, phase, arm, period, firm) request group made by the LLM agent.
PASS requires every D-024 threshold; the report also gives the measured token usage that
`make budget OUTPUT_TOKENS=...` should be re-run with. Price levels are descriptive only.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from run.common import write_json


def _get(d, *path, default=None):
    for key in path:
        if not isinstance(d, dict) or key not in d: return default
        d = d[key]
    return d


def report(run_dir):
    run_dir = Path(run_dir); c = yaml.safe_load((run_dir/'resolved_config.yaml').read_text())
    thresholds = c.get('smoke', {}).get('thresholds', {'min_valid':0.95,'max_carried':0.02,'max_truncated':0.02})
    groups = defaultdict(list); attempts = []
    for line in (run_dir/'calls.jsonl').read_text().splitlines():
        d = json.loads(line)
        if d.get('forced') or 'carried_previous' not in d: continue  # forced actions and mock rows
        key = (d.get('prefix_id'), d.get('phase'), d.get('arm'), d.get('period'), d.get('firm'))
        groups[key].append(d); attempts.append(d)
    if not attempts: raise ValueError('No LLM calls in this run: was it a live run?')
    decisions = len(groups)
    first_valid = sum(1 for g in groups.values() if g[0].get('failure') is None)
    valid = sum(1 for g in groups.values() if any(a.get('failure') is None for a in g))
    carried = sum(1 for g in groups.values() if any(a.get('carried_previous') for a in g))
    truncated = sum(1 for a in attempts if 'finish_reason=length' in str(a.get('failure') or ''))
    failures = Counter(str(a['failure']).split(':')[0][:60] for a in attempts if a.get('failure'))
    usage = [a.get('usage') or {} for a in attempts]
    num = lambda xs: np.array([x for x in xs if isinstance(x,(int,float))], dtype=float)
    prompt = num(u.get('prompt_tokens') for u in usage); completion = num(u.get('completion_tokens') for u in usage)
    reasoning = num(_get(u,'completion_tokens_details','reasoning_tokens') for u in usage)
    cached = num(_get(u,'prompt_tokens_details','cached_tokens') for u in usage)
    seconds = num(_get(u,'time_info','total_time') for u in usage)
    b = c['budget']
    spend = (prompt.sum()*b.get('input_price_per_million',0.) + completion.sum()*b.get('output_price_per_million',0.))/1e6
    rates = {'valid_decision_rate': valid/decisions, 'first_attempt_valid_rate': first_valid/decisions,
             'carried_decision_rate': carried/decisions, 'truncated_attempt_rate': truncated/len(attempts)}
    checks = {'valid': rates['valid_decision_rate'] >= thresholds['min_valid'],
              'carried': rates['carried_decision_rate'] <= thresholds['max_carried'],
              'truncated': rates['truncated_attempt_rate'] <= thresholds['max_truncated']}
    out = {'run': str(run_dir), 'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks,
           'thresholds': thresholds, 'decisions': decisions, 'attempts': len(attempts), **rates,
           'failure_kinds': dict(failures.most_common(10)),
           'models_reported': sorted({str(u.get('model')) for u in usage if u.get('model')}),
           'finish_reasons': dict(Counter(str(u.get('finish_reason')) for u in usage if 'finish_reason' in u)),
           'backoffs_total': int(sum(u.get('backoffs',0) or 0 for u in usage)),
           'mean_prompt_tokens': float(prompt.mean()) if prompt.size else None,
           'mean_completion_tokens': float(completion.mean()) if completion.size else None,
           'p95_completion_tokens': float(np.percentile(completion,95)) if completion.size else None,
           'mean_reasoning_tokens': float(reasoning.mean()) if reasoning.size else None,
           'cached_prompt_share': float(cached.sum()/prompt.sum()) if cached.size and prompt.sum() else None,
           'mean_provider_seconds': float(seconds.mean()) if seconds.size else None,
           'estimated_spend_usd': float(spend),
           'rerun_budget_with': f"make budget OUTPUT_TOKENS={int(round(completion.mean()))}" if completion.size else None}
    tr_path = run_dir/'trajectories.csv'
    if tr_path.exists():
        tr = pd.read_csv(tr_path); w = c['experiment']['window']; pre = tr[tr.phase=='prefix']
        last = pre[pre.period >= pre.period.max()+1-w]
        out['descriptive_only_prefix_delta'] = {int(k):round(float(v),3) for k,v in last.groupby('prefix_id').delta.mean().items()}
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--run-dir', required=True); a = p.parse_args()
    result = report(a.run_dir); write_json(Path(a.run_dir)/'smoke_report.json', result)
    print(json.dumps(result, indent=2))
