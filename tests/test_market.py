import unittest
import itertools
import numpy as np
from scipy.optimize import differential_evolution, minimize_scalar
from env.market import Market
LEGACY = "config/legacy_r2.yaml"  # the D-023..D-043 design, kept runnable (D-049)
from run.common import load_config


class MarketTests(unittest.TestCase):
    def setUp(self): self.m=Market.from_config(load_config(LEGACY,synthetic=True)['market'])
    def test_quantities_match_formula(self):
        p=np.array([1.2,1.7]); w=np.exp((np.array(self.m.a)-p)/self.m.mu)
        np.testing.assert_allclose(self.m.quantities(p),w/(w.sum()+np.exp(self.m.outside/self.m.mu)))
    def test_nash_fixed_point(self):
        np.testing.assert_allclose([self.m.best_response(i,self.m.nash[1-i]) for i in range(2)],self.m.nash,atol=1e-7)
    def test_monopoly_global_reference(self):
        for a in [(2.,2.),(1.,3.),(3.,1.)]:
            m=Market(a,(.3,.5),.7,0.,(0.,8.))
            ref=differential_evolution(lambda p:-sum(m.profits(p)),[m.bounds]*2,seed=21,tol=1e-10)
            self.assertGreaterEqual(sum(m.profits(m.monopoly)),-ref.fun-1e-7)
    def test_symmetry(self):
        self.assertAlmostEqual(*self.m.nash,places=7); self.assertAlmostEqual(*self.m.monopoly,places=7)
    def test_parameter_grid_stability(self):
        for quality,mu,cost in itertools.product([1.,2.,4.],[.15,.7,2.],[.1,.5]):
            with self.subTest(quality=quality,mu=mu,cost=cost):
                m=Market((quality,quality+.2),(cost,cost+.1),mu,0.,(0.,12.))
                np.testing.assert_allclose([m.best_response(i,m.nash[1-i]) for i in range(2)],m.nash,atol=1e-6)
                self.assertTrue(np.isfinite(m.monopoly).all())
                self.assertGreaterEqual(sum(m.profits(m.monopoly)),sum(m.profits(m.nash))-1e-8)
    def test_best_response_independent_reference(self):
        for rival in [0.,1.,3.,8.]:
            ref=minimize_scalar(lambda p:-self.m.profits([p,rival])[0],bounds=self.m.bounds,method='bounded')
            self.assertAlmostEqual(self.m.best_response(0,rival),ref.x,places=5)
    def test_extreme_logits_remain_finite(self):
        m=Market((1000.,999.),(.5,.5),.001,0.,(0.,2000.))
        self.assertTrue(np.isfinite(m.quantities([1000.,999.])).all())
    def test_invalid_market_rejected(self):
        with self.assertRaises(ValueError): Market((1.,1.),(0.,0.),0.,0.,(0.,8.))
    def test_unresolved_live_market_rejected(self):
        market=dict(load_config(LEGACY)['market'],a=None)
        with self.assertRaises(ValueError): Market.from_config(market)
    def test_calvano_benchmarks(self):
        # SOURCES.md: Nash ~1.47, joint monopoly ~1.92; per-firm profits 22.29 / 33.75 with beta=100.
        m=Market.from_config(load_config(LEGACY)['market'])
        np.testing.assert_allclose(m.nash,[1.4729,1.4729],atol=1e-4)
        np.testing.assert_allclose(m.monopoly,[1.9250,1.9250],atol=1e-4)
        np.testing.assert_allclose(m.nash_profit,[22.29,22.29],atol=5e-3)
        np.testing.assert_allclose(m.monopoly_profit,[33.75,33.75],atol=5e-3)
    def test_welfare_indices(self):
        m=Market.from_config(load_config(LEGACY)['market'])
        self.assertAlmostEqual(m.consumer_harm(m.nash),0.,places=9); self.assertAlmostEqual(m.consumer_harm(m.monopoly),1.,places=9)
        self.assertAlmostEqual(m.welfare_loss(m.nash),0.,places=9); self.assertAlmostEqual(m.welfare_loss(m.monopoly),1.,places=9)
        cs=[m.consumer_surplus([p,p]) for p in (1.2,1.5,1.8,2.1)]
        self.assertTrue(all(x>y for x,y in zip(cs,cs[1:])))  # consumers lose as prices rise
        # Roy's identity: -dCS/dp_i equals the quantity of product i.
        p=np.array([1.6,1.7]); h=1e-6; e=np.array([h,0.])
        self.assertAlmostEqual(-(m.consumer_surplus(p+e)-m.consumer_surplus(p-e))/(2*h),m.quantities(p)[0],places=5)
    def test_welfare_matches_published_logit_table(self):
        # SOURCES.md S7, Supplementary Table 17 (same calibration, M = 100): per-period CS, PS and TW
        # of 71.5, 44.6, 116.1 at Nash and 32.7, 67.5, 100.2 at joint monopoly; deadweight loss 13.7%.
        m=Market.from_config(load_config(LEGACY)['market'])
        for prices,(cs,ps,tw) in ((m.nash,(71.5,44.6,116.1)),(m.monopoly,(32.7,67.5,100.2))):
            self.assertAlmostEqual(round(m.consumer_surplus(prices),1),cs)
            self.assertAlmostEqual(round(float(m.profits(prices).sum()),1),ps)
            self.assertAlmostEqual(round(m.total_surplus(prices),1),tw)
        loss=100*(m.total_surplus(m.nash)-m.total_surplus(m.monopoly))/m.total_surplus(m.nash)
        self.assertAlmostEqual(round(loss,1),13.7)
    def test_size_scales_quantities_not_prices(self):
        base=Market((2.,2.),(1.,1.),.25,0.,(0.,4.)); big=Market((2.,2.),(1.,1.),.25,0.,(0.,4.),size=100.)
        np.testing.assert_allclose(big.nash,base.nash); np.testing.assert_allclose(big.monopoly,base.monopoly,atol=1e-6)
        np.testing.assert_allclose(big.quantities([1.6,1.7]),100*base.quantities([1.6,1.7]))
        np.testing.assert_allclose(big.delta(big.profits([1.6,1.7])),base.delta(base.profits([1.6,1.7])))
