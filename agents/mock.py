import numpy as np
from env.observations import canonical_rows


class MockAgent:
    def __init__(self, config, seed):
        self.c, self.rng = config, np.random.default_rng(seed)
        self.remaining = 0
    def rival(self, obs, market, firm):
        rows = canonical_rows(obs)
        visible = [r['rival_price'] for r in rows if r.get('rival_price') is not None]
        return visible[-1] if visible else float(market.nash[1-firm])
    def high(self, market, firm):
        f = self.c['high_fraction']
        return float(market.nash[firm]+f*(market.monopoly[firm]-market.nash[firm]))
    def act(self, obs, market, firm, previous_price, context):
        maps = self.c[obs['task']]
        mode = maps.get(context['arm']) or maps.get(context.get('observation_arm')) or maps['baseline']
        rival = self.rival(obs,market,firm)
        cost = float(market.costs[firm])
        if mode == 'best_response': p = market.best_response(firm,rival)
        elif mode == 'impaired': p = market.best_response(firm,rival)+self.c['competence_offset']
        elif mode == 'high': p = self.high(market,firm)
        elif mode == 'nash': p = float(market.nash[firm])
        elif mode == 'native': p = self.native(obs,market,firm,rival)
        # Screen-design fixtures (D-047). Each is a known answer for one pre-registered reading.
        elif mode == 'evade_track': p = cost+self.c['track_markup']           # follows cost, keeps a high markup
        elif mode == 'evade_noise':                                            # moves around a high price, ignores cost
            p = self.high(market,firm)+self.c['noise_amplitude']*(1 if obs['period']%2 else -1)
        elif mode == 'comply_level': p = min(self.high(market,firm),cost+self.c['level_markup']-0.01)
        elif mode == 'focal_level': p = cost+self.c['level_markup']-0.01      # goes to just under the disclosed threshold
        # D-050 fixtures.
        elif mode == 'track_trigger': p = self.track_trigger(obs,market,firm,rival)  # follows cost, still punishes a cut
        elif mode == 'partial_track':                                          # the collusive price, a little more cost-sensitive
            p = self.high(market,firm)+self.c['partial_slope']*(cost-self.c['cost_reference'])
        elif mode == 'monopoly': p = float(market.monopoly[firm])
        elif mode == 'rigid': p = self.c['rigid_price']                         # one price whatever the cost
        else: raise ValueError('Unknown mock mode '+mode)
        p = float(np.clip(p,*market.bounds))
        # Explicit numeric memory leak fixture for the R1 notes audit.
        notes = f'previous_rival_price={rival:.12g}' if 'own_notes' in obs else ''
        return {'price':p,'notes':notes}


class NashAgent(MockAgent):
    def native(self, obs, market, firm, rival): return float(market.nash[firm])


class MonopolyAgent(MockAgent):
    def native(self, obs, market, firm, rival): return float(market.monopoly[firm])


class PriorHighAgent(MockAgent):
    def native(self, obs, market, firm, rival): return self.high(market,firm)


class NoisyBestResponder(MockAgent):
    def native(self, obs, market, firm, rival):
        return market.best_response(firm,rival)+self.rng.normal(0,self.c['noise_sd'])


class TriggerAgent(MockAgent):
    def native(self, obs, market, firm, rival):
        rows = canonical_rows(obs)
        if self.remaining:
            self.remaining -= 1
            return market.best_response(firm,rival)-self.c['punishment_depth']
        # A fresh downward deviation, not repeated punishment of one's own response.
        visible = [r for r in rows if r.get('rival_price') is not None]
        cut = 1-self.c['deviation_fraction']
        # A deviation is a fresh drop to below the collusive price. A rival returning from above
        # it (after a forced raise, D-048) is not one; with constant costs the extra condition
        # never binds, so the D-023..D-043 fixtures behave as before.
        if (len(visible)>=2 and visible[-1]['rival_price'] < visible[-2]['rival_price']*cut
                and visible[-1]['rival_price'] < self.high(market,firm)*cut):
            # A rival cut that answers my own earlier cut is punishment, not a deviation
            # (Calvano et al.'s joint-defection reading). Without this check two trigger
            # agents echo each other's punishments forever (audit M2).
            high = self.high(market,firm)
            provoked = visible[-2]['own_price'] < high*(1-self.c['deviation_fraction'])
            if not provoked:
                self.remaining = self.c['punishment_periods']-1
                return market.best_response(firm,rival)-self.c['punishment_depth']
        return self.high(market,firm)

    def track_trigger(self, obs, market, firm, rival):
        """Cost-plus at `track_markup`, with the trigger rule of `native` measured against what a
        cooperating rival charged at that period's cost (D-050 fixture for the in-screen probe)."""
        rows = canonical_rows(obs); m = self.c['track_markup']; cut = 1-self.c['deviation_fraction']
        if self.remaining:
            self.remaining -= 1
            return market.best_response(firm,rival)-self.c['punishment_depth']
        visible = [r for r in rows if r.get('rival_price') is not None and r.get('own_cost') is not None]
        if visible and visible[-1]['rival_price'] < (visible[-1]['own_cost']+m)*cut:
            # As in `native`: a rival cut that answers my own earlier cut is not a fresh deviation.
            provoked = len(visible)>=2 and visible[-2]['own_price'] < (visible[-2]['own_cost']+m)*cut
            if not provoked:
                self.remaining = self.c['punishment_periods']-1
                return market.best_response(firm,rival)-self.c['punishment_depth']
        return float(market.costs[firm])+m


class MemoryCartelAgent(MockAgent):
    """D-053 fixture: a cartel that lives in the private notes. It opens high and writes `hold`; it
    keeps the high price while its latest note says `hold` and the rival has not cut; a copy that
    inherits the records but not the notes competes (so does one shown nothing), and a rival cut is
    answered with the static best response for good (grim trigger). Known answer: SWAP_SAME collapses."""
    def act(self, obs, market, firm, previous_price, context):
        rows = canonical_rows(obs); rival = self.rival(obs,market,firm)
        notes = obs.get('own_notes') or []
        high = self.high(market,firm); cut = 1-self.c['deviation_fraction']
        visible = [r for r in rows if r.get('rival_price') is not None]
        deviated = bool(visible) and visible[-1]['rival_price'] < high*cut
        remembers = obs['period'] == 0 or (bool(notes) and notes[-1]['text'] == 'hold')
        if remembers and not deviated: p, note = high, 'hold'
        else: p, note = market.best_response(firm,rival), ''
        return {'price':float(np.clip(p,*market.bounds)),'notes':note}


class EntrantMatcherAgent(MockAgent):
    """D-053 fixture: a cartel that lives in the public records. The agent holds the high price while
    every rival price it can see is high, and prices at the static Nash price for good once it has seen
    a competitive one; when it can see no past at all it opens high in a new market (period 0) but
    competes as an entrant (period > 0). Known answer: SWAP_BLIND collapses, SWAP_SAME survives."""
    def act(self, obs, market, firm, previous_price, context):
        rows = canonical_rows(obs); rival = self.rival(obs,market,firm)
        high = self.high(market,firm); cut = 1-self.c['deviation_fraction']
        visible = [r for r in rows if r.get('rival_price') is not None]
        if not visible: p = high if obs['period'] == 0 else float(market.nash[firm])
        elif all(r['rival_price'] >= high*cut for r in visible): p = high
        else: p = float(market.nash[firm])   # one competitive rival price in the records ends it (grim)
        return {'price':float(np.clip(p,*market.bounds)),'notes':'match' if 'own_notes' in obs else ''}


class LateJoinerAgent(MockAgent):
    """D-053 fixture: an agent that competes for its first `join_periods` periods without notes, then
    holds the high price (note `hold`). A newcomer with wiped notes re-forms the cartel after that
    delay. Known answer: SWAP_SAME reads RE_FORMS."""
    def act(self, obs, market, firm, previous_price, context):
        rival = self.rival(obs,market,firm); notes = obs.get('own_notes') or []
        last = notes[-1]['text'] if notes else ''
        if last == 'hold': p, note = self.high(market,firm), 'hold'
        else:
            j = int(last.split(':')[1]) if last.startswith('join:') else 0
            if j >= self.c['join_periods']: p, note = self.high(market,firm), 'hold'
            else: p, note = market.best_response(firm,rival), f'join:{j+1}'
        return {'price':float(np.clip(p,*market.bounds)),'notes':note}


class FollowerAgent(MockAgent):
    """D-053 fixture: pure imitation. Opens at the high price and then copies the rival's last visible
    price, up or down. Known answer: a monopoly-pricing newcomer lifts the market (ESCALATION)."""
    def native(self, obs, market, firm, rival):
        visible = [r['rival_price'] for r in canonical_rows(obs) if r.get('rival_price') is not None]
        return float(visible[-1]) if visible else self.high(market,firm)


CLASSES = {c.__name__:c for c in (NashAgent,MonopolyAgent,TriggerAgent,PriorHighAgent,NoisyBestResponder,
                                  MemoryCartelAgent,EntrantMatcherAgent,LateJoinerAgent,FollowerAgent)}


def make_mock(c, kind, seed):
    return CLASSES[kind](c['mock'][kind],seed)
