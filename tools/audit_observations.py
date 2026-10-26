"""Information-loss audit: deterministic quantity can undo price redaction."""
import argparse
import json
import re
from pathlib import Path
import numpy as np
from env.market import Market
from env.observations import build,canonical_rows
from run.common import load_config


def reconstruct(market, firm, own_price, own_quantity):
    own_quantity=own_quantity/market.size  # market share
    if not 0<own_quantity<1: raise ValueError('Quantity must be interior')
    vi=(market.a[firm]-own_price)/market.mu
    # e^v_r = e^v_i * (1/q_i - 1) - e^v_out; compute in log space.
    x=vi+np.log1p(-own_quantity)-np.log(own_quantity)
    y=market.outside/market.mu
    if x<=y: raise ValueError('Rival demand numerically unrecoverable')
    log_rival=x+np.log(-np.expm1(y-x))
    return float(market.a[1-firm]-market.mu*log_rival)


def audit(c):
    market=Market.from_config(c['market']); p=market.monopoly.tolist()
    h=[{'period':0,'prices':p,'quantities':market.quantities(p).tolist(),
        'profits':market.profits(p).tolist(),'notes':['','']}]
    report=[]
    for arm in ('R2','R4'):
        obs=build(h,0,arm,market,c); row=canonical_rows(obs)[-1]
        exact=reconstruct(market,0,h[0]['prices'][0],h[0]['quantities'][0])
        shown=reconstruct(market,0,row['own_price'],row['own_quantity'])
        report.append({'arm':arm,'explicit_rival_price':row.get('rival_price'),
            'reconstructable_if_parameters_known':bool(np.isclose(exact,p[1],atol=1e-7)),
            'demand_parameters_disclosed':c['observations']['market_information'] in ('full','own'),
            'absolute_error':abs(exact-p[1]),
            'absolute_error_from_displayed_values':abs(shown-p[1]),
            'meaning':'Exact inversion needs the demand parameters; with market_information '
                      'cost_only they are withheld, so only approximate learning from own sales remains.'})
    return report


def notes_check(path, arm='R1'):
    # Lexical matches only: copying and coincidence cannot be distinguished.
    prices={}; calls=matches=historical_matches=0
    for line in Path(path).read_text().splitlines():
        d=json.loads(line); key=(d['prefix_id'],d.get('phase'),d['arm'])
        # LLM calls log the structured observation separately from the rendered text.
        obs=d.get('observation',d.get('raw_input'))
        if not isinstance(obs,dict): continue
        base_key=(d['prefix_id'],d['firm'],'prefix')
        key=base_key if d.get('phase')=='prefix' else (d['prefix_id'],d['firm'],d['arm'],d.get('phase'))
        known=prices.setdefault(key,set(prices.get(base_key,set())))
        for row in canonical_rows(obs):
            for name in ('own_price','rival_price'):
                if row.get(name) is not None: known.add(round(float(row[name]),8))
        if d['arm']!=arm: continue
        calls+=1
        visible={round(float(row[name]),8) for row in canonical_rows(obs)
                 for name in ('own_price','rival_price') if row.get(name) is not None}
        for note in obs.get('own_notes',[]):
            tokens=re.findall(r'(?<![A-Za-z_])[-+]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',note['text'])
            for token in tokens:
                value=round(float(token),8)
                if value in known:
                    matches+=1
                    if value not in visible: historical_matches+=1
    return {'arm':arm,'calls':calls,'price_token_matches_in_displayed_notes':matches,
            'matches_not_in_displayed_price_row':historical_matches,
            'interpretation':'Repeated display counted repeatedly; lexical matches are not proof of copying.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--config',default='config/main.yaml')
    p.add_argument('--synthetic',action='store_true'); p.add_argument('--calls'); p.add_argument('--arm',default='R1')
    a=p.parse_args(); result=notes_check(a.calls,a.arm) if a.calls else audit(load_config(a.config,a.synthetic))
    print(json.dumps(result,indent=2))
