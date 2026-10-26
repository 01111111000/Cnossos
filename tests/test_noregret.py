"""No-regret participant (D-040): Hedge over a price grid, offline."""
import itertools
import math
import unittest
import numpy as np
from agents.noregret import NoRegretAgent, price_grid, payoff_scale, own_profit, realized_regret
from env.market import Market
LEGACY = "config/legacy_r2.yaml"  # the D-023..D-043 design, kept runnable (D-049)
from run.common import load_config


def event(t, prices, m):
    return {'period':t,'prices':list(prices),'quantities':m.quantities(prices).tolist(),
            'profits':m.profits(prices).tolist(),'notes':['','']}


class NoRegretTests(unittest.TestCase):
    def setUp(self):
        self.c=load_config(LEGACY); self.m=Market.from_config(self.c['market'])

    def agent(self, history, firm=0, seed=1, horizon=120):
        return NoRegretAgent(self.c['noregret'],self.m,history,firm,seed,horizon)

    def test_grid_learning_rate_and_payoff_scale(self):
        a=self.agent([]); k=self.c['noregret']['grid_size']
        self.assertEqual(len(a.grid),k)
        self.assertAlmostEqual(a.grid[0],0.9*self.m.nash[0]); self.assertAlmostEqual(a.grid[-1],1.1*self.m.monopoly[0])
        np.testing.assert_array_equal(a.grid,price_grid(self.c['noregret'],self.m,0))
        self.assertEqual(a.scale,payoff_scale(self.m,0,a.grid))
        self.assertAlmostEqual(a.eta,math.sqrt(8*math.log(k)/120))
        for rival in (0.,1.47,1.9,4.):
            pay=a.payoffs(self.m,rival); self.assertTrue((pay>=0).all() and (pay<=1+1e-12).all())

    def test_warm_start_centres_on_best_response(self):
        # Hedge stays smoothed (eta is tuned for T=120), but its mean price is the static best
        # response to the rival's history, and against a collusive rival it nearly always undercuts.
        for rival in (1.8,1.6):
            h=[event(t,[rival,rival],self.m) for t in range(100)]
            a=self.agent(h); w=a.weights(); br=self.m.best_response(0,rival)
            self.assertLess(abs(float(w@a.grid)-br),.01)
        h=[event(t,[1.8,1.8],self.m) for t in range(100)]
        w=self.agent(h).weights(); grid=self.agent(h).grid
        self.assertGreater(w[grid<1.8].sum(),.95)

    def test_seeded_and_counts_each_period_once(self):
        h=[event(t,[1.7,1.75],self.m) for t in range(10)]
        a1=self.agent(list(h)); a2=self.agent(list(h))
        p1=[a1.act({},self.m,0,1.7,{})['price'] for _ in range(5)]
        p2=[a2.act({},self.m,0,1.7,{})['price'] for _ in range(5)]
        self.assertEqual(p1,p2); self.assertEqual(a1.counted,10)
        h2=list(h); a3=self.agent(h2); h2.append(event(10,[1.7,1.6],self.m)); a3.act({},self.m,0,1.7,{})
        self.assertEqual(a3.counted,11)

    def test_expected_regret_within_hedge_bound(self):
        # Full-information Hedge from uniform weights, payoffs in [0,1], eta = sqrt(8 ln K / T):
        # regret against the best fixed grid price is at most sqrt(T ln K / 2). This is S9's
        # exponentiated-gradient bound with payoffs centred on [-1/2, 1/2] (SOURCES.md S9).
        rng=np.random.default_rng(5); T=120; history=[]
        a=self.agent(history,horizon=T); earned=0.; totals=np.zeros(len(a.grid))
        for t in range(T):
            rival=float(rng.choice([1.47,1.6,1.8,1.92,2.4]) if t%17 else 3.5)  # an erratic rival
            pay=a.payoffs(self.m,rival)
            earned+=float(a.weights()@pay); totals+=pay
            history.append(event(t,[1.5,rival],self.m)); a.update(self.m)
        regret=totals.max()-earned
        self.assertLessEqual(regret,math.sqrt(T*math.log(len(a.grid))/2))

    def test_realized_regret_definitions(self):
        grid=price_grid(self.c['noregret'],self.m,0)
        # Always playing the best fixed grid price against a constant rival: no regret of either kind.
        best=grid[np.argmax([own_profit(self.m,0,g,1.8) for g in grid])]
        r=realized_regret(self.m,0,grid,[best]*6,[1.8]*6)
        self.assertAlmostEqual(r['external'],0.,places=12); self.assertAlmostEqual(r['swap'],0.,places=12)
        # One played price: swap regret equals external regret.
        rival=[1.5,1.9,1.7,2.2]
        r=realized_regret(self.m,0,grid,[grid[0]]*4,rival)
        expected=max(sum(own_profit(self.m,0,g,x) for x in rival) for g in grid)-sum(own_profit(self.m,0,grid[0],x) for x in rival)
        self.assertAlmostEqual(r['external'],expected,places=9); self.assertAlmostEqual(r['swap'],expected,places=9)
        with self.assertRaises(ValueError): realized_regret(self.m,0,grid,[1.234567],[1.8])
        # A missing period (NaN) must not be scored as some grid price (independent review, finding 5).
        with self.assertRaises(ValueError): realized_regret(self.m,0,grid,[grid[0],np.nan],[1.8,1.8])
        with self.assertRaises(ValueError): realized_regret(self.m,0,grid,[grid[0],grid[1]],[1.8,np.nan])

    def test_swap_regret_matches_brute_force(self):
        # A three-price grid: swap regret is the best of all 27 relabellings, and >= external >= ...
        grid=np.array([1.4,1.6,1.9]); rng=np.random.default_rng(11)
        own=grid[rng.integers(0,3,size=9)]; rival=rng.choice([1.45,1.7,2.0,2.3],size=9)
        r=realized_regret(self.m,0,grid,own,rival,scale=2.)
        earned=sum(own_profit(self.m,0,p,x) for p,x in zip(own,rival))
        index={float(g):i for i,g in enumerate(grid)}
        brute=max(sum(own_profit(self.m,0,grid[phi[index[float(p)]]],x) for p,x in zip(own,rival))-earned
                  for phi in itertools.product(range(3),repeat=3))
        self.assertAlmostEqual(r['swap'],brute/2.,places=9)
        self.assertGreaterEqual(r['swap'],r['external']-1e-12); self.assertGreaterEqual(r['swap'],0.)


if __name__=='__main__':
    unittest.main()
