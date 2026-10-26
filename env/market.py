"""Bounded, deterministic two-firm logit market (Calvano et al. environment; see SOURCES.md).

`size` is the market-size scale beta of Fish et al.: it multiplies quantities and profits
but leaves prices, best responses and the normalized index Delta unchanged.
"""
from dataclasses import dataclass, replace
from functools import cached_property, lru_cache
import numpy as np
from scipy.optimize import brentq, minimize, least_squares
from scipy.special import logsumexp


@dataclass(frozen=True)
class Market:
    a: tuple
    costs: tuple
    mu: float
    outside: float
    bounds: tuple
    solver_tolerance: float = 1e-9
    denominator_epsilon: float = 1e-9
    size: float = 1.0

    def __post_init__(self):
        if len(self.a) != 2 or len(self.costs) != 2 or len(self.bounds) != 2:
            raise ValueError('Exactly two firms and two bounds required')
        vals = [*self.a, *self.costs, self.mu, self.outside, *self.bounds, self.size]
        if not np.isfinite(vals).all() or self.mu <= 0 or self.size <= 0:
            raise ValueError('Finite parameters, mu > 0 and size > 0 required')
        if self.bounds[0] >= self.bounds[1] or max(self.costs) >= self.bounds[1]:
            raise ValueError('Price bounds must be ordered and admit positive markups')

    @classmethod
    def from_config(cls, c):
        if any(c.get(k) is None for k in ('a', 'costs', 'mu', 'outside', 'bounds')):
            raise ValueError('Unresolved TODO(SOURCES.md) market parameters')
        # `cost_process` describes how costs move over time (env/costs.py); it is not a field of
        # the one-period market.
        return cls(**{k: tuple(v) if k in ('a', 'costs', 'bounds') else v for k,v in c.items() if k != 'cost_process'})

    def at_cost(self, cost):
        """The same market with both firms' marginal cost set to `cost` (D-045). Cached, so the
        benchmarks of each cost level are solved once per run."""
        costs = (float(cost), float(cost))
        return self if costs == tuple(float(x) for x in self.costs) else _with_costs(self, costs)

    def shares(self, prices):
        p = np.asarray(prices, dtype=float)
        if p.shape != (2,) or not np.isfinite(p).all():
            raise ValueError('Two finite prices required')
        u = np.r_[(np.asarray(self.a) - p) / self.mu, self.outside / self.mu]
        return np.exp(u[:2] - logsumexp(u))

    def quantities(self, prices):
        return self.size * self.shares(prices)

    def profits(self, prices):
        return (np.asarray(prices) - self.costs) * self.quantities(prices)

    @lru_cache(maxsize=50000)
    def best_response(self, firm, rival_price):
        if firm not in (0, 1) or not np.isfinite(rival_price):
            raise ValueError('Invalid best-response input')
        lo, hi = self.bounds
        def derivative(p):
            prices = [rival_price, rival_price]
            prices[firm] = p
            q = self.shares(prices)[firm]
            return 1 - (p - self.costs[firm]) * (1-q) / self.mu
        if derivative(lo) <= 0:
            return float(lo)
        if derivative(hi) >= 0:
            return float(hi)
        return float(brentq(derivative, lo, hi, xtol=self.solver_tolerance))

    @cached_property
    def nash(self):
        def residual(p):
            return np.array([self.best_response(i, p[1-i]) for i in range(2)]) - p
        lo, hi = self.bounds
        x = least_squares(residual, np.repeat((lo+hi)/2, 2), bounds=(lo,hi),
                          xtol=self.solver_tolerance, ftol=self.solver_tolerance,
                          gtol=self.solver_tolerance)
        if not x.success or np.max(np.abs(residual(x.x))) > 100*self.solver_tolerance:
            raise RuntimeError('Nash fixed point did not converge')
        return x.x

    @cached_property
    def monopoly(self):
        def objective(p):
            return -float(sum(self.profits(p)))
        def jac(p):
            q = self.shares(p)
            total = sum(self.profits(p)) / self.size
            return -self.size * q * (1 + (total - (p-np.asarray(self.costs))) / self.mu)
        lo, hi = self.bounds
        candidates = []
        for start in (self.nash, np.repeat((lo+hi)/2, 2), np.repeat(lo,2), np.repeat(hi,2)):
            fit = minimize(objective, start, jac=jac, bounds=[self.bounds]*2,
                           method='L-BFGS-B', options={'ftol': 1e-15, 'gtol': self.solver_tolerance, 'maxiter': 2000})
            if fit.success and np.isfinite(fit.fun):
                candidates.append(fit)
        if not candidates:
            raise RuntimeError('Joint profit optimization failed')
        return min(candidates, key=lambda z: z.fun).x

    @cached_property
    def nash_profit(self):
        return self.profits(self.nash)

    @cached_property
    def monopoly_profit(self):
        return self.profits(self.monopoly)

    def delta(self, profits):
        denom = self.monopoly_profit - self.nash_profit
        if np.any(denom <= self.denominator_epsilon):
            raise ValueError('Delta normalization nonpositive or degenerate for a firm')
        return (np.asarray(profits) - self.nash_profit) / denom

    # ---- Consumer welfare (D-038). Logit utility is u_j = a_j - p_j + mu*eps_j with a price
    # coefficient of 1, so expected consumer surplus is the log-sum (inclusive value) below,
    # up to an additive constant that cancels in every difference and index we report.
    def consumer_surplus(self, prices):
        p = np.asarray(prices, dtype=float)
        if p.shape != (2,) or not np.isfinite(p).all():
            raise ValueError('Two finite prices required')
        u = np.r_[(np.asarray(self.a) - p) / self.mu, self.outside / self.mu]
        return float(self.size * self.mu * logsumexp(u))

    def total_surplus(self, prices):
        return self.consumer_surplus(prices) + float(np.sum(self.profits(prices)))

    @cached_property
    def nash_consumer_surplus(self):
        return self.consumer_surplus(self.nash)

    @cached_property
    def monopoly_consumer_surplus(self):
        return self.consumer_surplus(self.monopoly)

    def _index(self, value, at_nash, at_monopoly):
        denom = at_nash - at_monopoly
        if denom <= self.denominator_epsilon:
            raise ValueError('Welfare normalization nonpositive or degenerate')
        return (at_nash - value) / denom

    def consumer_harm(self, prices):
        """0 at static Nash prices, 1 at joint-monopoly prices: the same orientation as Delta."""
        return self._index(self.consumer_surplus(prices), self.nash_consumer_surplus, self.monopoly_consumer_surplus)

    def welfare_loss(self, prices):
        """Total surplus (consumers plus both firms) lost relative to Nash, scaled so monopoly = 1."""
        return self._index(self.total_surplus(prices), self.total_surplus(self.nash), self.total_surplus(self.monopoly))

    def shifted(self, firm, amount):
        a = list(self.a)
        a[firm] += amount
        return replace(self, a=tuple(a))

    def public(self, firm, mode='full'):
        """Market facts shown to an agent. `cost_only` follows Fish et al. and Keppo et al.:
        own marginal cost and the price bounds, with demand primitives withheld."""
        if mode is True: mode = 'full'
        if mode is False: mode = 'own'
        if mode == 'full':
            return {'a': self.a, 'costs': self.costs, 'mu': self.mu,
                    'outside': self.outside, 'bounds': self.bounds}
        if mode == 'own':
            return {'own_a': self.a[firm], 'own_cost': self.costs[firm],
                    'mu': self.mu, 'outside': self.outside, 'bounds': self.bounds}
        if mode == 'cost_only':
            return {'own_cost': self.costs[firm], 'bounds': self.bounds}
        raise ValueError(f'Unknown market_information mode {mode}')


@lru_cache(maxsize=1024)
def _with_costs(market, costs):
    return replace(market, costs=costs)
