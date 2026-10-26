"""Recovery checks for the production inference: planted effect, null and CI coverage.

Data are drawn from a declared distribution, not from mock agents or LLMs, so the
true mean share removed of every arm is known exactly.
"""
import copy
import unittest
import numpy as np
import pandas as pd
from analysis.pipeline import infer
LEGACY = "config/legacy_r2.yaml"  # the D-023..D-043 design, kept runnable (D-049)
from run.common import load_config

ARMS=['baseline','R1','R2','R3','R4','OVERSIGHT','UNDERCUT','SHAM']


def dataset(rng,n,shares,noise=.05,base=(.55,.95),cost_noise=.01):
    # Delta_arm = Delta_baseline*(1-s)+e with E[e]=0, so E[share_arm]=s exactly.
    b=rng.uniform(*base,n); d={'baseline':b}
    for arm in ARMS[1:]: d[arm]=b*(1-shares.get(arm,0.))+rng.normal(0,noise,n)
    delta=pd.DataFrame(d); s=delta.rsub(delta.baseline,axis=0).div(delta.baseline,axis=0)
    k=pd.DataFrame({a:(np.zeros(n) if a=='baseline' else rng.normal(0,cost_noise,n)) for a in ARMS if a!='UNDERCUT'})
    return delta,s,k


class RecoveryTests(unittest.TestCase):
    reps=200; n=15

    @classmethod
    def setUpClass(cls):
        cls.c=load_config(LEGACY,synthetic=True); cls.c['analysis'].update(bootstrap_resamples=2000)

    def simulate(self,shares,seed):
        c=copy.deepcopy(self.c); rng=np.random.default_rng(seed); out=[]
        for r in range(self.reps):
            c['analysis']['bootstrap_seed']=seed+r
            out.append(infer(*dataset(rng,self.n,shares),c))
        return out

    def test_planted_effect_recovered_with_sane_coverage(self):
        truth={'R1':.5,'R2':.1,'R3':.1,'R4':.1}
        runs=self.simulate(truth,11)
        self.assertGreaterEqual(np.mean([v['winner']=='R1' for _,_,v in runs]),.95)
        mean_base=.75  # E[U(.55,.95)]: true removal of arm r is truth[r]*mean_base
        for arm in ['R1','R2','SHAM']:
            target=truth.get(arm,0.)*mean_base
            cover=np.mean([(lambda r:r.removal_low<=target<=r.removal_high)(s[s.arm==arm].iloc[0]) for s,_,_ in runs])
            with self.subTest(arm=arm): self.assertTrue(.90<=cover<=.99,cover)
            share=np.mean([(lambda r:r.share_low<=truth.get(arm,0.)<=r.share_high)(s[s.arm==arm].iloc[0]) for s,_,_ in runs])
            with self.subTest(arm=arm,quantity='pooled share'): self.assertTrue(.85<=share<=.99,share)
        # Bonferroni-adjusted pairwise contrast: coverage at least nominal 95%.
        contrast=np.mean([(lambda p:p.low<=.4*mean_base<=p.high)(p[(p.arm=='R1')&(p.other=='R2')].iloc[0]) for _,p,_ in runs])
        self.assertTrue(.95<=contrast<=1.,contrast)
        cost=np.mean([(lambda r:r.cost_low<=0<=r.cost_high)(s[s.arm=='R1'].iloc[0]) for s,_,_ in runs])
        self.assertTrue(.85<=cost<=.99,cost)

    def test_null_equal_restrictions_rarely_declare_winner(self):
        runs=self.simulate({'R1':.2,'R2':.2,'R3':.2,'R4':.2},23)
        self.assertLessEqual(np.mean([v['verdict']=='WINNER' for _,_,v in runs]),.05)

    def test_null_no_effect_rarely_declares_winner(self):
        runs=self.simulate({},37)
        self.assertLessEqual(np.mean([v['verdict']=='WINNER' for _,_,v in runs]),.05)
