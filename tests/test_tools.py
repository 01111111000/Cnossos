"""Smoke qualification report and facts table, on runs produced offline."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from agents.llm import LLMAgent
from analysis.pipeline import analyze
from run.cli import execute
LEGACY = "config/legacy_r2.yaml"  # the D-023..D-043 design, kept runnable (D-049)
from run.common import load_config
from tools.facts import facts
from tools.smoke_report import report


class Scripted:
    """Stands in for the provider: valid JSON except every `bad_every`-th call."""
    live=False
    def __init__(self, bad_every=None): self.n=0; self.bad_every=bad_every
    def complete(self, messages):
        self.n+=1
        usage={'prompt_tokens':1000,'completion_tokens':300,'completion_tokens_details':{'reasoning_tokens':200},
               'prompt_tokens_details':{'cached_tokens':500},'finish_reason':'stop','model':'gpt-oss-120b',
               'time_info':{'total_time':0.5},'backoffs':0}
        if self.bad_every and self.n % self.bad_every == 0: return 'not json', '{}', usage
        notes=any('"notes"' in m['content'] for m in messages)
        body={'price':1.8,'notes':'hold'} if notes else {'price':1.8}
        return json.dumps(body), '{}', usage


def small_live_like_config():
    c=load_config(LEGACY)  # the real market and interface, offline
    c['experiment'].update(prefixes=2,max_prefix=12,branch_periods=12,workers=1)
    c['competence'].update(periods=10,shock_at=5)
    return c


def run_with(transport_factory, out):
    maker=lambda c,kind,seed,logger,live: LLMAgent(c['llm'],transport_factory(),logger)
    with patch('run.fork.make_agent',maker), patch('run.competence.make_agent',maker):
        return execute(small_live_like_config(),out)


class ToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.root=Path(cls.tmp.name)
        run_with(lambda: Scripted(bad_every=40),cls.root/'ok')
        run_with(lambda: Scripted(bad_every=1),cls.root/'broken')
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_smoke_report_passes_healthy_run(self):
        r=report(self.root/'ok')
        self.assertEqual(r['status'],'PASS'); self.assertEqual(r['carried_decision_rate'],0.)
        self.assertLess(r['first_attempt_valid_rate'],1.); self.assertEqual(r['valid_decision_rate'],1.)
        self.assertEqual(r['mean_completion_tokens'],300.); self.assertEqual(r['mean_reasoning_tokens'],200.)
        self.assertEqual(r['models_reported'],['gpt-oss-120b']); self.assertAlmostEqual(r['cached_prompt_share'],.5)
        self.assertEqual(r['rerun_budget_with'],'make budget OUTPUT_TOKENS=300')
        self.assertEqual(set(r['descriptive_only_prefix_delta']),{0,1})

    def test_smoke_report_fails_broken_run(self):
        r=report(self.root/'broken')
        self.assertEqual(r['status'],'FAIL'); self.assertFalse(r['checks']['valid']); self.assertEqual(r['carried_decision_rate'],1.)

    def test_smoke_report_counts_decisions_not_attempts(self):
        r=report(self.root/'ok'); calls=[json.loads(x) for x in (self.root/'ok'/'calls.jsonl').read_text().splitlines()]
        llm=[d for d in calls if 'carried_previous' in d and not d.get('forced')]
        self.assertEqual(r['attempts'],len(llm)); self.assertLess(r['decisions'],r['attempts'])

    def test_facts_table_cites_files(self):
        analyze(self.root/'ok'); table=facts(self.root/'ok')
        self.assertIn('| Primary status |',table); self.assertIn('verdict.json:primary',table)
        self.assertIn('summary.csv',table)
        self.assertIn('SYNTHETIC',table)  # an offline run is flagged from metadata, whatever its agents
        self.assertLess(table.index('| baseline: Delta'),table.index('| R1: Delta'))
        self.assertIn('SHAM removal',table); self.assertIn('Placebo matched-cut rate',table)


class FakeCerebras:
    """HTTP stand-in for api.cerebras.ai: answers the schema it is sent."""
    def __init__(self): self.calls=0
    def __call__(self, request, timeout):
        import io
        self.calls+=1; body=json.loads(request.data)
        required=body['response_format']['json_schema']['schema']['required']
        content=json.dumps({'price':1.75,'notes':'keep'} if 'notes' in required else {'price':1.75})
        payload={'model':body['model'],'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':content,'reasoning':'r'}}],
                 'usage':{'prompt_tokens':800,'completion_tokens':250,'completion_tokens_details':{'reasoning_tokens':180}}}
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self,*a): return False
        return R(json.dumps(payload).encode())


class LivePathTests(unittest.TestCase):
    def test_live_path_end_to_end_with_fake_cerebras(self):
        from agents.llm import CerebrasAdapter
        import os
        c=small_live_like_config(); c['review']={k:True for k in c['review']}
        opener=FakeCerebras(); key='csk-fake-'+'9'*20
        with tempfile.TemporaryDirectory() as d, \
             patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','CEREBRAS_API_KEY':key}), \
             patch('run.fork.adapter_for',lambda llm: CerebrasAdapter(llm,opener=opener,sleep=lambda s:None)):
            out=Path(d)/'live'; prefixes,tr,comp=execute(c,out,live=True)
            meta=json.loads((out/'metadata.json').read_text())
            self.assertEqual((meta['provider'],meta['model_id'],meta['synthetic']),('cerebras','gpt-oss-120b',False))
            self.assertEqual(set(tr[tr.arm!='NOREGRET'].agent_kind),{'LLM:gpt-oss-120b'})
            r=report(out); self.assertEqual(r['status'],'PASS'); self.assertEqual(r['decisions'],opener.calls)
            analyze(out); self.assertIn('primary',json.loads((out/'verdict.json').read_text()))
            for f in out.rglob('*'):
                if f.is_file(): self.assertNotIn(key,f.read_text(errors='ignore'),f.name)

    def test_live_path_refused_until_review_flags(self):
        import os
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1'}):
            with self.assertRaisesRegex(RuntimeError,'Resolve'): execute(small_live_like_config(),Path(d)/'x',live=True)


if __name__=='__main__':
    unittest.main()
