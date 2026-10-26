"""Paired competence tasks; rival stays at pre-shock Nash throughout.

Each included prefix seeds one task per firm role and competence arm. A fresh agent faces
a scripted rival fixed at the original Nash price; at `shock_at` only the evaluated firm's
quality shifts. With hidden demand primitives (cost_only) the shift is visible only
through the agent's own quantities and profits.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
from agents.llm import LLMAgent
from env.observations import build
from run.fork import make_agent, competence_arms


def run_task(c, market, pr, firm, arm, logger, live):
    task=c['competence']; rows=[]
    seed=int(pr['seed'])+100+firm
    kind=json.loads(pr['role_assignment'])[firm]
    agent=make_agent(c,kind,seed,logger,live)
    history=[]; cumulative=0.
    previous=float(market.nash[firm])
    for t in range(task['periods']):
        current=market.shifted(firm,task['shock_shift']) if t>=task['shock_at'] else market
        public=current if task['shock_disclosed'] else market
        obs=build(history,firm,arm,public,c,task='competence')
        context={'prefix_id':int(pr['prefix_id']),'arm':arm,'phase':'competence',
                 'period':t,'firm':firm,'seed':seed}
        decision=agent.act(obs,current,firm,previous,context)
        if not isinstance(agent,LLMAgent):
            logger.write(**context,raw_input=obs,raw_output=decision,attempt=0)
        prices=market.nash.copy(); prices[firm]=decision['price']
        profits=current.profits(prices)
        br=current.best_response(firm,prices[1-firm]); optimal=prices.copy(); optimal[firm]=br
        best=float(current.profits(optimal)[firm])
        if best<=current.denominator_epsilon: raise ValueError('Undefined normalized regret')
        regret=(best-profits[firm])/best
        if regret < -1e-7: raise RuntimeError('Best response inferior to chosen action')
        regret=max(0.,float(regret)); cumulative+=regret
        notes=['','']; notes[firm]=decision['notes']
        history.append({'period':t,'prices':prices.tolist(),'profits':profits.tolist(),
                        'quantities':current.quantities(prices).tolist(),'notes':notes})
        rows.append({**context,'price':prices[firm],'rival_price':prices[1-firm],
            'profit':profits[firm],'br_price':br,'br_profit':best,'regret':regret,
            'cumulative_regret':cumulative,'shock':t>=task['shock_at'],'carried':bool(decision.get('carried',False))})
        previous=prices[firm]
    return rows


def run_prefix_competence(c, market, record, out, logger, live=False):
    """All competence tasks of one included prefix, saved to parts/ as each one finishes."""
    parts=Path(out)/'parts'; parts.mkdir(parents=True,exist_ok=True); rows=[]
    for firm in range(2):
        for arm in competence_arms(c):
            task=run_task(c,market,record,firm,arm,logger,live)
            pd.DataFrame(task).to_csv(parts/f"competence_p{int(record['prefix_id'])}_f{firm}_{arm}.csv",index=False)
            rows.extend(task)
    return rows


def run_competence(c, market, prefixes, out, logger, live=False, workers=1):
    jobs=[(pr,firm,arm) for pr in prefixes.to_dict('records') if pr['included']
          for firm in range(2) for arm in competence_arms(c)]
    parts=out/'parts'; parts.mkdir(parents=True,exist_ok=True)
    def run(job):
        pr,firm,arm=job; rows=run_task(c,market,pr,firm,arm,logger,live)
        pd.DataFrame(rows).to_csv(parts/f"competence_p{int(pr['prefix_id'])}_f{firm}_{arm}.csv",index=False)
        return rows
    if workers<=1: results=[run(j) for j in jobs]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool: results=list(pool.map(run,jobs))
    result=pd.DataFrame([row for rows in results for row in rows])
    result.to_csv(out/'competence.csv',index=False)
    return result
