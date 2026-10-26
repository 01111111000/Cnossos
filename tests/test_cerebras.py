"""Cerebras adapter and LLM-agent contract, offline. No network: the opener is a fake."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from agents.llm import (CerebrasAdapter, LLMAgent, ProviderError, adapter_for, request_seed,
                        response_schema, strict_output)
from env.market import Market
from env.observations import build
LEGACY = "config/legacy_r2.yaml"  # the D-023..D-043 design, kept runnable (D-049)
from run.common import CallLogger, CircuitBreakerTripped, load_config

KEY = 'csk-test-key-never-logged'


def reply(content, finish='stop', reasoning='thinking'):
    return json.dumps({'id':'x','model':'gpt-oss-120b','system_fingerprint':'fp',
        'choices':[{'index':0,'finish_reason':finish,'message':{'role':'assistant','content':content,'reasoning':reasoning}}],
        'usage':{'prompt_tokens':900,'completion_tokens':300,'total_tokens':1200,
                 'prompt_tokens_details':{'cached_tokens':640},'completion_tokens_details':{'reasoning_tokens':250}},
        'time_info':{'total_time':0.4}})


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FakeOpener:
    """Returns queued responses; an int queues an HTTP error with that status."""
    def __init__(self, *queue): self.queue=list(queue); self.requests=[]
    def __call__(self, request, timeout):
        self.requests.append(request)
        item=self.queue.pop(0)
        if isinstance(item,int):
            raise HTTPError(request.full_url,item,'error',{},io.BytesIO(b'{"error":"rate limited"}'))
        return FakeResponse(item.encode())


class CerebrasTests(unittest.TestCase):
    def setUp(self):
        self.c=load_config(LEGACY)  # the proposed live configuration, but with no live permission
        self.m=Market.from_config(self.c['market'])
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.log=Path(self.tmp.name)/'calls.jsonl'
        self.messages=[{'role':'system','content':'s'},{'role':'user','content':'u'}]

    def adapter(self, opener, sleeps=None):
        return CerebrasAdapter(self.c['llm'],opener=opener,sleep=(sleeps.append if sleeps is not None else lambda s:None))

    def test_refuses_without_live_permission(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'locked'): self.adapter(FakeOpener()).complete(self.messages)

    def test_missing_key(self):
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1'},clear=True):
            with self.assertRaisesRegex(RuntimeError,'CEREBRAS_API_KEY'): self.adapter(FakeOpener()).complete(self.messages)

    def test_payload_endpoint_and_auth(self):
        opener=FakeOpener(reply('{"price":1.8,"notes":"hold"}'))
        schema=response_schema(True,self.m.bounds)
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','CEREBRAS_API_KEY':KEY},clear=True):
            text,raw,usage=self.adapter(opener).complete(self.messages,schema=schema,seed=7)
        req=opener.requests[0]; body=json.loads(req.data)
        self.assertEqual(req.full_url,'https://api.cerebras.ai/v1/chat/completions')
        self.assertEqual(req.get_header('Authorization'),'Bearer '+KEY)
        # D-058: an explicit User-Agent, since Cerebras's edge rejects urllib's default with 403/1010.
        self.assertEqual(req.get_header('User-agent'),'apart-collusion-harness/1.0')
        self.assertEqual(body['model'],'gpt-oss-120b'); self.assertEqual(body['reasoning_effort'],'low')
        self.assertEqual(body['max_completion_tokens'],self.c['llm']['max_output_tokens'])
        self.assertNotIn('max_tokens',body); self.assertEqual(body['seed'],7)
        self.assertEqual(body['response_format'],schema)
        self.assertEqual(text,'{"price":1.8,"notes":"hold"}')
        self.assertEqual(usage['completion_tokens_details']['reasoning_tokens'],250)
        self.assertEqual(usage['backoffs'],0)
        self.assertNotIn(KEY,raw+json.dumps(usage))

    def test_schema_is_strict(self):
        s=response_schema(True,(0.,4.))['json_schema']
        self.assertTrue(s['strict']); self.assertFalse(s['schema']['additionalProperties'])
        self.assertEqual(s['schema']['required'],['price','notes'])
        self.assertEqual(s['schema']['properties']['price'],{'type':'number','minimum':0.,'maximum':4.})
        self.assertEqual(response_schema(False,(0.,4.))['json_schema']['schema']['required'],['price'])

    def test_rate_limit_backoff_then_success(self):
        sleeps=[]; opener=FakeOpener(429,503,reply('{"price":1.7}'))
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','CEREBRAS_API_KEY':KEY},clear=True):
            text,_,usage=self.adapter(opener,sleeps).complete(self.messages)
        self.assertEqual(text,'{"price":1.7}'); self.assertEqual(usage['backoffs'],2); self.assertEqual(sleeps,[2.0,4.0])

    def test_persistent_rate_limit_reports_status(self):
        opener=FakeOpener(*[429]*(self.c['llm']['rate_limit_retries']+1))
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','CEREBRAS_API_KEY':KEY},clear=True):
            with self.assertRaises(ProviderError) as ctx: self.adapter(opener).complete(self.messages)
        self.assertEqual(str(ctx.exception),'HTTP 429'); self.assertEqual(json.loads(ctx.exception.raw)['status'],429)

    def test_non_retryable_status_fails_fast(self):
        opener=FakeOpener(400)
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','CEREBRAS_API_KEY':KEY},clear=True):
            with self.assertRaisesRegex(ProviderError,'HTTP 400'): self.adapter(opener).complete(self.messages)
        self.assertEqual(len(opener.requests),1)

    def test_truncated_output_is_a_failure(self):
        opener=FakeOpener(reply(None,finish='length'))
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','CEREBRAS_API_KEY':KEY},clear=True):
            with self.assertRaisesRegex(ProviderError,'finish_reason=length'): self.adapter(opener).complete(self.messages)

    def test_retry_uses_a_new_seed(self):
        opener=FakeOpener(reply('not json'),reply('{"price":1.7,"notes":""}'))
        agent=LLMAgent(self.c['llm'],self.adapter(opener),CallLogger(self.log,{}))
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','CEREBRAS_API_KEY':KEY},clear=True):
            agent.act(build([],0,'baseline',self.m,self.c),self.m,0,1.5,{'arm':'baseline','phase':'prefix','period':0,'firm':0,'seed':1})
        seeds=[json.loads(r.data)['seed'] for r in opener.requests]
        self.assertEqual(seeds[1],seeds[0]+1)

    def test_truncated_output_counts_towards_spend(self):
        opener=FakeOpener(*[reply(None,finish='length')]*2)
        logger=CallLogger(self.log,{},spend_cap=100.,prices=(0.35,0.75))
        agent=LLMAgent(self.c['llm'],self.adapter(opener),logger)
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','CEREBRAS_API_KEY':KEY},clear=True):
            out=agent.act(build([],0,'baseline',self.m,self.c),self.m,0,1.5,{'arm':'baseline'})
        self.assertTrue(out['carried']); self.assertAlmostEqual(logger.spend,2*(900*0.35+300*0.75)/1e6)
        self.assertEqual(json.loads(self.log.read_text().splitlines()[0])['usage']['prompt_tokens'],900)

    def test_retry_after_and_incomplete_read(self):
        import http.client
        class Opener(FakeOpener):
            def __call__(self, request, timeout):
                self.requests.append(request); item=self.queue.pop(0)
                if item=='incomplete': raise http.client.IncompleteRead(b'')
                if item==429: raise HTTPError(request.full_url,429,'slow',{'Retry-After':'7'},io.BytesIO(b''))
                return FakeResponse(item.encode())
        sleeps=[]; opener=Opener('incomplete',429,reply('{"price":1.7}'))
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','CEREBRAS_API_KEY':KEY},clear=True):
            text,_,usage=self.adapter(opener,sleeps).complete(self.messages)
        self.assertEqual(text,'{"price":1.7}'); self.assertEqual(sleeps,[2.0,7.0]); self.assertEqual(usage['backoffs'],2)

    def test_adapter_selection(self):
        self.assertIsInstance(adapter_for(self.c['llm']),CerebrasAdapter)

    def test_request_seed_shared_across_arms(self):
        base={'seed':5,'phase':'branch','period':103,'firm':1}
        self.assertEqual(request_seed({**base,'arm':'baseline'}),request_seed({**base,'arm':'R2'}))
        self.assertNotEqual(request_seed(base),request_seed({**base,'firm':0}))

    def test_agent_end_to_end_with_fake_provider(self):
        opener=FakeOpener(reply('{"price":1.85,"notes":"'+'n'*900+'"}'))
        logger=CallLogger(self.log,{'provider':'cerebras'})
        agent=LLMAgent(self.c['llm'],self.adapter(opener),logger)
        obs=build([],0,'baseline',self.m,self.c)
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','CEREBRAS_API_KEY':KEY},clear=True):
            out=agent.act(obs,self.m,0,1.47,{'arm':'baseline','phase':'prefix','period':0,'firm':0,'seed':3})
        self.assertEqual(out['price'],1.85); self.assertEqual(len(out['notes']),self.c['llm']['notes_max_chars'])
        entry=json.loads(self.log.read_text())
        self.assertTrue(entry['notes_truncated']); self.assertEqual(entry['observation'],json.loads(json.dumps(obs)))
        self.assertNotIn(KEY,self.log.read_text())

    def test_notes_overflow_policy(self):
        with self.assertRaises(ValueError): strict_output('{"price":1,"notes":"abcdef"}',True,(0,4),3)
        self.assertEqual(strict_output('{"price":1,"notes":"abcdef"}',True,(0,4),3,'truncate')['notes'],'abc')

    def test_carry_keeps_previous_notes(self):
        class Bad:
            live=False
            def complete(self,messages): return 'not json','{}',{}
        h=[{'period':0,'prices':[1.5,1.5],'quantities':[40.,40.],'profits':[20.,20.],'notes':['plan A','x']}]
        agent=LLMAgent(self.c['llm'],Bad(),CallLogger(self.log,{}))
        out=agent.act(build(h,0,'baseline',self.m,self.c),self.m,0,1.5,{'arm':'baseline'})
        self.assertEqual(out,{'price':1.5,'notes':'plan A','carried':True})

    def test_circuit_breaker_stops_run(self):
        class Down:
            live=False
            def complete(self,messages): raise ProviderError('HTTP 503')
        logger=CallLogger(self.log,{},max_consecutive_carries=2)
        agent=LLMAgent(self.c['llm'],Down(),logger); obs=build([],0,'baseline',self.m,self.c)
        agent.act(obs,self.m,0,1.5,{'arm':'baseline'})
        with self.assertRaises(CircuitBreakerTripped): agent.act(obs,self.m,0,1.5,{'arm':'baseline'})


MODAL='https://example--llm-gptoss120b-serve.us-east.modal.run/v1'
TOKEN='modal-test-token-never-logged'


def vllm_reply(content, field='reasoning_content', finish='stop'):
    """A vLLM gpt-oss reply: served model name, reasoning in `reasoning_content` or `reasoning`, no time_info."""
    return json.dumps({'id':'v','model':'openai/gpt-oss-120b',
        'choices':[{'index':0,'finish_reason':finish,'message':{'role':'assistant','content':content,field:'think'*3}}],
        'usage':{'prompt_tokens':800,'completion_tokens':120,'total_tokens':920,'prompt_tokens_details':None}})


class EndpointOverrideTests(unittest.TestCase):
    """D-060: an environment override sends the Cerebras adapter's requests to a vLLM endpoint."""
    def setUp(self):
        self.c=load_config(LEGACY); self.m=Market.from_config(self.c['market'])
        self.messages=[{'role':'system','content':'s'},{'role':'user','content':'u'}]
        self.env={'ALLOW_LIVE_CALLS':'1','OPENAI_COMPAT_BASE_URL':MODAL+'/','OPENAI_COMPAT_MODEL':'openai/gpt-oss-120b',
                  'OPENAI_COMPAT_API_KEY':' '+TOKEN+'\r\n'}

    def test_request_goes_to_the_override_endpoint(self):
        opener=FakeOpener(vllm_reply('{"price":1.8,"notes":"hold"}'))
        schema=response_schema(True,self.m.bounds)
        with patch.dict(os.environ,self.env,clear=True):
            text,raw,usage=CerebrasAdapter(self.c['llm'],opener=opener).complete(self.messages,schema=schema,seed=7)
        req=opener.requests[0]; body=json.loads(req.data)
        self.assertEqual(req.full_url,MODAL+'/chat/completions')
        self.assertEqual(req.get_header('Authorization'),'Bearer '+TOKEN)
        self.assertEqual(req.get_header('User-agent'),'apart-collusion-harness/1.0')
        self.assertEqual(body['model'],'openai/gpt-oss-120b'); self.assertNotIn('reasoning_format',body)
        self.assertEqual(body['reasoning_effort'],'low'); self.assertEqual(body['seed'],7)
        self.assertEqual(body['response_format'],schema)
        self.assertEqual(body['max_completion_tokens'],self.c['llm']['max_output_tokens'])
        self.assertEqual(text,'{"price":1.8,"notes":"hold"}')
        self.assertEqual(usage['endpoint_host'],'example--llm-gptoss120b-serve.us-east.modal.run')
        self.assertEqual(usage['served_model'],'openai/gpt-oss-120b'); self.assertEqual(usage['model'],'openai/gpt-oss-120b')
        self.assertEqual(usage['reasoning_chars'],15); self.assertEqual(usage['completion_tokens'],120)
        self.assertNotIn(TOKEN,raw+json.dumps(usage))

    def test_reasoning_field_is_accepted_too(self):
        opener=FakeOpener(vllm_reply('{"price":1.7}',field='reasoning'))
        with patch.dict(os.environ,self.env,clear=True):
            _,_,usage=CerebrasAdapter(self.c['llm'],opener=opener).complete(self.messages)
        self.assertEqual(usage['reasoning_chars'],15)

    def test_without_override_nothing_changes(self):
        opener=FakeOpener(reply('{"price":1.8}'))
        with patch.dict(os.environ,{'ALLOW_LIVE_CALLS':'1','CEREBRAS_API_KEY':KEY},clear=True):
            _,_,usage=CerebrasAdapter(self.c['llm'],opener=opener).complete(self.messages)
        body=json.loads(opener.requests[0].data)
        self.assertEqual(opener.requests[0].full_url,'https://api.cerebras.ai/v1/chat/completions')
        self.assertEqual(body['model'],'gpt-oss-120b'); self.assertEqual(body['reasoning_format'],'parsed')
        for k in ('endpoint_host','served_model','reasoning_chars'): self.assertNotIn(k,usage)

    def test_half_an_override_or_no_token_is_refused(self):
        for env in ({'ALLOW_LIVE_CALLS':'1','OPENAI_COMPAT_BASE_URL':MODAL,'CEREBRAS_API_KEY':KEY},
                    {'ALLOW_LIVE_CALLS':'1','OPENAI_COMPAT_MODEL':'openai/gpt-oss-120b','CEREBRAS_API_KEY':KEY}):
            with patch.dict(os.environ,env,clear=True):
                with self.assertRaisesRegex(RuntimeError,'Set both'): CerebrasAdapter(self.c['llm'],opener=FakeOpener()).complete(self.messages)
        env={**self.env,'CEREBRAS_API_KEY':KEY}; env.pop('OPENAI_COMPAT_API_KEY')
        with patch.dict(os.environ,env,clear=True):
            with self.assertRaisesRegex(RuntimeError,'OPENAI_COMPAT_API_KEY'): CerebrasAdapter(self.c['llm'],opener=FakeOpener()).complete(self.messages)

    def test_metadata_records_the_override(self):
        from run.common import metadata
        # metadata() runs git, which needs the system's search path.
        system={k:v for k,v in os.environ.items() if k.upper() in ('PATH','PATHEXT','SYSTEMROOT','COMSPEC')}
        with patch.dict(os.environ,{**system,**self.env},clear=True):
            meta=metadata(self.c,live=True)
        self.assertEqual(meta['endpoint_override'],{'replaces_provider':'cerebras',
            'host':'example--llm-gptoss120b-serve.us-east.modal.run','served_model':'openai/gpt-oss-120b'})
        self.assertNotIn(TOKEN,json.dumps(meta))
        with patch.dict(os.environ,system,clear=True):
            self.assertNotIn('endpoint_override',metadata(self.c,live=True))


class StopTests(unittest.TestCase):
    def test_worker_failure_stops_other_workers(self):
        c=load_config(LEGACY); m=Market.from_config(c['market'])
        with tempfile.TemporaryDirectory() as d:
            logger=CallLogger(Path(d)/'calls.jsonl',{})
            logger.stop(RuntimeError('worker 1 crashed'))
            class Never:
                live=False
                def complete(self,messages): raise AssertionError('no request may be sent after a stop')
            with self.assertRaisesRegex(RuntimeError,'worker 1 crashed'):
                LLMAgent(c['llm'],Never(),logger).act(build([],0,'baseline',m,c),m,0,1.5,{'arm':'baseline'})


class SpendCapTests(unittest.TestCase):
    def test_spend_cap_stops_every_worker(self):
        c=load_config(LEGACY); m=Market.from_config(c['market'])
        with tempfile.TemporaryDirectory() as d:
            logger=CallLogger(Path(d)/'calls.jsonl',{},spend_cap=0.001,prices=(0.35,0.75))
            class Costly:
                live=False
                def complete(self,messages): return '{"price":1.8,"notes":""}','{}',{'prompt_tokens':2000,'completion_tokens':800}
            agent=LLMAgent(c['llm'],Costly(),logger); obs=build([],0,'baseline',m,c)
            with self.assertRaisesRegex(CircuitBreakerTripped,'cap'): agent.act(obs,m,0,1.5,{'arm':'baseline'})
            other=LLMAgent(c['llm'],Costly(),logger)  # another worker sharing the run logger
            with self.assertRaisesRegex(CircuitBreakerTripped,'cap'): other.act(obs,m,1,1.5,{'arm':'baseline'})
            # The call that crossed the cap is logged; the second worker never sends a request.
            self.assertEqual(len((Path(d)/'calls.jsonl').read_text().splitlines()),1)


if __name__=='__main__':
    unittest.main()
