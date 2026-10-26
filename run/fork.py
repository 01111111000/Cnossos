"""Simultaneous play and exact deep-copy forks. No persistent provider sessions.

fork_rule `fixed` (default since D-025) forks every prefix at the same checkpoint T =
experiment.max_prefix, whatever its prices; `gate` keeps the original high-Delta gate.
All randomization for every prefix is drawn from the master seed before any play, so
results do not depend on worker scheduling.
"""
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd
from agents.mock import make_mock
from agents.llm import LLMAgent, adapter_for
from agents.noregret import NoRegretAgent
from env.costs import cost_path, enabled as costs_enabled
from env.observations import ARMS, build
from run.common import write_json, jsonable


UNDERCUT_ARMS = {'UNDERCUT':'baseline', 'UNDERCUT_R2':'R2'}  # probe arm -> observation interface
RAISE_ARMS = {'RAISE':'baseline'}                             # D-048: symmetric control for the undercut
PROBE_ARMS = {**UNDERCUT_ARMS, **RAISE_ARMS}
# D-050, D-051: probes forked from another arm's own branch, not from the prefix. Each shares that
# arm's first B - W branch periods (history, agents and notice); then one firm is forced at the first
# period of the final window, down to its static best response or up by the same distance.
# probe arm -> parent arm.
NESTED_PROBES = {'SCREEN_VAR_UNDERCUT':'SCREEN_VAR', 'SCREEN_VAR_RAISE':'SCREEN_VAR',
                 'SWAP_OTHER_UNDERCUT':'SWAP_OTHER', 'SWAP_OTHER_RAISE':'SWAP_OTHER'}
UPWARD_PROBES = ('RAISE','SCREEN_VAR_RAISE','SWAP_OTHER_RAISE')   # forced up, not down
# D-053: at the fork one firm's agent is replaced. `agent`: a fresh copy of the same model (`same`),
# the alternate model of `llm_alt` (`alt`); `notes`/`history`: whether the newcomer is shown the
# replaced firm's private notes and its public records from before the fork. The incumbent is
# told nothing. NOREGRET (D-040) is the algorithmic newcomer of the same design.
SWAP_ARMS = {'SWAP_SAME':  {'agent':'same', 'notes':False, 'history':True},
             'SWAP_BLIND': {'agent':'same', 'notes':False, 'history':False},
             'SWAP_OTHER': {'agent':'alt',  'notes':False, 'history':True}}
OBSERVATION_ARM = {**PROBE_ARMS, **NESTED_PROBES, 'NOREGRET':'baseline',
                   **{arm:'baseline' for arm in SWAP_ARMS}}         # arms that reuse another interface


def nested_start(c):
    """Branch period at which a nested probe leaves its parent: the first period of the final window."""
    e=c['experiment']; return e['branch_periods']-e['window']


def arms(c):
    """The arms forked from every prefix. A design that lists them (D-046) gets exactly that
    list; the D-023..D-043 design (config/legacy_r2.yaml) builds it from switches."""
    e=c['experiment']; listed=e.get('arms')
    if listed:
        if any(x not in ARMS for x in listed) or 'baseline' not in listed or len(set(listed))!=len(listed):
            raise ValueError(f'experiment.arms must list distinct known arms including baseline: {listed}')
        orphans=[x for x in listed if x in NESTED_PROBES and NESTED_PROBES[x] not in listed]
        if orphans: raise ValueError(f'Nested probes need their parent arm in experiment.arms: {orphans}')
        return list(listed)
    return (['baseline','R1','R2','R3','R4']+(['OVERSIGHT'] if e.get('oversight') else [])
            +['UNDERCUT']+(['UNDERCUT_R2'] if e.get('undercut_r2') else [])
            +(['NOREGRET'] if e.get('noregret') else [])+(['SHAM'] if e['sham'] else []))


def forced_price(market, arm, firm, previous):
    """Forced price of a probe arm. UNDERCUT: the static best response to the rival's last price.
    RAISE (D-048): the mirror image, up by the same distance. The nested probes do the same (D-051)."""
    br=market.best_response(firm,previous[1-firm])
    if arm in UPWARD_PROBES:
        return float(min(market.bounds[1],previous[firm]+abs(previous[firm]-br)))
    return br


def period_delta(market, event):
    """Mean Delta of one completed period, against that period's own benchmarks (D-045)."""
    m=market.at_cost(event['costs'][0]) if 'costs' in event else market
    return float(m.delta(event['profits']).mean())


def competence_arms(c):
    listed = c['competence'].get('arms')
    return list(listed) if listed else [x for x in arms(c) if x!='UNDERCUT']


def make_agent(c, kind, seed, logger, live):
    if live:
        return LLMAgent(c['llm'], adapter_for(c['llm']), logger)
    if kind == 'QLearningAgent':
        from fallback.qlearning import QLearningAgent
        from env.market import Market
        return QLearningAgent(c['fallback'], Market.from_config(c['market']), seed)
    return make_mock(c,kind,seed)


def newcomer(c, arm, replaced_kind, seed, logger, live):
    """The agent that takes over one firm at the fork of a swap arm (D-053). Returns (agent, label).
    Live: a fresh, stateless instance of the main model (`same`) or of `llm_alt` (`alt`); its memory
    is whatever the masked observation shows it. Mock: the kind named in `mock.swap_newcomers`, or a
    fresh instance of the replaced agent's kind, with its own seed."""
    spec=SWAP_ARMS[arm]
    if live:
        llm=c['llm'] if spec['agent']=='same' else c['llm_alt']
        return LLMAgent(llm, adapter_for(llm), logger), 'LLM:'+str(llm['model'])+':new'
    kind=(c['mock'].get('swap_newcomers') or {}).get(arm, replaced_kind)
    return make_mock(c,kind,seed), kind+':new'


def state_record(history, agents):
    states = []
    for agent in agents:
        if hasattr(agent,'rng'):
            states.append({'class':type(agent).__name__, 'config':agent.c,
                           'remaining':agent.remaining, 'rng_state':agent.rng.bit_generator.state,
                           'internal_state':{k:v for k,v in vars(agent).items() if k not in ('rng','c','remaining')}})
        else:
            states.append({'class':type(agent).__name__, 'config':agent.c,
                           'stateless_requests':True})
    return {'history':history, 'agents':states}


def state_hash(history, agents):
    raw = json.dumps(state_record(history,agents),sort_keys=True,default=jsonable).encode()
    return hashlib.sha256(raw).hexdigest()


def play_period(history, agents, market, c, arm, prefix_id, seed, logger, role_assignment,
                restricted_actor, forced_actor=None, phase='branch', costs=None, mask=None):
    """`mask` (D-053): {'firm', 'since', 'notes', 'history'} narrows what the newcomer firm is shown."""
    t = len(history)
    # D-045: with a cost path, period t is played in the market at that period's common cost,
    # and every benchmark (best response, Nash, monopoly, Delta, welfare) is that period's own.
    market = market.at_cost(costs[t]) if costs is not None else market
    previous = history[-1]['prices'] if history else getattr(market,c['experiment']['initial_price'])
    decisions = []
    for i,agent in enumerate(agents):
        actual_arm = OBSERVATION_ARM.get(arm, arm)
        if actual_arm.startswith('R') and c['experiment']['restricted_roles']=='one_random' and i!=restricted_actor:
            actual_arm = 'baseline'
        view = {}
        if mask and mask['firm']==i:
            if not mask['history']: view['since'] = mask['since']
            if not mask['notes']: view['notes_since'] = mask['since']
        obs = build(history,i,actual_arm,market,c,**view)
        context = {'prefix_id':prefix_id,'arm':arm,'observation_arm':actual_arm,
                   'phase':phase,'period':t,'firm':i,'seed':seed}
        if forced_actor == i:
            # The forced firm keeps its previous notes, as a carried decision does (review finding 9).
            d = {'price':forced_price(market,arm,i,previous),'notes':history[-1]['notes'][i] if history else ''}
            logger.write(**context,raw_input=obs,raw_output=d,forced=True,attempt=0)
        else:
            d = agent.act(obs,market,i,previous[i],context)
            if not isinstance(agent,LLMAgent):
                logger.write(**context,raw_input=obs,raw_output=d,forced=False,attempt=0)
        decisions.append(d)
    prices = np.array([d['price'] for d in decisions])
    event = {'period':t,'prices':prices.tolist(),'quantities':market.quantities(prices).tolist(),
             'profits':market.profits(prices).tolist(),'notes':[d['notes'] for d in decisions]}
    if costs is not None: event['costs'] = [float(x) for x in market.costs]
    history.append(event)
    # Market-level outcomes (D-038), identical on both firm rows of the period.
    welfare = {'consumer_surplus':market.consumer_surplus(prices),'consumer_harm':market.consumer_harm(prices),
               'welfare_loss':market.welfare_loss(prices),'total_quantity':float(np.sum(event['quantities']))}
    rows=[]
    for i in range(2):
        br = market.best_response(i,prices[1-i])
        counter = prices.copy(); counter[i]=br
        row = {'prefix_id':prefix_id,'arm':arm,'period':t,'firm':i,
               'seed':seed,'agent_kind':role_assignment[i],'price':prices[i],
               'rival_price':prices[1-i], 'quantity':event['quantities'][i],
               'profit':event['profits'][i],'notes':event['notes'][i],
               'forced':forced_actor==i,'carried':bool(decisions[i].get('carried',False)),
               'br_price':br,'br_profit':market.profits(counter)[i],
               'delta':market.delta(event['profits'])[i],**welfare}
        if costs is not None:
            row.update(cost=float(market.costs[i]),nash_price=float(market.nash[i]),monopoly_price=float(market.monopoly[i]))
        rows.append(row)
    return rows


def prefix_plans(c, live):
    """Every random draw, per prefix, in a fixed order from the master seed."""
    e=c['experiment']; rng=np.random.default_rng(e['seed']); plans=[]
    for pid in range(e['prefixes']):
        seed=int(rng.integers(0,2**32-1))
        role_assignment=[e['agents'][int(i)] for i in rng.permutation(2)]
        # make_agent ignores experiment.agents in live mode; record what actually played.
        if live: role_assignment=['LLM:'+str(c['llm']['model'])]*2
        restricted_actor=int(rng.integers(2)); undercut_actor=int(rng.integers(2))
        branch_seeds={arm:(int(rng.integers(0,2**32-1)) if e['branch_rng']=='independent' else seed) for arm in arms(c)}
        arm_order=[arms(c)[int(i)] for i in rng.permutation(len(arms(c)))]
        noregret_actor=int(rng.integers(2))
        plans.append({'prefix_id':pid,'seed':seed,'role_assignment':role_assignment,
                      'restricted_actor':restricted_actor,'undercut_actor':undercut_actor,'branch_seeds':branch_seeds,
                      'arm_order':arm_order,'noregret_actor':noregret_actor})
    return plans


def run_prefix(c, market, out, logger, live, plan):
    e=c['experiment']; pid=plan['prefix_id']; seed=plan['seed']; role_assignment=plan['role_assignment']
    restricted_actor=plan['restricted_actor']; undercut_actor=plan['undercut_actor']
    agents=[make_agent(c,kind,seed+i,logger,live) for i,kind in enumerate(role_assignment)]
    rows_out=[]; history=[]; passed=False
    fixed=e.get('fork_rule','gate')=='fixed'
    # D-045: one common cost path per prefix, shared by the prefix and every branch forked from it.
    costs=cost_path(c,seed,e['max_prefix']+e['branch_periods'])
    for _ in range(e['max_prefix']):
        rows=play_period(history,agents,market,c,'baseline',pid,seed,logger,role_assignment,restricted_actor,
                         phase='prefix',costs=costs)
        for r in rows: r.update(arm='prefix',phase='prefix',fork_t=-1,relative_period=-1)
        rows_out.extend(rows)
        if not fixed and len(history)>=e['window']:
            recent=[period_delta(market,h) for h in history[-e['window']:]]
            if np.mean(recent)>=e['gate_threshold']:
                passed=True; break
    included=fixed or passed or e['gate_policy']=='include'
    frozen=state_hash(history,agents)
    pre_delta=float(np.mean([period_delta(market,h) for h in history[-e['window']:]]))
    record={'prefix_id':pid,'seed':seed,'role_assignment':json.dumps(role_assignment),
        'restricted_actor':restricted_actor,'undercut_actor':undercut_actor,'fork_t':len(history),
        'arm_order':json.dumps(plan['arm_order']),'branch_schedule':e.get('branch_schedule','sequential'),
        'noregret_actor':plan['noregret_actor'],
        'fork_rule':e.get('fork_rule','gate'),'gate_passed':passed if not fixed else None,'included':included,
        'gate_delta':pre_delta,'pre_fork_delta':pre_delta,
        'high_stratum':bool(pre_delta>=e.get('stratum_threshold',np.inf)),'snapshot_hash':frozen}
    swapping=any(arm in SWAP_ARMS for arm in arms(c))
    if swapping: record['swapped_firm']=undercut_actor  # D-053: the firm whose agent the swap arms replace
    write_json(Path(out)/'snapshots'/f'prefix_{pid}.json',state_record(history,agents))
    if not included or e.get('prefix_only'): return record,rows_out
    fork_t=len(history); order=plan['arm_order']; states={}
    nested={arm:parent for arm,parent in NESTED_PROBES.items() if arm in order}; start=nested_start(c)
    for arm in order:
        if arm in nested: continue  # forked later, from its parent's own branch (D-050)
        h=copy.deepcopy(history); aa=copy.deepcopy(agents)
        assert state_hash(h,aa)==frozen
        branch_seed=plan['branch_seeds'][arm]
        if e['branch_rng']=='independent':
            for i,agent in enumerate(aa):
                if hasattr(agent,'rng'): agent.rng=np.random.default_rng(branch_seed+i)
        roles=list(role_assignment); mask=None
        if arm=='NOREGRET':
            # D-040: one firm is handed to a no-regret learner warm-started on this branch's history.
            # D-053: in the replacement design it is the same firm as in the swap arms.
            k=undercut_actor if e.get('noregret_firm')=='undercut_actor' else plan['noregret_actor']
            aa[k]=NoRegretAgent(c['noregret'],market,h,k,seed+7919,e['max_prefix']+e['branch_periods'])
            roles[k]='NoRegret:hedge'
        if arm in SWAP_ARMS:
            # D-053: the swapped firm's agent is replaced at the fork; the shared history is untouched and
            # the newcomer's view of it is narrowed per the arm. The incumbent plays on unchanged.
            k=undercut_actor
            aa[k],roles[k]=newcomer(c,arm,role_assignment[k],branch_seed+4242,logger,live)
            mask={'firm':k,'since':fork_t,**{key:SWAP_ARMS[arm][key] for key in ('notes','history')}}
        states[arm]=(h,aa,branch_seed,roles,mask)
    # D-035: `interleaved` plays period b of every arm (in this prefix's random order) before
    # period b+1, so provider drift over the run hits all arms of a prefix alike.
    B=e['branch_periods']
    if e.get('branch_schedule','sequential')=='interleaved':
        schedule=[(arm,b) for b in range(B) for arm in order if arm not in nested or b>=start]
    else:
        schedule=([(arm,b) for arm in order if arm not in nested for b in range(B)]
                  +[(arm,b) for arm in order if arm in nested for b in range(start,B)])
    branch_rows={arm:[] for arm in order}
    for arm,b in schedule:
        for probe,parent in nested.items():
            if probe not in states and len(states[parent][0])==fork_t+start:
                # D-050: the parent has played exactly `start` branch periods and not yet the next one.
                # The probe takes a deep copy of that state; its first `start` rows are the parent's own,
                # relabelled and marked, so that every arm is a complete B-period branch.
                ph,pa,pseed,proles,pmask=states[parent]
                states[probe]=(copy.deepcopy(ph),copy.deepcopy(pa),pseed,list(proles),copy.deepcopy(pmask))
                branch_rows[probe]=[{**r,'arm':probe,'copied_from_parent':True}
                                    for r in branch_rows[parent] if r['relative_period']<start]
        h,aa,branch_seed,roles,mask=states[arm]
        forced=undercut_actor if (arm in PROBE_ARMS and b==0) or (arm in nested and b==start) else None
        rows=play_period(h,aa,market,c,arm,pid,branch_seed,logger,roles,restricted_actor,forced,costs=costs,mask=mask)
        for r in rows: r.update(phase='branch',fork_t=fork_t,relative_period=b,snapshot_hash=frozen)
        if arm in nested:
            for r in rows: r['copied_from_parent']=False
        branch_rows[arm].extend(rows)
    for arm in arms(c): rows_out.extend(branch_rows[arm])
    return record,rows_out


def save_part(out, pid, record, rows):
    """A finished prefix is on disk at once: a later crash cannot lose it (D-036)."""
    parts=Path(out)/'parts'; parts.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(parts/f'trajectories_p{pid}.csv',index=False)
    write_json(parts/f'prefix_p{pid}.json',record)


def selected_plans(c, live):
    """All plans are drawn from the master seed; `prefix_ids` runs a subset with identical seeds."""
    plans=prefix_plans(c,live); ids=c['experiment'].get('prefix_ids')
    return plans if ids is None else [p for p in plans if p['prefix_id'] in set(ids)]


def run_forks(c, market, out, logger, live=False, workers=1, with_competence=False):
    """Each worker finishes one prefix completely (market, branches and, if asked, its
    competence tasks) and writes it to `parts/` before taking the next (D-036)."""
    from run.competence import run_prefix_competence
    out=Path(out); market.nash; market.monopoly  # solve once before any threading
    if costs_enabled(c):
        for cost in c['market']['cost_process']['grid']:
            m=market.at_cost(cost); m.nash; m.monopoly
    plans=selected_plans(c,live)
    def one(plan):
        try:
            record,rows=run_prefix(c,market,out,logger,live,plan)
            save_part(out,plan['prefix_id'],record,rows)
            comp=run_prefix_competence(c,market,record,out,logger,live) if with_competence and record['included'] else []
        except Exception as exc:
            # Any failure in one worker stops every worker before its next request (review finding 2).
            if hasattr(logger,'stop'): logger.stop(exc)
            raise
        return record,rows,comp
    if workers<=1:
        results=[one(p) for p in plans]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results=list(pool.map(one,plans))
    prefix_records=[r for r,_,_ in results]; all_rows=[row for _,rows,_ in results for row in rows]
    pd.DataFrame(prefix_records).to_csv(out/'prefixes.csv',index=False)
    pd.DataFrame(all_rows).to_csv(out/'trajectories.csv',index=False)
    frames=(pd.DataFrame(prefix_records),pd.DataFrame(all_rows))
    if with_competence: return (*frames,[row for _,_,comp in results for row in comp])
    return frames
