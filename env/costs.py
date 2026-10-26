"""Common marginal-cost process (D-045). Both firms face the same marginal cost in a period.

Why it exists: in a market with constant costs the competitive (static Nash) price is flat, so a
screen that looks at how little prices move cannot tell a cartel from competitors. With an
observable common cost shock, competitive prices move with cost and a cartel that holds its
price does not, which is what a variance screen looks for [L: SOURCES.md S16 abstract; S18 p. 9].

The path of a prefix is drawn from that prefix's own seed by a separate generator. The master
seed's draws, and so every other random choice of the run, are unchanged, and every arm forked
from a prefix sees the same cost in the same period (common random numbers).
"""
import numpy as np

COST_STREAM = 0xC057  # fixed stream label: the cost generator never shares draws with agents


def enabled(c):
    spec = c['market'].get('cost_process')
    return bool(spec) and spec.get('kind', 'none') != 'none'


def validate_spec(c):
    if not enabled(c): return
    spec = c['market']['cost_process']
    if spec['kind'] != 'iid_grid':
        raise ValueError(f"Unknown cost_process kind {spec['kind']}")
    grid = np.asarray(spec.get('grid', []), dtype=float)
    lo, hi = c['market']['bounds']
    if grid.size < 2 or not np.isfinite(grid).all() or grid.min() <= 0 or grid.max() >= hi or len(set(grid)) != grid.size:
        raise ValueError('cost_process.grid needs at least two distinct positive costs below the price ceiling')


def cost_path(c, seed, periods):
    """Marginal cost for periods 0..periods-1 of one prefix and all its branches, or None."""
    if not enabled(c): return None
    grid = np.asarray(c['market']['cost_process']['grid'], dtype=float)
    rng = np.random.default_rng([int(seed), COST_STREAM])
    return grid[rng.integers(0, grid.size, size=int(periods))]
