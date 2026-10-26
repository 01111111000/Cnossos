import argparse
from pathlib import Path
import pandas as pd
import yaml
from env.market import Market
from run.common import load_config,require_live,metadata,write_json,CallLogger,validate,competence_enabled
from run.fork import run_forks


def execute(c, out, live=False, workers=None):
    if live: require_live(c)
    validate(c)
    workers=workers or c['experiment'].get('workers',1)
    out=Path(out)
    if out.exists() and any(out.iterdir()): raise FileExistsError(f'Will not overwrite run {out}')
    out.mkdir(parents=True,exist_ok=True)
    market=Market.from_config(c['market']); meta=metadata(c,live)
    write_json(out/'metadata.json',{**meta,'workers':workers})
    (out/'resolved_config.yaml').write_text(yaml.safe_dump(c,sort_keys=True))
    b=c['budget']
    logger=CallLogger(out/'calls.jsonl',meta,c['llm'].get('max_consecutive_carries') if live else None,
                      b.get('max_spend_usd_per_run') if live else None,
                      (b.get('input_price_per_million',0.),b.get('output_price_per_million',0.)))
    if c['experiment'].get('prefix_only') or not competence_enabled(c):
        prefixes,trajectories=run_forks(c,market,out,logger,live,workers)
        return prefixes,trajectories,None
    prefixes,trajectories,rows=run_forks(c,market,out,logger,live,workers,with_competence=True)
    competence=pd.DataFrame(rows); competence.to_csv(out/'competence.csv',index=False)
    return prefixes,trajectories,competence


def smoke_preset(c):
    """Pipeline and provider qualification only. Smoke data never enter the main analysis."""
    c['experiment'].update(c.get('smoke',{}).get('experiment',{'prefixes':2,'max_prefix':100,'branch_periods':12}))
    if competence_enabled(c):
        c['competence'].update(c.get('smoke',{}).get('competence',{'periods':10,'shock_at':5}))
    return c


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config',default='config/main.yaml')
    p.add_argument('--run-id',required=True)
    p.add_argument('--live',action='store_true')
    p.add_argument('--synthetic',action='store_true')
    p.add_argument('--smoke',action='store_true')
    p.add_argument('--workers',type=int,default=None,help='parallel prefixes (default: experiment.workers)')
    p.add_argument('--prefix-ids',default=None,
                   help='comma-separated subset of prefixes to (re)run with their original seeds, e.g. after a crash (D-036)')
    args=p.parse_args()
    if args.live==args.synthetic: p.error('Choose exactly one of --live and --synthetic')
    if Path(args.run_id).name!=args.run_id: p.error('run-id must be a single path component')
    c=load_config(args.config,args.synthetic)
    if args.smoke: smoke_preset(c)
    if args.prefix_ids: c['experiment']['prefix_ids']=[int(x) for x in args.prefix_ids.split(',')]
    validate(c)
    execute(c,Path('results')/args.run_id,args.live,args.workers)


if __name__=='__main__': main()
