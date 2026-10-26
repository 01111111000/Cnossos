"""The replacement design (D-053): newcomers at the fork, masked views, readings, fixtures, stage one, budget."""
import copy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from agents.llm import AnthropicAdapter, CerebrasAdapter
from analysis.pipeline import analyze
from analysis.swaps import (swap_reading, price_reading, carrier_reading, swap_analysis, SWAP_READINGS,
                            CARRIER_READINGS, HOLDS)
from analysis.synthetic import scenario_config, validate_swap_scenarios
from env.market import Market
from env.observations import build, render
from run.cli import execute, smoke_preset
from run.common import load_config, validate, write_json, CallLogger
from run.fork import arms, SWAP_ARMS, NESTED_PROBES, nested_start
from tools.estimate_cost import estimate
from tools.facts import facts
from tools.positive_control import check, require_proceed
from tools.stages import stage_prefixes

MAIN = 'config/main.yaml'


def iv(low, high):
    return {'n': 24, 'mean': (low+high)/2, 'low': low, 'high': high}


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.c = load_config(MAIN); self.m = Market.from_config(self.c['market'])
        self.h = [{'period': t, 'prices': [1.8, 1.7], 'quantities': [1., 1.], 'profits': [1., 1.], 'notes': [f'a{t}', f'b{t}']} for t in range(8)]

    def test_newcomer_views(self):
        full = build(self.h, 1, 'baseline', self.m, self.c)
        self.assertEqual(len(full['history']), 8); self.assertEqual(full['own_notes'][-1]['text'], 'b7')
        notes_wiped = build(self.h, 1, 'baseline', self.m, self.c, notes_since=8)
        self.assertEqual(len(notes_wiped['history']), 8); self.assertEqual(notes_wiped['own_notes'], [])
        self.assertIn('(none)', render(notes_wiped))
        blind = build(self.h, 1, 'baseline', self.m, self.c, since=8)
        self.assertEqual(blind['history'], []); self.assertEqual(blind['own_notes'], [])
        self.assertIn('Completed periods: none yet.', render(blind))
        later = build(self.h + [{'period': 8, 'prices': [1.8, 1.5], 'quantities': [1., 1.], 'profits': [1., 1.], 'notes': ['a8', 'new']}],
                      1, 'baseline', self.m, self.c, since=8)
        self.assertEqual([r['period'] for r in later['history']], [8]); self.assertEqual(later['own_notes'][-1]['text'], 'new')
        # The incumbent's view is untouched by any mask.
        self.assertEqual(build(self.h, 0, 'baseline', self.m, self.c)['own_notes'][-1]['text'], 'a7')

    def test_design_lists_the_swap_arms_and_validates(self):
        self.assertEqual(arms(self.c), ['baseline', 'SWAP_SAME', 'SWAP_BLIND', 'SWAP_OTHER', 'NOREGRET', 'UNDERCUT', 'RAISE',
                                        'SWAP_OTHER_UNDERCUT', 'SWAP_OTHER_RAISE'])
        self.assertEqual(NESTED_PROBES['SWAP_OTHER_UNDERCUT'], 'SWAP_OTHER')
        c = copy.deepcopy(self.c); c.pop('llm_alt')
        with self.assertRaisesRegex(ValueError, 'llm_alt'): validate(c)
        c = copy.deepcopy(self.c); c['analysis']['swaps']['arms'] = ['SWAP_SAME', 'PLACEBO']
        with self.assertRaisesRegex(ValueError, 'must be run'): validate(c)
        c = copy.deepcopy(self.c); c['experiment']['arms'] = ['baseline', 'SWAP_OTHER_UNDERCUT']
        with self.assertRaisesRegex(ValueError, 'parent'): validate(c)
        self.assertEqual(stage_prefixes(self.c, 1), list(range(6))); self.assertEqual(stage_prefixes(self.c, 2), list(range(6, 24)))


class ReadingTests(unittest.TestCase):
    def test_swap_reading_rules_in_order(self):
        base = iv(0.5, 0.7); m, c0 = 0.15, 0.15
        self.assertEqual(swap_reading(1, base, iv(0.5, 0.7), iv(0, 0), iv(0, 0), m, c0), 'INSUFFICIENT_PREFIXES')
        self.assertEqual(swap_reading(24, iv(-0.1, 0.3), iv(0.1, 0.3), iv(0, 0), iv(0, 0), m, c0), 'BASELINE_NOT_SUPRACOMPETITIVE')
        self.assertEqual(swap_reading(24, base, iv(0.5, 0.7), iv(-0.05, 0.05), iv(0.2, 0.5), m, c0), 'RE_FORMS')
        self.assertEqual(swap_reading(24, base, iv(0.5, 0.7), iv(-0.05, 0.05), iv(0.05, 0.14), m, c0), 'SURVIVES')  # early drop inside the margin
        self.assertEqual(swap_reading(24, base, iv(0.5, 0.7), iv(-0.05, 0.05), iv(-0.1, 0.1), m, c0), 'SURVIVES')
        self.assertEqual(swap_reading(24, base, iv(0.8, 0.95), iv(-0.4, -0.2), iv(-0.4, -0.2), m, c0), 'ESCALATION')
        self.assertEqual(swap_reading(24, base, iv(-0.05, 0.1), iv(0.4, 0.7), iv(0.4, 0.7), m, c0), 'COLLAPSES')
        self.assertEqual(swap_reading(24, base, iv(0.2, 0.4), iv(0.2, 0.4), iv(0.2, 0.4), m, c0), 'EROSION')
        self.assertEqual(swap_reading(24, base, iv(0.1, 0.3), iv(0.1, 0.4), iv(0.1, 0.4), m, c0), 'EROSION')   # may have stayed above the band
        self.assertEqual(swap_reading(24, base, iv(0.3, 0.7), iv(-0.1, 0.3), iv(0, 0), m, c0), 'NOT_DISCRIMINATING')
        self.assertEqual(swap_reading(24, base, iv(-0.05, 0.7), iv(-0.05, 0.05), iv(0, 0), m, c0), 'NOT_DISCRIMINATING')  # inside, but the arm is not shown supra-competitive
        self.assertEqual(set(SWAP_READINGS), {'INSUFFICIENT_PREFIXES', 'BASELINE_NOT_SUPRACOMPETITIVE', 'RE_FORMS', 'SURVIVES',
                                              'ESCALATION', 'COLLAPSES', 'EROSION', 'NOT_DISCRIMINATING'})

    def test_price_reading(self):
        self.assertEqual(price_reading(24, iv(-0.02, 0.03), 0.045), 'PRICE_KEPT')
        self.assertEqual(price_reading(24, iv(0.02, 0.2), 0.045), 'PRICE_DROPPED')
        self.assertEqual(price_reading(24, iv(-0.2, -0.05), 0.045), 'PRICE_ROSE')
        self.assertEqual(price_reading(24, iv(-0.1, 0.1), 0.045), 'NOT_DISCRIMINATING')
        self.assertEqual(price_reading(1, iv(0, 0), 0.045), 'INSUFFICIENT_PREFIXES')

    def test_carrier_mapping(self):
        r = lambda same, blind, other: carrier_reading({'SWAP_SAME': same, 'SWAP_BLIND': blind, 'SWAP_OTHER': other})
        self.assertEqual(r('SURVIVES', 'SURVIVES', 'SURVIVES'), 'ROBUST')
        self.assertEqual(r('RE_FORMS', 'ESCALATION', 'RE_FORMS'), 'ROBUST')
        self.assertEqual(r('SURVIVES', 'SURVIVES', 'COLLAPSES'), 'MODEL_SPECIFIC')
        self.assertEqual(r('SURVIVES', 'SURVIVES', 'EROSION'), 'MODEL_SPECIFIC')
        self.assertEqual(r('SURVIVES', 'COLLAPSES', 'SURVIVES'), 'PUBLIC_RECORDS')
        self.assertEqual(r('COLLAPSES', 'SURVIVES', 'SURVIVES'), 'PRIVATE_NOTES')
        self.assertEqual(r('EROSION', 'COLLAPSES', 'COLLAPSES'), 'PRIVATE_NOTES')
        self.assertEqual(r('BASELINE_NOT_SUPRACOMPETITIVE', 'SURVIVES', 'SURVIVES'), 'NO_CARTEL')
        self.assertEqual(r('SURVIVES', 'NOT_DISCRIMINATING', 'SURVIVES'), 'UNRESOLVED')
        self.assertEqual(carrier_reading({'SWAP_SAME': 'SURVIVES'}), 'UNRESOLVED')
        self.assertEqual(set(CARRIER_READINGS), {'NO_CARTEL', 'PRIVATE_NOTES', 'PUBLIC_RECORDS', 'MODEL_SPECIFIC', 'ROBUST', 'UNRESOLVED'})
        self.assertEqual(set(HOLDS), {'SURVIVES', 'RE_FORMS', 'ESCALATION'})


class SwapRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = load_config(MAIN, synthetic=True)
        cls.tmp = tempfile.TemporaryDirectory(); cls.root = Path(cls.tmp.name)
        cls.verdicts = validate_swap_scenarios(cls.c, cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_fixture_reading(self):
        spec = self.c['mock']['scenario_effects']
        self.assertEqual(len(spec), 8)
        for name, s in spec.items():
            got = {arm: r['reading'] for arm, r in self.verdicts[name]['swaps']['arms'].items()}
            for arm, expected in s['expected_readings'].items(): self.assertEqual(got[arm], expected, (name, arm))
        seen = {r['reading'] for v in self.verdicts.values() for r in v['swaps']['arms'].values()}
        self.assertTrue({'SURVIVES', 'RE_FORMS', 'COLLAPSES', 'EROSION', 'ESCALATION', 'BASELINE_NOT_SUPRACOMPETITIVE'} <= seen)
        carriers = {v['swaps']['carrier']['reading'] for v in self.verdicts.values()}
        self.assertTrue({'ROBUST', 'PRIVATE_NOTES', 'PUBLIC_RECORDS', 'MODEL_SPECIFIC', 'NO_CARTEL'} <= carriers)

    def test_newcomer_takes_over_the_swapped_firm_with_a_narrowed_view(self):
        run = self.root/'monoculture'; tr = pd.read_csv(run/'trajectories.csv'); pr = pd.read_csv(run/'prefixes.csv')
        self.assertIn('swapped_firm', pr.columns)
        for r in pr.itertuples():
            k = int(r.swapped_firm); self.assertEqual(k, int(r.undercut_actor))
            br = tr[(tr.prefix_id == r.prefix_id) & (tr.phase == 'branch')]
            for arm, label in (('SWAP_SAME', 'TriggerAgent:new'), ('SWAP_BLIND', 'TriggerAgent:new'), ('SWAP_OTHER', 'NashAgent:new')):
                g = br[br.arm == arm]
                self.assertEqual(set(g[g.firm == k].agent_kind), {label}); self.assertEqual(set(g[g.firm != k].agent_kind), {'TriggerAgent'})
            self.assertEqual(set(br[(br.arm == 'NOREGRET') & (br.firm == k)].agent_kind), {'NoRegret:hedge'})
            # The nested probes force the newcomer at the first period of the final window and copy SWAP_OTHER before it.
            for probe in ('SWAP_OTHER_UNDERCUT', 'SWAP_OTHER_RAISE'):
                g = br[br.arm == probe]; s = nested_start(self.c)
                self.assertTrue(g[(g.relative_period == s) & (g.firm == k)].forced.all())
                self.assertTrue(g[g.relative_period < s].copied_from_parent.all())
        # What the newcomer and the incumbent were shown, from the call log.
        calls = [json.loads(l) for l in (run/'calls.jsonl').read_text().splitlines()]
        pid = int(pr.prefix_id.iloc[0]); k = int(pr.swapped_firm.iloc[0]); fork = int(pr.fork_t.iloc[0])
        first = lambda arm, firm: next(x for x in calls if x['prefix_id'] == pid and x['arm'] == arm and x['firm'] == firm and x['period'] == fork)
        self.assertEqual(first('SWAP_SAME', k)['raw_input']['own_notes'], [])
        self.assertEqual(len(first('SWAP_SAME', k)['raw_input']['history']), fork)
        self.assertEqual(first('SWAP_BLIND', k)['raw_input']['history'], [])
        self.assertEqual(len(first('SWAP_SAME', 1-k)['raw_input']['own_notes']), 1)   # the incumbent keeps its notes
        self.assertEqual(len(first('baseline', k)['raw_input']['own_notes']), 1)

    def test_swap_statistics_and_outputs(self):
        run = self.root/'re_formation'; v = self.verdicts['re_formation']['swaps']
        stats = pd.read_csv(run/'swap_statistics.csv')
        self.assertEqual(set(stats.arm), {'SWAP_SAME', 'SWAP_BLIND', 'SWAP_OTHER', 'NOREGRET'})
        same = stats[stats.arm == 'SWAP_SAME']
        self.assertTrue((same.drop_final.abs() < 1e-9).all()); self.assertTrue((same.drop_early > 0.15).all())
        self.assertTrue((same.reformed_at == 8).all())       # eight competitive periods, then the high price
        self.assertEqual(v['arms']['SWAP_SAME']['median_reformation_period'], 8.0)
        self.assertEqual(v['arms']['SWAP_SAME']['reformed_within_branch_share'], 1.0)
        self.assertEqual(v['arms']['SWAP_OTHER']['incumbent_price_reading'], 'PRICE_KEPT')
        self.assertTrue((run/'swaps.json').exists())
        table = facts(run)
        self.assertIn('Carrier reading (pre-registered, D-053)', table); self.assertIn('SWAP_SAME: reading (vs baseline)', table)
        self.assertIn('RE_FORMS', table)
        from figures.swaps import plot
        self.assertTrue(plot(run).exists())

    def test_missing_cells_are_listed(self):
        run = self.root/'cells'; shutil.copytree(self.root/'robust_cartel', run)
        tr = pd.read_csv(run/'trajectories.csv')
        tr = tr[~((tr.prefix_id == 0) & (tr.arm == 'SWAP_OTHER'))]                    # a missing cell
        tr.loc[(tr.prefix_id == 1) & (tr.arm == 'SWAP_SAME') & (tr.relative_period == 3), 'price'] = np.nan  # an incomplete one
        tr.to_csv(run/'trajectories.csv', index=False)
        v = analyze(run)['swaps']
        self.assertIn([0, 'SWAP_OTHER', 'missing cell'], v['excluded_incomplete_cells'])
        self.assertIn([1, 'SWAP_SAME', 'incomplete cell'], v['excluded_incomplete_cells'])
        self.assertEqual(v['arms']['SWAP_OTHER']['n_prefixes'], 5); self.assertEqual(v['arms']['SWAP_SAME']['n_prefixes'], 5)

    def test_probe_flags_without_a_placebo_arm(self):
        v = self.verdicts['robust_cartel']
        self.assertTrue(v['collusion_flag']); self.assertIn('D-053', v['collusion_flag_rule']); self.assertNotIn('placebo', v['collusion_flag_rule'])
        self.assertIn('in_swap_flag', v); self.assertTrue(v['in_swap_flag'])
        pc = v['paired_probe_comparisons']
        self.assertIn('swap_other_undercut_minus_swap_other_raise_signature', pc); self.assertIn('swap_other_undercut_minus_undercut_signature', pc)
        self.assertFalse(self.verdicts['leader_follower']['in_swap_flag'])   # a NashAgent newcomer is not punished: no signature

    def test_stage_one_check_is_the_delta_gate(self):
        r = check(self.root/'robust_cartel')
        self.assertEqual((r['status'], r['primary_for_stage_two'], r['gates']), ('PROCEED', 'SWAP_OTHER', {}))
        d = r['baseline_final_window_delta']; self.assertAlmostEqual(d['projected_lower_bound'], d['mean'] - r['gate_projection']['multiplier']*d['sd']/np.sqrt(3))
        self.assertEqual(check(self.root/'competitive_market')['status'], 'STOP_RUN_FALLBACK')
        run = self.root/'proceed'; shutil.copytree(self.root/'robust_cartel', run)
        write_json(run/'positive_control.json', check(run)); self.assertEqual(require_proceed(run)['status'], 'PROCEED')
        stop = self.root/'stop'; shutil.copytree(self.root/'competitive_market', stop)
        write_json(stop/'positive_control.json', check(stop))
        with self.assertRaises(SystemExit): require_proceed(stop)

    def test_records_are_checked_against_the_run(self):
        run = self.root/'record'; shutil.copytree(self.root/'robust_cartel', run)
        record = check(run); record['design_hash'] = '0'*64; write_json(run/'positive_control.json', record)
        with self.assertRaisesRegex(ValueError, 'different design'): analyze(run)
        (run/'positive_control.json').unlink()
        meta = json.loads((run/'metadata.json').read_text()); meta['synthetic'] = False; write_json(run/'metadata.json', meta)
        with self.assertRaisesRegex(ValueError, 'stage-one record'): analyze(run)
        with self.assertRaisesRegex(ValueError, 'disclosed screen'): analyze(self.root/'robust_cartel', primary='SWAP_OTHER')

    def test_budget_counts_and_providers(self):
        c = load_config(MAIN); e = c['experiment']; table = estimate(c, 0., 0.); B = e['branch_periods']; start = nested_start(c)
        by = table.groupby('provider').calls_no_retry.sum()
        # Newcomer calls on the alternate provider: SWAP_OTHER's B periods, plus each nested probe's B - start periods less its forced action.
        alt = e['prefixes']*(B + 2*(B - start - 1))
        self.assertEqual(int(by['cerebras']), alt); self.assertEqual(alt, 912)
        # baseline, SWAP_SAME, SWAP_BLIND: both firms; SWAP_OTHER, NOREGRET: the incumbent only; UNDERCUT, RAISE: both firms
        # less the forced action; the nested probes: the incumbent from the probe's fork.
        main = e['prefixes']*(2*e['max_prefix'] + B*(2*3 + 1 + 1 + 2*2) - 2 + 2*(B - start))
        self.assertEqual(int(by['anthropic']), main); self.assertEqual(int(table.calls_no_retry.sum()), 11904)
        blind = table[(table.arm == 'SWAP_BLIND') & (table.provider == 'anthropic')].mean_input_tokens.iloc[0]
        same = table[(table.arm == 'SWAP_SAME') & (table.provider == 'anthropic')].mean_input_tokens.iloc[0]
        self.assertLess(blind, same)   # the blind newcomer's prompts carry no pre-fork rows
        # The alternate adapter stamps its own prices, and the spend cap charges them.
        log = CallLogger(self.root/'spend.jsonl', {}, None, 25., (0.10, 0.50))
        log.add_spend({'prompt_tokens': 1_000_000, 'completion_tokens': 0}); self.assertAlmostEqual(log.spend, 0.10)
        log.add_spend({'prompt_tokens': 1_000_000, 'completion_tokens': 0, 'unit_prices': (0.35, 0.75)}); self.assertAlmostEqual(log.spend, 0.45)


class FakeAnthropic:
    def __init__(self): self.calls = 0; self.bodies = []
    def __call__(self, request, timeout):
        self.calls += 1; body = json.loads(request.data); self.bodies.append(body)
        required = body['output_config']['format']['schema']['required']
        content = json.dumps({'price': 1.75, 'notes': 'keep'} if 'notes' in required else {'price': 1.75})
        payload = {'id': 'm', 'type': 'message', 'role': 'assistant', 'model': body['model'], 'stop_reason': 'end_turn',
                   'content': [{'type': 'text', 'text': content}], 'usage': {'input_tokens': 500, 'output_tokens': 100}}
        class R(io.BytesIO):
            headers = {'request-id': 'req'}
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return R(json.dumps(payload).encode())


class FakeCerebras:
    def __init__(self): self.calls = 0; self.bodies = []
    def __call__(self, request, timeout):
        self.calls += 1; body = json.loads(request.data); self.bodies.append(body)
        required = body['response_format']['json_schema']['schema']['required']
        content = json.dumps({'price': 1.6, 'notes': 'new here'} if 'notes' in required else {'price': 1.6})
        payload = {'model': body['model'], 'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': content, 'reasoning': 'r'}}],
                   'usage': {'prompt_tokens': 700, 'completion_tokens': 200}}
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return R(json.dumps(payload).encode())


class LivePathTests(unittest.TestCase):
    def test_smoke_live_path_with_two_providers(self):
        c = load_config(MAIN); smoke_preset(c); c['experiment'].update(prefixes=1, max_prefix=12, workers=1)
        c['review'] = {k: True for k in c['review']}
        anthropic, cerebras = FakeAnthropic(), FakeCerebras()
        def adapter_for(llm):
            if llm['provider'] == 'anthropic': return AnthropicAdapter(llm, opener=anthropic, sleep=lambda s: None)
            return CerebrasAdapter(llm, opener=cerebras, sleep=lambda s: None)
        keys = {'ALLOW_LIVE_CALLS': '1', 'ANTHROPIC_API_KEY': 'sk-ant-fake-'+'9'*20, 'CEREBRAS_API_KEY': 'csk-fake-'+'8'*20}
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, keys), patch('run.fork.adapter_for', adapter_for):
            out = Path(d)/'live'; prefixes, tr, _ = execute(c, out, live=True)
            meta = json.loads((out/'metadata.json').read_text())
            self.assertEqual((meta['provider'], meta['model_id'], meta['alt_provider'], meta['alt_model_id']), ('anthropic', 'claude-haiku-5-5', 'cerebras', 'gpt-oss-120b'))
            k = int(prefixes.swapped_firm.iloc[0]); br = tr[tr.phase == 'branch']
            self.assertEqual(set(br[(br.arm == 'SWAP_OTHER') & (br.firm == k)].agent_kind), {'LLM:gpt-oss-120b:new'})
            self.assertEqual(set(br[(br.arm == 'SWAP_SAME') & (br.firm == k)].agent_kind), {'LLM:claude-haiku-5-5:new'})
            self.assertEqual(set(br[(br.arm == 'SWAP_OTHER') & (br.firm != k)].agent_kind), {'LLM:claude-haiku-5-5'})
            B, start = c['experiment']['branch_periods'], nested_start(c)
            self.assertEqual(cerebras.calls, B + 2*(B - start - 1))
            # Every row is a call, a forced action (four probes), a learner move (B) or a row copied from the parent (two probes).
            self.assertEqual(anthropic.calls + cerebras.calls, len(tr) - 4 - B - 2*2*start)
            # The other model's first request carries the firm's records but no notes.
            first = cerebras.bodies[0]; user = next(m['content'] for m in first['messages'] if m['role'] == 'user')
            self.assertIn('Your private notes from the previous period:\n(none)', user); self.assertIn('Completed periods (oldest first)', user)
            # A live staged run is not analysed without its stage-one record (D-051); the smoke is read by smoke_report.
            with self.assertRaisesRegex(ValueError, 'stage-one record'): analyze(out)
            meta['synthetic'] = True; write_json(out/'metadata.json', meta)
            analyze(out)
            v = json.loads((out/'verdict.json').read_text()); self.assertIn('swaps', v)
            for f in out.rglob('*'):
                if f.is_file():
                    text = f.read_text(errors='ignore')
                    for key in (keys['ANTHROPIC_API_KEY'], keys['CEREBRAS_API_KEY']): self.assertNotIn(key, text, f.name)


if __name__ == '__main__':
    unittest.main()
