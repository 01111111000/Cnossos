import unittest
import copy
import numpy as np
from env.market import Market
from env.observations import build,canonical_rows,render
LEGACY = "config/legacy_r2.yaml"  # the D-023..D-043 design, kept runnable (D-049)
from run.common import load_config
from tools.audit_observations import reconstruct,audit


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.c=load_config(LEGACY,synthetic=True); self.m=Market.from_config(self.c['market'])
        self.h=[]
        for t in range(5):
            p=[1.+t/10,2.+t/10]
            self.h.append({'period':t,'prices':p,'quantities':self.m.quantities(p).tolist(),
                'profits':self.m.profits(p).tolist(),'notes':[f'mine-{t}',f'theirs-{t}']})
    def obs(self,arm): return build(self.h,0,arm,self.m,self.c)
    def test_baseline_exact_fields(self):
        o=self.obs('baseline')
        self.assertEqual(set(o),{'task','period','firm','market','history','own_notes'})
        self.assertEqual(set(o['history'][0]),{'period','own_price','own_quantity','own_profit','rival_price'})
        self.assertEqual(len(o['history']),5)
        self.assertNotIn('theirs',str(o))
    def test_notes_latest_only(self):
        # D-028: notes_policy latest, as in Fish et al. (previous period's notes only).
        self.assertEqual(self.obs('baseline')['own_notes'],[{'period':4,'text':'mine-4'}])
    def test_r1_one_row_and_no_notes(self):
        # D-028: R1 keeps only the last completed row and no notes.
        o=self.obs('R1'); base=self.obs('baseline')
        self.assertEqual(o['history'],base['history'][-1:]); self.assertNotIn('own_notes',o)
    def test_r1_notes_switch(self):
        c=copy.deepcopy(self.c); c['observations']['r1_keeps_notes']=True
        self.assertIn('own_notes',build(self.h,0,'R1',self.m,c))
    def test_r2_only_rival_column_removed(self):
        o=self.obs('R2'); base=self.obs('baseline')
        for row in base['history']: row.pop('rival_price')
        self.assertEqual(o,base)
    def test_r3_only_notes_removed(self):
        o=self.obs('R3'); base=self.obs('baseline'); base.pop('own_notes')
        self.assertEqual(o,base); self.assertNotIn('notes',str(o))
    def test_r4_timestamped_delay(self):
        o=self.obs('R4'); self.assertEqual(o['rival_price_delay_periods'],2)
        self.assertEqual([r['rival_price'] for r in o['history']],[2.,2.1,2.2,None,None])
    def test_oversight_only_adds_the_notice(self):
        o=self.obs('OVERSIGHT'); base=self.obs('baseline')
        self.assertEqual(o.pop('notice'),self.c['observations']['oversight_notice']); self.assertEqual(o,base)
        self.assertTrue(render(self.obs('OVERSIGHT')).startswith('Notice: A competition authority'))
        self.assertNotIn('Notice',render(base))
    def test_cost_only_hides_demand_primitives(self):
        o=self.obs('baseline'); self.assertEqual(set(o['market']),{'own_cost','bounds'})
        text=render(o)
        for word in ('mu','outside','quality','a_0'): self.assertNotIn(word,text)
    def test_history_window_and_rounding(self):
        h=[]
        for t in range(130):
            p=[1.23456+t/1000,1.5]
            h.append({'period':t,'prices':p,'quantities':self.m.quantities(p).tolist(),
                      'profits':self.m.profits(p).tolist(),'notes':['','']})
        o=build(h,0,'baseline',self.m,self.c)
        self.assertEqual(len(o['history']),100); self.assertEqual(o['history'][0]['period'],30)
        self.assertEqual(o['history'][-1]['own_price'],round(1.23456+129/1000,2))
    def test_render_matches_structured_observation(self):
        for arm in ['baseline','R1','R2','R3','R4','SHAM']:
            with self.subTest(arm=arm):
                text=render(self.obs(arm))
                self.assertEqual('rival_price' in text, arm!='R2')
                self.assertEqual('private notes' in text, arm in ('baseline','R2','R4','SHAM'))
                self.assertNotIn('theirs',text)
        self.assertIn('NA',render(self.obs('R4')))
        self.assertEqual(render(self.obs('R1')).count('\n'),render(build(self.h[-1:],0,'R1',self.m,self.c)).count('\n'))
    def test_sham_drops_only_a_derivable_column(self):
        # D-037: SHAM removes own profit, which equals (own price - own cost) x own quantity.
        sham=canonical_rows(self.obs('SHAM')); base=canonical_rows(self.obs('baseline')); cost=self.m.costs[0]
        for s,b in zip(sham,base):
            self.assertNotIn('own_profit',s); self.assertEqual(s,{k:v for k,v in b.items() if k!='own_profit'})
            self.assertAlmostEqual((s['own_price']-cost)*s['own_quantity'],b['own_profit'],places=1)
        self.assertEqual(self.obs('SHAM')['own_notes'],self.obs('baseline')['own_notes'])
        self.assertNotIn('your_profit',render(self.obs('SHAM')))
    def test_sham_columns_format_still_available(self):
        c=copy.deepcopy(self.c); c['observations']['sham_format']='columns'
        self.assertEqual(canonical_rows(build(self.h,0,'SHAM',self.m,c)),canonical_rows(self.obs('baseline')))
    def test_builder_does_not_mutate_history(self):
        before=copy.deepcopy(self.h)
        for arm in ['baseline','R1','R2','R3','R4','SHAM']: self.obs(arm)
        self.assertEqual(before,self.h)
    def test_inversion_r2_and_r4(self):
        # Exact inversion is possible only if demand parameters are known; cost_only withholds them.
        for h in self.h:
            for i in range(2): self.assertAlmostEqual(reconstruct(self.m,i,h['prices'][i],h['quantities'][i]),h['prices'][1-i],places=7)
        report=audit(self.c)
        self.assertTrue(all(r['reconstructable_if_parameters_known'] for r in report))
        self.assertFalse(any(r['demand_parameters_disclosed'] for r in report))
    def test_no_future_price_disclosure(self):
        o=build(self.h[:2],0,'R4',self.m,self.c)
        self.assertEqual([r['rival_price'] for r in o['history']],[None,None])
