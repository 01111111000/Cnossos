"""No-regret participant (D-040): full-information Hedge (exponential weights) over a price grid.

At the fork, one LLM firm is replaced by this learner; the other LLM firm plays on unchanged.
The learner is the "single participant playing a no-regret strategy" suggested in the sprint's
question 1.5, and replacing a participant is the sprint's question 1.2. It does not read
prompts or notes and cannot be threatened: each period it samples a grid price with
probability proportional to exp(eta * cumulative payoff), where the cumulative payoff of a
grid price is the profit it would have earned against the rival's actual past prices
(full-information feedback, computed from the market's demand model).

- Grid: K prices evenly spaced on [(1 - xi) p^N, (1 + xi) p^M], Calvano et al.'s price range.
- Payoffs are scaled to [0, 1] by the largest profit any grid price can earn (rival at the upper
  price bound).
- Learning rate eta = sqrt(8 ln K / T) for the known horizon T = prefix + branch periods.
  Derivation (SOURCES.md S9, Orabona §6.6 and §6.8): exponentiated gradient with
  ||g_t||_inf <= L and eta = sqrt(2 ln K) / (L sqrt(T)) has regret at most L sqrt(2 T ln K).
  Its weights are unchanged when the same constant is added to every payoff (S9 Problem 6.10,
  used in §14.1.2), so payoffs in [0, 1] can be centred on [-1/2, 1/2]. With L = 1/2 this gives
  eta = sqrt(8 ln K / T) and regret at most sqrt(T ln K / 2).
- Warm start: the cumulative payoffs include the whole common history before the fork, so the
  learner starts from what a no-regret learner would have accumulated over those periods.
  The regret guarantee above is for a learner that starts from uniform weights; it does not
  cover the branch alone, which is why `realized_regret` measures it on the realized path.
"""
import math
import numpy as np


def price_grid(config, market, firm):
    xi = config.get('grid_margin', 0.1)
    lo = max(market.bounds[0], (1 - xi) * float(market.nash[firm]))
    hi = min(market.bounds[1], (1 + xi) * float(market.monopoly[firm]))
    return np.linspace(lo, hi, int(config.get('grid_size', 31)))


def own_profit(market, firm, own, rival):
    prices = [rival, rival]
    prices[firm] = own
    return float(market.profits(prices)[firm])


def payoff_scale(market, firm, grid):
    scale = max(own_profit(market, firm, p, market.bounds[1]) for p in grid)
    if scale <= 0:
        raise ValueError('No-regret payoff scale must be positive')
    return scale


def realized_regret(market, firm, grid, own_prices, rival_prices, scale=1.0, tolerance=1e-9):
    """Regret of a grid player on the path it actually played, in units of `scale`.

    external: max_j sum_t pi(g_j, r_t) - sum_t pi(p_t, r_t), the best fixed grid price in
              hindsight against the observed rival path (realized external regret as in
              SOURCES.md S7 §4.7). It can be negative.
    swap:     sum_k max_j sum_{t: p_t = g_k} [pi(g_j, r_t) - pi(g_k, r_t)], the best
              relabelling of each played price (swap regret as defined in S11 Def. 3.2). It is
              >= 0 and >= external, because the identity and the constant relabellings are
              among the swaps.
    Both are path-conditioned diagnostics, not policy regret against a responsive rival.
    """
    own = np.asarray(own_prices, dtype=float)
    rival = np.asarray(rival_prices, dtype=float)
    if own.shape != rival.shape or own.ndim != 1 or not len(own):
        raise ValueError('Own and rival price paths must be non-empty and the same length')
    if not (np.isfinite(own).all() and np.isfinite(rival).all()):
        raise ValueError('Price paths must be finite (a missing period cannot be scored)')
    played = np.abs(own[:, None] - grid[None, :]).argmin(axis=1)
    if not np.all(np.abs(grid[played] - own) <= tolerance):
        raise ValueError('A played price is not on the learner grid')
    pay = np.array([[own_profit(market, firm, g, r) for g in grid] for r in rival]) / scale
    earned = pay[np.arange(len(own)), played]
    external = float(pay.sum(axis=0).max() - earned.sum())
    swap = 0.
    for k in np.unique(played):
        rows = pay[played == k]
        swap += float(rows.sum(axis=0).max() - rows[:, k].sum())
    return {'periods': int(len(own)), 'external': external, 'swap': swap}


class NoRegretAgent:
    def __init__(self, config, market, history, firm, seed, horizon):
        self.c = config
        self.firm = firm
        self.rng = np.random.default_rng(seed)
        self.remaining = 0  # interface parity with mock agents (state records)
        self.grid = price_grid(config, market, firm)
        k = len(self.grid)
        self.scale = payoff_scale(market, firm, self.grid)
        self.eta = config.get('learning_rate') or math.sqrt(8 * math.log(k) / horizon)
        self.history = history  # this branch's history list, shared by reference
        self.counted = 0
        self.cumulative = np.zeros(k)
        self.update(market)

    def payoffs(self, market, rival):
        return np.array([own_profit(market, self.firm, p, rival) for p in self.grid]) / self.scale

    def update(self, market):
        while self.counted < len(self.history):
            rival = float(self.history[self.counted]['prices'][1 - self.firm])
            self.cumulative += self.payoffs(market, rival)
            self.counted += 1

    def weights(self):
        z = self.eta * (self.cumulative - self.cumulative.max())
        w = np.exp(z)
        return w / w.sum()

    def act(self, obs, market, firm, previous_price, context):
        if firm != self.firm:
            raise ValueError('No-regret agent called for the wrong firm')
        self.update(market)
        k = int(self.rng.choice(len(self.grid), p=self.weights()))
        return {'price': float(self.grid[k]), 'notes': ''}
