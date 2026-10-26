import copy
import unittest
import numpy as np
from env.market import Market
from env.observations import build
from fallback.qlearning import QLearningAgent
LEGACY = "config/legacy_r2.yaml"  # the D-023..D-043 design, kept runnable (D-049)
from run.common import load_config


class QLearningTests(unittest.TestCase):
    def setUp(self):
        self.c=load_config(LEGACY,synthetic=True); self.m=Market.from_config(self.c['market'])
        self.a=QLearningAgent(self.c['fallback'],self.m,1)
    def test_update_equation(self):
        self.a.q[1]=2.; self.a.update(0,0,1.,1)
        self.assertAlmostEqual(self.a.q[0,0],self.c['fallback']['alpha']*(1+2*self.c['fallback']['gamma']))
    def test_hidden_rival_uses_unknown_state(self):
        obs=build([],0,'R2',self.m,self.c)
        self.assertEqual(self.a.state(obs),len(self.a.grid))
    def test_fork_copy_preserves_q_and_rng(self):
        other=copy.deepcopy(self.a)
        np.testing.assert_array_equal(other.q,self.a.q)
        self.assertEqual(other.rng.random(),self.a.rng.random())
        other.q[0,0]=99; self.assertNotEqual(other.q[0,0],self.a.q[0,0])
    def test_single_action_in_bounds_no_training_run(self):
        obs=build([],0,'baseline',self.m,self.c)
        d=self.a.act(obs,self.m,0,self.m.nash[0],{})
        self.assertGreaterEqual(d['price'],self.m.bounds[0]); self.assertLessEqual(d['price'],self.m.bounds[1])
