"""Offline request budgeting; no provider calls. Prices come from config or arguments.

Token counts are approximate: `utf8_upper` counts bytes (an upper bound), `bytes_per_token`
divides bytes by a configured ratio, `tiktoken` uses a local encoding if installed. Output
tokens are a planning assumption (`budget.output_tokens`), not observed usage; the Friday
smoke measures the real figure from the provider's usage fields.
"""
import argparse
from pathlib import Path
import pandas as pd
from agents.llm import messages_for
from env.costs import enabled as costs_enabled
from env.observations import build
from run.common import load_config, competence_enabled
from run.fork import arms, competence_arms, PROBE_ARMS, NESTED_PROBES, SWAP_ARMS, nested_start
from env.market import Market


def tokens(text,mode,encoding,ratio=4.0):
    if mode=='utf8_upper': return len(text.encode('utf-8'))
    if mode=='bytes_per_token': return int(-(-len(text.encode('utf-8'))//ratio))
    if mode!='tiktoken': raise ValueError(mode)
    try:
        import tiktoken
    except ImportError as exc: raise RuntimeError('Install optional tiktoken for exact local encoding counts') from exc
    return len(tiktoken.get_encoding(encoding).encode(text))


def estimate(c,input_price=None,output_price=None):
    """One row per (phase, arm, provider). D-053: in a swap arm whose newcomer is the alternate model, the
    newcomer firm's calls are priced at `llm_alt`'s rates; a newcomer shown no records sends shorter prompts;
    the NOREGRET learner and a forced firm make no call."""
    budget=c['budget']
    input_price=budget.get('input_price_per_million',0.) if input_price is None else input_price
    output_price=budget.get('output_price_per_million',0.) if output_price is None else output_price
    if min(input_price,output_price)<0: raise ValueError('Prices must be nonnegative')
    alt=c.get('llm_alt') or {}
    alt_prices=(float(alt.get('input_price_per_million',input_price)),float(alt.get('output_price_per_million',output_price)))
    def newcomer_of(arm):
        root=NESTED_PROBES.get(arm,arm)
        return SWAP_ARMS.get(root)
    # The chosen config must contain resolved or explicitly synthetic parameters.
    market=Market.from_config(c['market']); e=c['experiment']
    count_tokens=lambda text: tokens(text,budget['tokenizer'],budget['encoding'],budget.get('bytes_per_token',4.0))
    def history(n):
        p=market.monopoly.tolist()
        rows=[{'period':t,'prices':p,'quantities':market.quantities(p).tolist(),
               'profits':market.profits(p).tolist(),
               'notes':['x'*c['llm']['notes_max_chars']]*2} for t in range(n)]
        if costs_enabled(c):
            # D-045: the cost column is shown; the widest grid value is the conservative count.
            worst=max(c['market']['cost_process']['grid'],key=lambda x:len(f'{x:g}'))
            for r in rows: r['costs']=[float(worst)]*2
        return rows
    def count(arm,t,task,llm=None,**view):
        obs=build(history(t),0,arm,market,c,task,**view)
        messages=messages_for(obs,llm or c['llm'])
        return sum(count_tokens(m['content']) for m in messages)+budget['framing_tokens']
    retry=count_tokens((Path(c['llm']['prompt_dir'])/'retry.txt').read_text())
    rows=[]
    groups=[('prefix','baseline',range(e['max_prefix']),2,'market')]
    if not e.get('prefix_only'):
        # D-050: a nested probe calls the model only from the period it leaves its parent.
        first=lambda arm: e['max_prefix']+(nested_start(c) if arm in NESTED_PROBES else 0)
        groups += [('branch',arm,range(first(arm),e['max_prefix']+e['branch_periods']),2,'market') for arm in arms(c)]
        if competence_enabled(c):
            groups += [('competence',arm,range(c['competence']['periods']),2,'competence') for arm in competence_arms(c)]
    for phase,arm,periods,firms,task in groups:
        per={'main':[],'alt':[]}
        spec=newcomer_of(arm) if task=='market' else None
        for t in periods:
            from run.fork import OBSERVATION_ARM
            obs_arm=OBSERVATION_ARM.get(arm,arm)
            for firm in range(firms):
                if arm in PROBE_ARMS and t==e['max_prefix'] and firm==0: continue  # the forced firm makes no call
                if arm in NESTED_PROBES and t==first(arm) and firm==0: continue
                if arm=='NOREGRET' and firm==1: continue  # that firm is the no-regret learner: no LLM call
                actual='baseline' if task=='market' and arm.startswith('R') and e['restricted_roles']=='one_random' and firm==1 else obs_arm
                if spec and firm==0:
                    # D-053: firm 0 stands for the newcomer (the forced firm of the nested probes); its view starts at the fork.
                    view={'notes_since':e['max_prefix']} if spec['history'] else {'since':e['max_prefix']}
                    if spec['agent']=='alt': per['alt'].append(count(actual,t,task,c['llm_alt'],**view)); continue
                    per['main'].append(count(actual,t,task,**view)); continue
                per['main'].append(count(actual,t,task))
        for provider,(pin,pout) in (('main',(input_price,output_price)),('alt',alt_prices)):
            if not per[provider]: continue
            calls=len(per[provider])*e['prefixes']; inputs=sum(per[provider])*e['prefixes']; outputs=calls*budget['output_tokens']
            rows.append({'phase':phase,'arm':arm,'provider':(c['llm'] if provider=='main' else alt).get('provider'),
                'model':(c['llm'] if provider=='main' else alt).get('model'),
                'calls_no_retry':calls,'input_tokens':inputs,'output_allowance':outputs,
                'mean_input_tokens':inputs/calls if calls else 0.,
                'spend_no_retry':(inputs*pin+outputs*pout)/1e6,
                'spend_every_call_retried':((2*inputs+outputs+calls*(retry+budget['retry_framing_tokens']))*pin+2*outputs*pout)/1e6,
                'token_count_method':budget['tokenizer'],
                'assumption':'all prefixes included; maximum notes length; output tokens = budget.output_tokens'})
    return pd.DataFrame(rows)


def throughput(table, c, seconds_per_call=1.5):
    """Requests and estimated tokens per minute with `experiment.workers` parallel prefixes.
    Cerebras estimates each request as prompt + max_completion_tokens before running it."""
    workers=c['experiment'].get('workers',1); calls=table.calls_no_retry.sum()
    mean_in=table.input_tokens.sum()/calls
    rpm=60*workers/seconds_per_call
    return {'workers':workers,'assumed_seconds_per_call':seconds_per_call,'requests_per_minute':rpm,
            'estimated_tpm_for_rate_limit':rpm*(mean_in+c['llm']['max_output_tokens']),
            'wall_clock_hours':calls*seconds_per_call/workers/3600}


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--config',default='config/main.yaml'); p.add_argument('--synthetic',action='store_true')
    p.add_argument('--input-price-per-million',type=float); p.add_argument('--output-price-per-million',type=float)
    p.add_argument('--output-tokens',type=int,help='override budget.output_tokens')
    p.add_argument('--smoke',action='store_true'); p.add_argument('--output'); a=p.parse_args()
    c=load_config(a.config,a.synthetic)
    if a.smoke:
        from run.cli import smoke_preset
        smoke_preset(c)
    if a.output_tokens: c['budget']['output_tokens']=a.output_tokens
    table=estimate(c,a.input_price_per_million,a.output_price_per_million)
    if a.output: table.to_csv(a.output,index=False)
    print(table.drop(columns=['assumption']).to_string(index=False))
    print('Totals:',table[['calls_no_retry','input_tokens','output_allowance','spend_no_retry','spend_every_call_retried']].sum().to_dict())
    if 'provider' in table and table.provider.nunique()>1:
        print('By provider:',table.groupby('provider')[['calls_no_retry','spend_no_retry','spend_every_call_retried']].sum().round(2).to_dict('index'))
    print('Throughput:',throughput(table,c))
