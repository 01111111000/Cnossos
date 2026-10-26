import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from agents.llm import LLMAgent,OpenAIAdapter,AnthropicAdapter,ProviderError,strict_output,messages_for
from env.market import Market
from env.observations import build
LEGACY = "config/legacy_r2.yaml"  # the D-023..D-043 design, kept runnable (D-049)
from run.common import load_config,CallLogger,require_live


class ScriptedTransport:
    live=False
    def __init__(self,outputs): self.outputs=iter(outputs); self.calls=0
    def complete(self,messages):
        self.calls+=1; s=next(self.outputs)
        return s,json.dumps({'text':s}),{}


class LLMTests(unittest.TestCase):
    def setUp(self):
        self.c=load_config(LEGACY,synthetic=True); self.m=Market.from_config(self.c['market'])
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.log=Path(self.tmp.name)/'calls.jsonl'; self.logger=CallLogger(self.log,{})
    def run_agent(self,outputs,arm='baseline'):
        transport=ScriptedTransport(outputs); a=LLMAgent(self.c['llm'],transport,self.logger)
        result=a.act(build([],0,arm,self.m,self.c),self.m,0,1.23,{'arm':arm})
        return result,transport.calls
    def test_both_live_adapters_refuse_without_gate(self):
        with patch.dict(os.environ,{},clear=True):
            for klass in [OpenAIAdapter,AnthropicAdapter]:
                with self.assertRaisesRegex(RuntimeError,'locked'): klass(self.c['llm']).complete([])
    def test_llm_agent_gate_precedes_transport(self):
        with patch.dict(os.environ,{},clear=True):
            a=LLMAgent(self.c['llm'],OpenAIAdapter(self.c['llm']),self.logger)
            with self.assertRaisesRegex(RuntimeError,'locked'): a.act({},self.m,0,1.,{})
        self.assertFalse(self.log.exists())
    def test_run_gate_refuses_without_permission(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'locked'): require_live(self.c)
    def test_strict_json_schema(self):
        invalid=['{"price": true, "notes":""}','{"price":NaN,"notes":""}',
                 '{"price":1,"price":2,"notes":""}','{"price":1,"notes":"","extra":2}',
                 '{"price":20,"notes":""}','```json\n{"price":1,"notes":""}\n```',
                 '{"price":"1","notes":""}','[1,2]']
        for s in invalid:
            with self.subTest(s=s),self.assertRaises(ValueError): strict_output(s,True,self.m.bounds,1000)
    def test_valid_response_one_call_raw_logging(self):
        r,n=self.run_agent(['{"price":1.5,"notes":"memo"}'])
        self.assertEqual(r,{'price':1.5,'notes':'memo'}); self.assertEqual(n,1)
        log=json.loads(self.log.read_text()); self.assertIsNotNone(log['raw_output']); self.assertEqual(len(log['raw_input']),2)
    def test_one_retry_then_success(self):
        r,n=self.run_agent(['oops','{"price":1.5,"notes":""}'])
        self.assertEqual(n,2); self.assertEqual(r['price'],1.5)
        self.assertEqual(len(self.log.read_text().splitlines()),2)
    def test_double_failure_carries_previous(self):
        r,n=self.run_agent(['oops','{"price":-10,"notes":""}'])
        self.assertEqual(n,2); self.assertEqual(r['price'],1.23)
        self.assertTrue(json.loads(self.log.read_text().splitlines()[-1])['carried_previous'])
    def test_transport_failure_retries_same_request(self):
        class FailingOnce:
            live=False
            def __init__(self): self.sent=[]
            def complete(self,messages):
                self.sent.append(messages)
                if len(self.sent)==1: raise ProviderError('URLError')
                return '{"price":1.5,"notes":""}','{}',{}
        transport=FailingOnce(); a=LLMAgent(self.c['llm'],transport,self.logger)
        r=a.act(build([],0,'baseline',self.m,self.c),self.m,0,1.23,{'arm':'baseline'})
        self.assertEqual(r['price'],1.5); self.assertEqual(len(transport.sent),2)
        # No fabricated assistant turn or "previous response was invalid" message.
        self.assertEqual(transport.sent[1],transport.sent[0])
    def test_r3_no_notes_requested_or_accepted(self):
        obs=build([],0,'R3',self.m,self.c)
        self.assertNotIn('notes',json.dumps(messages_for(obs,self.c['llm'])))
        r,n=self.run_agent(['{"price":1.5}'],'R3'); self.assertEqual(n,1); self.assertEqual(r['notes'],'')
        with self.assertRaises(ValueError): strict_output('{"price":1.5,"notes":""}',False,self.m.bounds,1000)
