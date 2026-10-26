"""Anthropic adapter (D-052), offline. No network: the opener is a fake."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from agents.llm import AnthropicAdapter, LLMAgent, ProviderError, adapter_for, anthropic_schema, response_schema
from env.market import Market
from env.observations import build
from run.cli import execute, smoke_preset
from run.common import CallLogger, load_config
from tools.smoke_report import report

MAIN = 'config/main.yaml'
KEY = 'sk-ant-test-key-never-logged'


def reply(content, stop='end_turn', thinking='weighing the rival price', model='claude-haiku-5-5'):
    blocks = [{'type':'thinking','thinking':thinking,'signature':'sig'}] if thinking is not None else []
    if content is not None: blocks.append({'type':'text','text':content})
    return json.dumps({'id':'msg_1','type':'message','role':'assistant','model':model,'content':blocks,
                       'stop_reason':stop,'stop_sequence':None,
                       'usage':{'input_tokens':900,'output_tokens':300,'cache_creation_input_tokens':0,'cache_read_input_tokens':0}})


class FakeResponse(io.BytesIO):
    headers = {'request-id':'req_test'}
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FakeOpener:
    """Returns queued responses; an int queues an HTTP error with that status."""
    def __init__(self, *queue): self.queue=list(queue); self.requests=[]
    def __call__(self, request, timeout):
        self.requests.append(request)
        item=self.queue.pop(0)
        if isinstance(item,int):
            raise HTTPError(request.full_url,item,'error',{'Retry-After':'3'},io.BytesIO(b'{"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}'))
        return FakeResponse(item.encode())


class AnthropicTests(unittest.TestCase):
    def setUp(self):
        self.c=load_config(MAIN)
        self.m=Market.from_config(self.c['market'])
        self.messages=[{'role':'system','content':'s'},{'role':'user','content':'u'}]
        self.env={'ALLOW_LIVE_CALLS':'1','ANTHROPIC_API_KEY':KEY}

    def adapter(self, opener, sleeps=None):
        return AnthropicAdapter(self.c['llm'],opener=opener,sleep=(sleeps.append if sleeps is not None else lambda s:None))

    def test_main_config_selects_anthropic(self):
        self.assertEqual((self.c['llm']['provider'],self.c['llm']['model']),('anthropic','claude-haiku-5-5'))
        self.assertIsInstance(adapter_for(self.c['llm']),AnthropicAdapter)

    def test_refuses_without_live_permission_or_key(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'locked'): self.adapter(FakeOpener()).complete(self.messages)
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1'},clear=True):
            with self.assertRaisesRegex(RuntimeError,'ANTHROPIC_API_KEY'): self.adapter(FakeOpener()).complete(self.messages)

    def test_payload_endpoint_auth_and_documented_parameters(self):
        opener=FakeOpener(reply('{"price":1.8,"notes":"hold"}')); schema=response_schema(True,self.m.bounds)
        with patch.dict(os.environ,self.env,clear=True):
            text,raw,usage=self.adapter(opener).complete(self.messages,schema=schema,seed=7)
        req=opener.requests[0]; body=json.loads(req.data)
        self.assertEqual(req.full_url,'https://api.anthropic.com/v1/messages')
        self.assertEqual(req.get_header('X-api-key'),KEY); self.assertEqual(req.get_header('Anthropic-version'),'2023-06-01')
        self.assertEqual(body['model'],'claude-haiku-5-5'); self.assertEqual(body['system'],'s')
        self.assertEqual(body['messages'],[{'role':'user','content':'u'}])
        self.assertEqual(body['max_tokens'],self.c['llm']['max_output_tokens'])
        # Haiku 5.5 rejects any temperature but 1, top_p and top_k: none is sent. No seed parameter exists.
        for forbidden in ('temperature','top_p','top_k','seed','response_format','max_completion_tokens'):
            self.assertNotIn(forbidden,body)
        self.assertEqual(body['thinking'],{'type':'adaptive','display':'summarized'})
        self.assertEqual(body['output_config']['effort'],'medium')
        fmt=body['output_config']['format']; self.assertEqual(fmt['type'],'json_schema')
        self.assertEqual(fmt['schema']['required'],['price','notes']); self.assertFalse(fmt['schema']['additionalProperties'])
        self.assertNotIn('minimum',fmt['schema']['properties']['price'])   # not supported by the API
        self.assertIn('between 0.0 and 4.0',fmt['schema']['properties']['price']['description'])
        self.assertEqual(text,'{"price":1.8,"notes":"hold"}')
        self.assertEqual((usage['prompt_tokens'],usage['completion_tokens']),(900,300))  # the spend cap's names
        self.assertEqual((usage['input_tokens'],usage['finish_reason'],usage['backoffs'],usage['request_id']),(900,'end_turn',0,'req_test'))
        self.assertEqual(usage['requested_seed'],7); self.assertGreater(usage['thinking_chars'],0)
        self.assertNotIn(KEY,raw+json.dumps(usage))

    def test_non_default_temperature_would_be_sent_and_schema_bounds_stay_enforced(self):
        a=AnthropicAdapter({**self.c['llm'],'temperature':0.7})
        self.assertEqual(a.payload(self.messages)['temperature'],0.7)
        with patch.dict(os.environ,self.env,clear=True):
            text,_,_=self.adapter(FakeOpener(reply('{"price":9.5,"notes":"x"}'))).complete(self.messages,schema=response_schema(True,self.m.bounds))
        from agents.llm import strict_output
        with self.assertRaisesRegex(ValueError,'Invalid price'): strict_output(text,True,self.m.bounds,800)

    def test_truncation_refusal_and_empty_output_raise_with_paid_usage(self):
        for body,pattern in ((reply('{"pri',stop='max_tokens'),'Truncated'),(reply('I cannot help',stop='refusal'),'Refusal'),
                             (reply(None),'empty')):
            with patch.dict(os.environ,self.env,clear=True):
                with self.assertRaisesRegex(ProviderError,pattern) as cm: self.adapter(FakeOpener(body)).complete(self.messages)
            self.assertEqual(cm.exception.usage['completion_tokens'],300)

    def test_transient_errors_back_off_and_honour_retry_after(self):
        sleeps=[]; opener=FakeOpener(529,429,reply('{"price":1.5}'))
        with patch.dict(os.environ,self.env,clear=True):
            text,_,usage=self.adapter(opener,sleeps).complete(self.messages)
        self.assertEqual((text,usage['backoffs'],len(opener.requests)),('{"price":1.5}',2,3))
        self.assertEqual(sleeps,[3.0,4.0])   # max(backoff, Retry-After) then 2 * 2
        with patch.dict(os.environ,self.env,clear=True):
            with self.assertRaisesRegex(ProviderError,'HTTP 400'): self.adapter(FakeOpener(400)).complete(self.messages)

    def test_agent_retries_once_then_carries(self):
        obs=build([],0,'baseline',self.m,self.c)
        with tempfile.TemporaryDirectory() as d:
            log=CallLogger(Path(d)/'calls.jsonl',{'provider':'anthropic'},None,25.,(0.10,0.50))
            opener=FakeOpener(reply('{"price":"bad"}'),reply('{"price":1.6,"notes":"ok"}'))
            with patch.dict(os.environ,self.env,clear=True):
                r=LLMAgent(self.c['llm'],self.adapter(opener),log).act(obs,self.m,0,1.4,{'seed':1,'phase':'prefix','period':0,'firm':0})
            self.assertEqual(r['price'],1.6)
            retry=json.loads(opener.requests[1].data)['messages']
            self.assertEqual([m['role'] for m in retry],['user','assistant','user'])  # ends with a user turn: no prefill
            opener=FakeOpener(reply('{"price":9}'),reply('{"price":9}'))
            with patch.dict(os.environ,self.env,clear=True):
                r=LLMAgent(self.c['llm'],self.adapter(opener),log).act(obs,self.m,0,1.4,{'seed':1,'phase':'prefix','period':1,'firm':0})
            self.assertTrue(r.get('carried')); self.assertEqual(r['price'],1.4)
            lines=[json.loads(l) for l in (Path(d)/'calls.jsonl').read_text().splitlines()]
            self.assertEqual(len(lines),4); self.assertNotIn(KEY,(Path(d)/'calls.jsonl').read_text())


class FakeAnthropic:
    """HTTP stand-in for api.anthropic.com: answers the schema it is sent."""
    def __init__(self): self.calls=0
    def __call__(self, request, timeout):
        self.calls+=1; body=json.loads(request.data)
        required=body['output_config']['format']['schema']['required']
        content=json.dumps({'price':1.75,'notes':'keep'} if 'notes' in required else {'price':1.75})
        return FakeResponse(reply(content,model=body['model']).encode())


class LivePathTests(unittest.TestCase):
    def test_smoke_live_path_end_to_end_with_fake_anthropic(self):
        # The smoke preset (2 prefixes x 100 periods, 12 branch periods), shrunk to one 12-period prefix, on the
        # single-provider screen design; the two-provider replacement design is covered by tests/test_swaps.py.
        c=load_config('config/screens.yaml'); smoke_preset(c); c['experiment'].update(prefixes=1,max_prefix=12,workers=1)
        c['review']={k:True for k in c['review']}
        opener=FakeAnthropic(); key='sk-ant-fake-'+'9'*20
        with tempfile.TemporaryDirectory() as d, \
             patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','ANTHROPIC_API_KEY':key}), \
             patch('run.fork.adapter_for',lambda llm: AnthropicAdapter(llm,opener=opener,sleep=lambda s:None)):
            out=Path(d)/'live'; prefixes,tr,comp=execute(c,out,live=True)
            meta=json.loads((out/'metadata.json').read_text())
            self.assertEqual((meta['provider'],meta['model_id'],meta['synthetic']),('anthropic','claude-haiku-5-5',False))
            self.assertEqual(set(tr.agent_kind),{'LLM:claude-haiku-5-5'})
            r=report(out); self.assertEqual(r['status'],'PASS'); self.assertEqual(r['decisions'],opener.calls)
            self.assertEqual(r['models_reported'],['claude-haiku-5-5']); self.assertEqual(r['mean_completion_tokens'],300.)
            for f in out.rglob('*'):
                if f.is_file(): self.assertNotIn(key,f.read_text(errors='ignore'),f.name)


if __name__=='__main__':
    unittest.main()
