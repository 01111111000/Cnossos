"""Prefix IDs of each stage of the main run (D-046, D-050, D-053), read from the config.

Stage one is the first `stage_one.prefixes` of the design section (analysis.screens or analysis.swaps); stage two is the rest of
`experiment.prefixes`. The Makefile calls this, so the stage split lives in one place, inside the
config hash.
"""
import argparse
from run.common import read_config


def stage_prefixes(c, stage):
    design=c['analysis'].get('screens') or c['analysis'].get('swaps') or {}   # D-053: either staged design
    total=int(c['experiment']['prefixes']); first=int((design.get('stage_one') or {}).get('prefixes',0))
    if not 2<=first<total: raise ValueError(f'Stage one needs 2 <= analysis.screens.stage_one.prefixes < {total}')
    return list(range(first)) if stage==1 else list(range(first,total))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('stage',type=int,choices=(1,2)); p.add_argument('--config',default='config/main.yaml')
    a=p.parse_args(); print(','.join(str(x) for x in stage_prefixes(read_config(a.config),a.stage)))
