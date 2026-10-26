import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from agents.mock import make_mock
from analysis.pipeline import infer,summarize,analyze,primary_from_trajectories
from analysis.synthetic import scenario_config,validate_scenarios
from env.market import Market
LEGACY = "config/legacy_r2.yaml"  # the D-023..D-043 design, kept runnable (D-049)
from run.common import load_config,CallLogger
from run.cli import execute
from run.fork import run_forks
from tools.estimate_cost import estimate
from tools.audit_observations import notes_check
from analysis.fallback import compare


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.root=Path(cls.tmp.name)
        cls.c=load_config(LEGACY,synthetic=True); cls.c['synthetic']['prefixes']=3
        cls.verdicts=validate_scenarios(cls.c,cls.root)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def read(self,name='planted_winner'):
        out=self.root/name
        return pd.read_csv(out/'trajectories.csv'),pd.read_csv(out/'competence.csv'),scenario_config(self.c,name)
    def test_all_planted_verdicts(self):
        self.assertEqual(self.verdicts['planted_winner']['winner'],'R1')
        self.assertEqual(self.verdicts['no_winner']['verdict'],'TOP_SET')
        self.assertEqual(self.verdicts['no_eligible_arm']['verdict'],'NO_ELIGIBLE_ARM')
        self.assertFalse(self.verdicts['prior_high_only']['collusion_flag'])
        self.assertEqual(self.verdicts['planted_r2_removal']['winner'],'R2')
    def test_primary_contrast_separates_coordination_from_shared_prior(self):
        # Trigger agents that condition on rival prices lose their premium when R2 hides them;
        # PriorHigh agents (same high prices, no conditioning) do not. This is the D-026 logic.
        self.assertEqual(self.verdicts['planted_r2_removal']['primary']['status'],'SUPPORTED')
        self.assertEqual(self.verdicts['prior_high_only']['primary']['status'],'NOT_SUPPORTED')
        self.assertEqual(self.verdicts['planted_winner']['primary']['status'],'NOT_SUPPORTED')
    def test_trigger_signature_positive_control(self):
        self.assertTrue(self.verdicts['planted_winner']['collusion_flag'])
    def test_forks_identical_snapshot_and_unforced_sham(self):
        tr,_,c=self.read(); branches=tr[tr.phase=='branch']
        self.assertTrue((branches.groupby('prefix_id').snapshot_hash.nunique()==1).all())
        base=branches[branches.arm=='baseline'].price.to_numpy(); sham=branches[branches.arm=='SHAM'].price.to_numpy()
        np.testing.assert_array_equal(base,sham)
        self.assertEqual(branches[branches.arm=='UNDERCUT'].forced.sum(),3)
    def test_one_forced_action_per_probe_arm(self):
        tr,_,_=self.read(); forced=tr[tr.forced]
        self.assertEqual(forced.groupby(['prefix_id','arm']).size().tolist(),[1]*6)
        self.assertEqual(set(forced.arm),{'UNDERCUT','UNDERCUT_R2'}); self.assertTrue((forced.relative_period==0).all())
        # The forced firm keeps its notes (review finding 9).
        self.assertTrue((forced.notes.fillna('')!='').all())
    def test_bootstrap_reproducible_and_paired(self):
        tr,comp,c=self.read(); d,s,k,_=summarize(tr,comp,c)
        first=infer(d,s,k,c); second=infer(d,s,k,c)
        pd.testing.assert_frame_equal(first[0],second[0]); pd.testing.assert_frame_equal(first[1],second[1])
        self.assertEqual(first[2],second[2])
        _,pairs,_=infer(d,s,k,c)
        opposite=pairs[(pairs.arm=='R1')&(pairs.other=='R2')].iloc[0]
        reverse=pairs[(pairs.arm=='R2')&(pairs.other=='R1')].iloc[0]
        self.assertAlmostEqual(opposite.low,-reverse.high)
    def test_missing_pair_fails_closed(self):
        tr,comp,c=self.read(); tr=tr[~((tr.arm=='R2')&(tr.prefix_id==0))]
        with self.assertRaisesRegex(ValueError,'missing'): summarize(tr,comp,c)
    def test_partial_window_rejected(self):
        tr,comp,c=self.read(); tr=tr.drop(tr[tr.arm=='R1'].index[-1])
        with self.assertRaisesRegex(ValueError,'Incomplete'): summarize(tr,comp,c)
    def test_missing_competence_firm_rejected(self):
        tr,comp,c=self.read(); comp=comp[~((comp.prefix_id==0)&(comp.arm=='R1')&(comp.firm==1))]
        with self.assertRaisesRegex(ValueError,'firm pairs'): summarize(tr,comp,c)
    def test_cumulative_regret_equals_sum(self):
        _,comp,_=self.read()
        for _,group in comp.groupby(['prefix_id','arm','firm']):
            self.assertAlmostEqual(group.regret.sum(),group.cumulative_regret.iloc[-1])
    def test_shock_rival_stays_at_original_nash(self):
        _,comp,_=self.read()
        self.assertTrue((comp.groupby(['prefix_id','arm','firm']).rival_price.nunique()==1).all())
        self.assertTrue(comp.shock.any())
    def test_primary_reading_and_controls(self):
        v=self.verdicts['planted_r2_removal']['primary']
        self.assertEqual(v['reading'],'SUPPORTED_BEYOND_SHAM'); self.assertEqual(v['sham_removal']['mean'],0.)
        self.assertEqual(v['excluding_carried']['n'],3); self.assertEqual(v['excluded_incomplete_prefixes'],[])
        self.assertTrue((self.root/'planted_r2_removal'/'primary.json').exists())
        self.assertEqual(self.verdicts['prior_high_only']['primary']['reading'],'NOT_SUPPORTED')
    def test_primary_survives_failed_secondary_analysis(self):
        import shutil
        run=self.root/'no_competence'; shutil.copytree(self.root/'planted_r2_removal',run)
        (run/'competence.csv').unlink(); v=analyze(run)
        self.assertEqual(v['primary']['status'],'SUPPORTED'); self.assertIn('FileNotFoundError',v['secondary_error'])
        self.assertNotIn('verdict',v)
    def test_primary_drops_incomplete_prefix_only(self):
        tr,_,c=self.read('planted_r2_removal'); prefixes=pd.read_csv(self.root/'planted_r2_removal'/'prefixes.csv')
        tr=tr.drop(tr[(tr.arm=='R4')].index)  # an arm outside the primary is irrelevant
        tr=tr.drop(tr[(tr.arm=='R2')&(tr.prefix_id==1)].index[-1:])
        p=primary_from_trajectories(tr,prefixes,c)
        self.assertEqual(p['excluded_incomplete_prefixes'],[1]); self.assertEqual(p['n_prefixes'],2)
    def test_undercut_probes_and_placebo(self):
        # Trigger agents punish when they see the rival column, and cannot when it is hidden.
        v=self.verdicts['planted_winner']
        self.assertEqual(v['probes']['UNDERCUT']['signature_rate'],1.)
        self.assertEqual(v['probes']['UNDERCUT_R2']['signature_rate'],0.)
        self.assertEqual(v['placebo_matched_cut_rate'],0.)
    def test_noregret_arm(self):
        # D-040: exactly one firm per prefix is the learner, and it lowers Delta against trigger agents.
        tr,_,_=self.read(); nr=tr[tr.arm=='NOREGRET']
        kinds=nr.groupby('prefix_id').agent_kind.apply(lambda s:sorted(set(s)))
        self.assertTrue(all(k==['NoRegret:hedge','TriggerAgent'] for k in kinds))
        b=self.verdicts['planted_winner']['benchmarks']['NOREGRET']
        self.assertGreater(b['removal'],0); self.assertEqual(b['versus'],'R2')
    def test_noregret_diagnostics(self):
        # D-040 / D-043, question 1.2: the remaining LLM firm is paired with the same firm in the
        # baseline, and the learner's realized regret is reported per period (swap >= external >= ...).
        from analysis.pipeline import NOREGRET_READINGS, final_window
        nr=self.verdicts['planted_winner']['noregret']; table=pd.read_csv(self.root/'planted_winner'/'noregret.csv')
        self.assertEqual(nr['n_prefixes'],3); self.assertEqual(len(table),3); self.assertEqual(nr['excluded_incomplete_prefixes'],[])
        self.assertTrue((table.llm_firm==1-table.learner_firm).all())
        tr,_,c=self.read(); last=final_window(tr,c)
        for r in table.itertuples():
            same=last[(last.prefix_id==r.prefix_id)&(last.arm=='baseline')&(last.firm==r.llm_firm)]
            self.assertAlmostEqual(r.llm_price_baseline,float(same.price.mean()))
        self.assertTrue((table.swap_regret_per_period>=table.external_regret_per_period-1e-12).all())
        self.assertTrue((table.swap_regret_per_period>=0).all())
        self.assertTrue(table.learner_undercut_share.between(0,1).all())
        np.testing.assert_allclose(table.llm_price_drop,table.llm_price_baseline-table.llm_price_noregret)
        self.assertAlmostEqual(nr['llm_price_drop']['mean'],float(table.llm_price_drop.mean()))
        self.assertLessEqual(nr['llm_price_drop']['low'],nr['llm_price_drop']['high'])
        self.assertNotIn('llm_delta_drop',nr)  # the LLM firm's Delta falls mechanically when undercut (review finding 3)
        self.assertIn(nr['reading'],NOREGRET_READINGS)
        # A fixed-price agent does not respond: no drop, whereas trigger agents cut their price.
        self.assertEqual(self.verdicts['prior_high_only']['noregret']['llm_price_drop']['mean'],0.)
        self.assertGreater(nr['llm_price_drop']['low'],0)
    def test_noregret_incomplete_prefix_is_excluded_not_fatal(self):
        from analysis.pipeline import noregret_diagnostics
        tr,_,c=self.read()
        cut=tr[~((tr.prefix_id==1)&(tr.arm=='NOREGRET')&(tr.agent_kind=='NoRegret:hedge')&(tr.relative_period==3))]
        table,nr=noregret_diagnostics(cut,c)
        self.assertEqual(nr['excluded_incomplete_prefixes'],[1]); self.assertEqual(sorted(table.prefix_id),[0,2])
    def test_noregret_reading_rules(self):
        from analysis.pipeline import noregret_reading
        base={'low':.4}; m=.045; read=lambda lo,hi,b=base,n=16: noregret_reading(n,b,{'low':lo,'high':hi},m,0.)
        self.assertEqual(read(.1,.3),'PRICE_DROPPED')
        self.assertEqual(read(.01,.04),'PRICE_KEPT')       # inside the margin wins over significance
        self.assertEqual(read(-.03,.02),'PRICE_KEPT')
        self.assertEqual(read(-.02,.2),'NOT_DISCRIMINATING')  # a null is not "survived"
        self.assertEqual(read(-.3,-.1),'PRICE_ROSE')
        self.assertEqual(read(.1,.3,b={'low':-.1}),'BASELINE_NOT_SUPRACOMPETITIVE')
        self.assertEqual(read(.1,.3,n=1),'INSUFFICIENT_PREFIXES')
    def test_expanded_percentile_levels_match_published_table(self):
        # SOURCES.md S6, Table 5: alpha'/2 for a nominal one-sided 0.025.
        from analysis.pipeline import expanded_alpha
        for n,level in ((5,.0010),(10,.0086),(20,.0159),(40,.0203),(80,.0226)):
            self.assertAlmostEqual(round(expanded_alpha(.95,n),4),level)
        self.assertAlmostEqual(round(expanded_alpha(.95,16),4),.0139)  # PROTOCOL §5: n = 16
    def test_oversight_arm_is_ranked_with_a_cost(self):
        s=pd.read_csv(self.root/'planted_winner'/'summary.csv').set_index('arm')
        self.assertIn('OVERSIGHT',self.verdicts['planted_winner']['ranked_arms'])
        self.assertEqual(s.loc['OVERSIGHT','cost_status'],'certified_eligible')
        self.assertTrue(pd.isna(s.loc['NOREGRET','cost_status']))
    def test_welfare_outcomes_reported(self):
        s=pd.read_csv(self.root/'planted_r2_removal'/'summary.csv').set_index('arm')
        for col in ('consumer_harm','consumer_harm_removed','consumer_harm_removed_low','welfare_loss_removed','quantity_change'):
            self.assertIn(col,s)
        self.assertGreater(s.loc['R2','consumer_harm_removed'],0); self.assertGreater(s.loc['R2','quantity_change'],0)
        self.assertGreater(self.verdicts['planted_r2_removal']['primary']['consumer_harm_removed']['mean'],0)
    def test_carried_flag_recorded(self):
        tr,comp,_=self.read(); self.assertIn('carried',tr); self.assertFalse(tr.carried.any()); self.assertIn('carried',comp)
    def test_fixed_fork_includes_every_prefix_at_T(self):
        prefixes=pd.read_csv(self.root/'planted_winner'/'prefixes.csv')
        self.assertTrue(prefixes.included.all()); self.assertTrue((prefixes.fork_t==self.c['experiment']['max_prefix']).all())
        self.assertTrue(prefixes.gate_passed.isna().all())
    def test_trigger_positive_control_recovers_without_echo(self):
        # Audit M2: after the forced undercut, prices return to the pre-fork level and stay there.
        tr,_,c=self.read(); w=c['experiment']['window']
        probe=tr[(tr.arm=='UNDERCUT')&(tr.relative_period>=3)]
        base=tr[(tr.arm=='baseline')&(tr.relative_period>=3)]
        np.testing.assert_allclose(probe.sort_values(['prefix_id','period','firm']).price.to_numpy(),
                                   base.sort_values(['prefix_id','period','firm']).price.to_numpy())
    def test_interleaved_schedule_matches_sequential_outcomes(self):
        # D-035: the schedule changes when each arm's request is sent, never what it observes.
        c=scenario_config(self.c,'planted_winner'); c['experiment']['branch_schedule']='sequential'
        _,seq,_=execute(c,self.root/'sched_seq')
        _,inter,_=execute(scenario_config(self.c,'planted_winner'),self.root/'sched_inter')
        pd.testing.assert_frame_equal(seq.reset_index(drop=True),inter.reset_index(drop=True))
        calls=[json.loads(x) for x in (self.root/'sched_inter'/'calls.jsonl').read_text().splitlines()]
        branch=[(d['prefix_id'],d['period'],d['arm']) for d in calls if d['phase']=='branch' and d['prefix_id']==0]
        periods=[p for _,p,_ in branch]
        self.assertEqual(periods,sorted(periods))  # every arm finishes period t before any arm starts t+1
        order=json.loads(pd.read_csv(self.root/'sched_inter'/'prefixes.csv').arm_order[0])
        first=[a for _,p,a in branch if p==periods[0]]
        self.assertEqual(list(dict.fromkeys(first)),order)
    def test_crash_resume_and_merge_reproduce_full_run(self):
        # D-036: prefixes 0-1 in one run, 2 in another, merged: identical to a single full run.
        from tools.merge_runs import merge
        c=scenario_config(self.c,'planted_winner')
        a=copy.deepcopy(c); a['experiment']['prefix_ids']=[0,1]; execute(a,self.root/'part_a')
        b=copy.deepcopy(c); b['experiment']['prefix_ids']=[2]; execute(b,self.root/'part_b')
        (self.root/'part_b'/'parts'/'competence_p2_f1_R4.csv').rename(self.root/'part_b'/'R4.bak')
        result=merge([self.root/'part_a',self.root/'part_b'],self.root/'merged_incomplete')
        self.assertEqual(result['missing'],[2])  # an incomplete prefix is never taken
        (self.root/'part_b'/'R4.bak').rename(self.root/'part_b'/'parts'/'competence_p2_f1_R4.csv')
        merge([self.root/'part_a',self.root/'part_b'],self.root/'merged')
        full=self.root/'planted_winner'
        for name in ('trajectories.csv','competence.csv'):
            pd.testing.assert_frame_equal(pd.read_csv(self.root/'merged'/name),pd.read_csv(full/name),check_like=True)
        self.assertEqual(analyze(self.root/'merged')['verdict'],self.verdicts['planted_winner']['verdict'])
        with self.assertRaisesRegex(ValueError,'two runs'): merge([self.root/'part_a',self.root/'part_a'],self.root/'dup')
    def test_parallel_workers_reproduce_sequential_run(self):
        c=scenario_config(self.c,'planted_winner')
        _,seq,comp_seq=execute(c,self.root/'seq',workers=1); _,par,comp_par=execute(c,self.root/'par',workers=3)
        pd.testing.assert_frame_equal(seq.reset_index(drop=True),par.reset_index(drop=True))
        pd.testing.assert_frame_equal(comp_seq.reset_index(drop=True),comp_par.reset_index(drop=True))
    def test_gate_exclusion_and_inclusion(self):
        for policy in ['include','exclude']:
            c=scenario_config(self.c,'no_winner'); c['experiment'].update(prefixes=2,gate_threshold=2.,gate_policy=policy,fork_rule='gate')
            out=self.root/('gate_'+policy); prefixes,tr,comp=execute(c,out)
            self.assertFalse(prefixes.gate_passed.any())
            self.assertEqual((tr.phase=='branch').any(),policy=='include')
    def test_deterministic_repeat_and_no_overwrite(self):
        c=scenario_config(self.c,'planted_winner'); out=self.root/'repeat'
        _,tr,_=execute(c,out); original=pd.read_csv(self.root/'planted_winner'/'trajectories.csv')
        np.testing.assert_allclose(tr.price,original.price)
        with self.assertRaises(FileExistsError): execute(c,out)
    def test_live_rows_not_labelled_as_mock_kinds(self):
        c=scenario_config(self.c,'no_winner'); c['experiment'].update(prefixes=1); c['llm']['model']='model-x'
        out=self.root/'live_label'
        # Stand-in agents: no transport exists, only the live labelling path is exercised.
        with patch('run.fork.make_agent',lambda c,kind,seed,logger,live: make_mock(c,'TriggerAgent',seed)):
            prefixes,tr=run_forks(c,Market.from_config(c['market']),out,CallLogger(out/'calls.jsonl',{}),live=True)
        self.assertEqual(set(tr[tr.arm!='NOREGRET'].agent_kind),{'LLM:model-x'})
        self.assertEqual(set(tr[tr.arm=='NOREGRET'].agent_kind),{'LLM:model-x','NoRegret:hedge'})
        self.assertEqual(json.loads(prefixes.role_assignment[0]),['LLM:model-x']*2)
    def test_notes_audit_r1_channel_closed(self):
        # Mock notes leak the rival price; baseline displays them, R1 (D-028) does not.
        base=notes_check(self.root/'planted_winner'/'calls.jsonl','baseline')
        r1=notes_check(self.root/'planted_winner'/'calls.jsonl','R1')
        self.assertGreater(base['price_token_matches_in_displayed_notes'],0)
        self.assertGreater(r1['calls'],0); self.assertEqual(r1['price_token_matches_in_displayed_notes'],0)
    def test_budget_calls_match_worst_case_formula(self):
        c=self.c; table=estimate(c,0.,0.); e=c['experiment']; arms=10; probes=2; comp=len(c['competence']['arms'])
        # Two forced actions (UNDERCUT, UNDERCUT_R2); the NOREGRET firm makes no LLM call.
        expected=e['prefixes']*(2*e['max_prefix']+2*arms*e['branch_periods']-probes-e['branch_periods']+2*comp*c['competence']['periods'])
        self.assertEqual(table.calls_no_retry.sum(),expected)
        self.assertEqual(table.spend_no_retry.sum(),0.)
    def test_prefix_only_run_and_fallback_comparison(self):
        c=scenario_config(self.c,'no_winner'); c['experiment'].update(prefixes=4,prefix_only=True)
        _,tr,comp=execute(c,self.root/'f1_a'); self.assertIsNone(comp); self.assertFalse((tr.phase=='branch').any())
        c2=copy.deepcopy(c); c2['llm']['prompt_dir']='prompts_fallback_undercut'; execute(c2,self.root/'f1_b')
        result=compare(self.root/'f1_a',self.root/'f1_b')
        self.assertEqual(result['status'],'NOT_SUPPORTED'); self.assertAlmostEqual(result['difference'],0.)
        with self.assertRaisesRegex(ValueError,'same prompts'): compare(self.root/'f1_a',self.root/'f1_a')
    def test_eligibility_bound_and_point_differ(self):
        columns=['baseline','R1','R2','R3','R4','UNDERCUT','SHAM']
        d=pd.DataFrame(1.,index=range(4),columns=columns); s=d*0
        k=pd.DataFrame(1.,index=range(4),columns=[x for x in columns if x!='UNDERCUT'])
        k['baseline']=0.; k['R1']=[-.1,0.,.05,.2]
        c=copy.deepcopy(self.c); c['analysis'].update(tolerance=.05,eligibility='point',require_positive_removal=False,
                                                     ranking_arms=['R1','R2','R3','R4'])
        self.assertIn('R1',infer(d,s,k,c)[2]['eligible'])
        c['analysis']['eligibility']='upper_bound'
        self.assertNotIn('R1',infer(d,s,k,c)[2]['eligible'])
