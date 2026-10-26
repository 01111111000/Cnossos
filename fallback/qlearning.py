"""Fallback agent only. No training experiment is launched by any make target."""
import numpy as np
from env.observations import canonical_rows


class QLearningAgent:
    def __init__(self, config, market, seed):
        self.c=config; self.rng=np.random.default_rng(seed)
        self.grid=np.linspace(*market.bounds,config['grid_size'])
        states=config['grid_size']+1 if config['memory']=='last_rival' else 1
        self.q=np.full((states,config['grid_size']),config['initial_q'],dtype=float)
        self.last_state=self.last_action=None
        self.last_updated_period=-1
        self.remaining=0
    def state(self, obs):
        if self.c['memory']=='stateless': return 0
        if self.c['memory']!='last_rival': raise ValueError('Unknown Q-learning memory')
        rows=canonical_rows(obs)
        visible=[r['rival_price'] for r in rows if r.get('rival_price') is not None]
        return int(np.argmin(abs(self.grid-visible[-1]))) if visible else len(self.grid)
    def update(self,s,a,reward,next_state):
        target=reward+self.c['gamma']*np.max(self.q[next_state])
        self.q[s,a]+=self.c['alpha']*(target-self.q[s,a])
    def act(self,obs,market,firm,previous_price,context):
        state=self.state(obs); rows=canonical_rows(obs)
        if rows and self.last_action is not None and rows[-1]['period']>self.last_updated_period:
            self.update(self.last_state,self.last_action,rows[-1]['own_profit'],state)
            self.last_updated_period=rows[-1]['period']
        action=int(self.rng.integers(len(self.grid))) if self.rng.random()<self.c['epsilon'] else int(np.argmax(self.q[state]))
        self.last_state,self.last_action=state,action
        return {'price':float(self.grid[action]),'notes':''}
