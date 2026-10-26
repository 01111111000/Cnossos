"""REST adapters are guarded twice. Unit tests use a non-live scripted transport.

Anthropic (D-052) is the main provider. Facts used here were read from platform.claude.com/docs
on 2026-10-20 (Messages API, structured outputs, thinking, effort, errors, Haiku 5.5 migration
guide): POST https://api.anthropic.com/v1/messages with x-api-key and anthropic-version
2023-06-01; `system` is a top-level string; `max_tokens` is required and thinking tokens count
towards it and are billed as output; adaptive thinking is on by default on Claude Haiku 5.5 and
`thinking: {type: adaptive, display: summarized}` returns a summary of it; depth is steered by
`output_config.effort` (low/medium/high); `output_config.format` {type: json_schema, schema}
constrains the reply (no numeric minimum/maximum, additionalProperties must be false); Haiku 5.5
rejects temperature != 1, top_p, top_k and prefilled assistant turns; `stop_reason` is end_turn,
max_tokens or refusal; usage reports input_tokens and output_tokens; 429 (retry-after) and 529
are transient. There is no seed parameter.

Cerebras (D-024, now the alternate provider) exposes an OpenAI-compatible chat-completions
endpoint. Facts used here were read from inference-docs.cerebras.ai on 2026-10-16:
POST https://api.cerebras.ai/v1/chat/completions, Bearer CEREBRAS_API_KEY, reasoning returned
separately in choices[0].message.reasoning and counted in max_completion_tokens, strict
json_schema response_format supported for gpt-oss-120b, 429 on rate limit.

D-060: an environment override (OPENAI_COMPAT_BASE_URL, OPENAI_COMPAT_MODEL, OPENAI_COMPAT_API_KEY)
sends the Cerebras adapter's requests to another OpenAI-compatible endpoint serving the same model
(a self-hosted vLLM on Modal). The configuration is unchanged; the endpoint host and served model are
stamped into metadata.json and every call's usage. vLLM returns reasoning in message.reasoning or
message.reasoning_content; the decision is read from message.content in both cases.
"""
import hashlib
import http.client
import json
import math
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from env.observations import render

KEY_NAMES = {'openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY','cerebras':'CEREBRAS_API_KEY'}
URLS = {'openai':'https://api.openai.com/v1/chat/completions',
        'anthropic':'https://api.anthropic.com/v1/messages',
        'cerebras':'https://api.cerebras.ai/v1/chat/completions'}
RETRYABLE_STATUS = {429, 500, 502, 503, 504, 529}
# D-058: Cerebras's edge (Cloudflare) answers HTTP 403, error code 1010, to urllib's default
# User-Agent ("Python-urllib/3.x"). The successful smoke used an explicit User-Agent
# (D-058). The header changes nothing in the request body.
USER_AGENT = 'apart-collusion-harness/1.0'
OVERRIDE_URL, OVERRIDE_MODEL, OVERRIDE_KEY = 'OPENAI_COMPAT_BASE_URL', 'OPENAI_COMPAT_MODEL', 'OPENAI_COMPAT_API_KEY'


def endpoint_override():
    """D-060: the OpenAI-compatible endpoint that replaces Cerebras for this process, or None.
    The base URL and the served model name are set together or not at all."""
    base, model = os.environ.get(OVERRIDE_URL, '').strip(), os.environ.get(OVERRIDE_MODEL, '').strip()
    if not base and not model: return None
    if not (base and model): raise RuntimeError(f'Set both {OVERRIDE_URL} and {OVERRIDE_MODEL}, or neither')
    return {'url': base.rstrip('/')+'/chat/completions', 'host': urlparse(base).hostname, 'served_model': model}


def guard():
    if os.environ.get('ALLOW_LIVE_CALLS') != '1':
        raise RuntimeError('Live calls locked: ALLOW_LIVE_CALLS=1 is required')


class ProviderError(RuntimeError):
    def __init__(self, message, raw=None, usage=None):
        super().__init__(message)
        self.raw = raw
        self.usage = usage or {}


def response_schema(with_notes, bounds):
    """Strict JSON schema for one decision. Notes length is enforced by our own parser."""
    properties = {'price': {'type':'number','minimum':float(bounds[0]),'maximum':float(bounds[1])}}
    required = ['price']
    if with_notes:
        properties['notes'] = {'type':'string'}; required.append('notes')
    return {'type':'json_schema','json_schema':{'name':'pricing_decision','strict':True,
            'schema':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}}


class RESTAdapter:
    """Minimal OpenAI chat-completions transport, kept for the `openai` provider option only."""
    live = True
    accepts_options = False
    def __init__(self, config):
        self.c = config
    def complete(self, messages):
        guard()
        provider = self.c['provider']
        key = os.environ.get(KEY_NAMES[provider])
        if not key: raise RuntimeError(f'Missing {KEY_NAMES[provider]}')
        payload = {'model':self.c['model'], 'temperature':self.c['temperature'],
                   'messages':messages, 'max_completion_tokens':self.c['max_output_tokens']}
        headers = {'Authorization': 'Bearer '+key, 'Content-Type':'application/json'}
        request = Request(URLS[provider], data=json.dumps(payload).encode(), headers=headers)
        try:
            with urlopen(request, timeout=self.c['timeout_seconds']) as response:
                raw = response.read().decode()
        except Exception as exc:
            # Do not log headers or exception bodies that might echo credentials.
            raise ProviderError(type(exc).__name__) from None
        try:
            data = json.loads(raw)
            return data['choices'][0]['message']['content'], raw, data.get('usage', {})
        except (KeyError, TypeError, ValueError):
            raise ProviderError('Malformed provider response', raw) from None


class OpenAIAdapter(RESTAdapter):
    def __init__(self, config):
        super().__init__({**config, 'provider':'openai'})


class CerebrasAdapter:
    """OpenAI-compatible Cerebras endpoint with schema-constrained output and backoff."""
    live = True
    accepts_options = True
    def __init__(self, config, opener=urlopen, sleep=time.sleep):
        self.c = {**config, 'provider':'cerebras'}
        self.opener, self.sleep = opener, sleep
    def payload(self, messages, schema=None, seed=None, override=None):
        p = {'model':override['served_model'] if override else self.c['model'], 'messages':messages,
             'temperature':self.c['temperature'], 'max_completion_tokens':self.c['max_output_tokens']}
        if self.c.get('reasoning_effort'): p['reasoning_effort'] = self.c['reasoning_effort']
        # reasoning_format is a Cerebras-only option; it is not sent to an override endpoint (D-060).
        if self.c.get('reasoning_format') and not override: p['reasoning_format'] = self.c['reasoning_format']
        if schema is not None and self.c.get('structured_output', True): p['response_format'] = schema
        if seed is not None and self.c.get('send_seed', True): p['seed'] = int(seed)
        return p
    def complete(self, messages, schema=None, seed=None):
        guard()
        override = endpoint_override()
        if override:
            key = os.environ.get(OVERRIDE_KEY, '').strip().lstrip('\ufeff')
            if not key: raise RuntimeError(f'Missing {OVERRIDE_KEY}')
        else:
            key = os.environ.get(KEY_NAMES['cerebras'])
            if not key: raise RuntimeError('Missing CEREBRAS_API_KEY')
        body = json.dumps(self.payload(messages, schema, seed, override)).encode()
        headers = {'Authorization':'Bearer '+key, 'Content-Type':'application/json', 'User-Agent':USER_AGENT}
        raw, _, backoffs = _transport(self.opener, Request(override['url'] if override else URLS['cerebras'], data=body, headers=headers),
                                      self.c['timeout_seconds'], int(self.c.get('rate_limit_retries', 5)),
                                      float(self.c.get('backoff_seconds', 2.0)), self.sleep)
        try:
            data = json.loads(raw)
            choice = data['choices'][0]
            text = choice['message'].get('content')
            usage = {**data.get('usage', {}), 'backoffs':backoffs,
                     'finish_reason':choice.get('finish_reason'), 'model':data.get('model'),
                     'system_fingerprint':data.get('system_fingerprint'), 'time_info':data.get('time_info')}
            if override:
                reasoning = choice['message'].get('reasoning') or choice['message'].get('reasoning_content') or ''
                usage.update(endpoint_host=override['host'], served_model=override['served_model'],
                             reasoning_chars=len(reasoning))
        except (KeyError, TypeError, ValueError, IndexError):
            raise ProviderError('Malformed provider response', raw) from None
        if text is None or choice.get('finish_reason') == 'length':
            # Paid tokens still count towards the spend cap (review finding 5).
            raise ProviderError(f"Truncated or empty output (finish_reason={choice.get('finish_reason')})", raw, usage)
        return text, raw, stamp_prices(usage, self.c)


def stamp_prices(usage, llm):
    """D-053: an adapter whose config names its prices (`input_price_per_million`, `output_price_per_million`,
    as `llm_alt` does) stamps them on usage, so the run's spend cap charges each provider at its own rate."""
    if 'input_price_per_million' in llm and 'output_price_per_million' in llm:
        usage['unit_prices'] = (float(llm['input_price_per_million']), float(llm['output_price_per_million']))
    return usage


def _transport(opener, request, timeout, retries, base, sleep):
    """One request with exponential backoff on transient failures. Returns (raw, headers, backoffs)."""
    backoffs = 0
    while True:
        try:
            with opener(request, timeout=timeout) as response:
                raw = response.read().decode()
                headers = dict(getattr(response, 'headers', None) or {})
            return raw, headers, backoffs
        except HTTPError as exc:
            detail = exc.read().decode(errors='replace')[:500] if hasattr(exc,'read') else ''
            if exc.code in RETRYABLE_STATUS and backoffs < retries:
                wait = base*(2**backoffs)
                try: wait = max(wait, min(60., float((exc.headers or {}).get('Retry-After'))))
                except (TypeError, ValueError): pass
                sleep(wait); backoffs += 1; continue
            raise ProviderError(f'HTTP {exc.code}', json.dumps({'status':exc.code,'body':detail,'backoffs':backoffs})) from None
        except (URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            if backoffs < retries:
                sleep(base*(2**backoffs)); backoffs += 1; continue
            raise ProviderError(type(exc).__name__, json.dumps({'backoffs':backoffs})) from None


def anthropic_schema(schema):
    """The decision schema in the Messages API's structured-output form (D-052). Numeric bounds are
    not supported there, so they move into the description and `strict_output` enforces them."""
    s = json.loads(json.dumps(schema['json_schema']['schema']))
    for name, prop in s['properties'].items():
        lo, hi = prop.pop('minimum', None), prop.pop('maximum', None)
        if lo is not None or hi is not None:
            prop['description'] = f'{name} between {lo} and {hi} inclusive'
    return {'type':'json_schema', 'schema':s}


class AnthropicAdapter:
    """Claude Messages API with adaptive thinking, structured output and backoff (D-052)."""
    live = True
    accepts_options = True
    VERSION = '2023-06-01'
    def __init__(self, config, opener=urlopen, sleep=time.sleep):
        self.c = {**config, 'provider':'anthropic'}
        self.opener, self.sleep = opener, sleep
    def payload(self, messages, schema=None, seed=None):
        system = [m['content'] for m in messages if m['role']=='system']
        p = {'model':self.c['model'], 'max_tokens':self.c['max_output_tokens'],
             'messages':[{'role':m['role'],'content':m['content']} for m in messages if m['role']!='system']}
        if system: p['system'] = '\n\n'.join(system)
        temperature = self.c.get('temperature')
        # Claude Haiku 5.5 rejects any temperature other than its default of 1; it is sent only when
        # it differs from the default, so an older model's run still records what it asked for.
        if temperature is not None and float(temperature) != 1.0: p['temperature'] = temperature
        display = self.c.get('thinking_display', 'summarized')
        if display: p['thinking'] = {'type':'adaptive', 'display':display}
        output = {}
        if self.c.get('reasoning_effort'): output['effort'] = self.c['reasoning_effort']
        if schema is not None and self.c.get('structured_output', True): output['format'] = anthropic_schema(schema)
        if output: p['output_config'] = output
        # No seed parameter exists; the request seed is kept in the call log only.
        return p
    def complete(self, messages, schema=None, seed=None):
        guard()
        key = os.environ.get(KEY_NAMES['anthropic'])
        if not key: raise RuntimeError('Missing ANTHROPIC_API_KEY')
        body = json.dumps(self.payload(messages, schema, seed)).encode()
        headers = {'x-api-key':key, 'anthropic-version':self.VERSION, 'Content-Type':'application/json'}
        raw, response_headers, backoffs = _transport(self.opener, Request(URLS['anthropic'], data=body, headers=headers),
                                                     self.c['timeout_seconds'], int(self.c.get('rate_limit_retries', 5)),
                                                     float(self.c.get('backoff_seconds', 2.0)), self.sleep)
        try:
            data = json.loads(raw)
            blocks = data['content']
            texts = [b['text'] for b in blocks if b.get('type')=='text']
            thinking = ''.join(b.get('thinking') or '' for b in blocks if b.get('type') in ('thinking','redacted_thinking'))
            u = data.get('usage', {})
            # prompt_tokens/completion_tokens are the names the spend cap and the smoke report read.
            usage = {**u, 'prompt_tokens':u.get('input_tokens',0), 'completion_tokens':u.get('output_tokens',0),
                     'backoffs':backoffs, 'finish_reason':data.get('stop_reason'), 'model':data.get('model'),
                     'request_id':response_headers.get('request-id') or response_headers.get('Request-Id'),
                     'thinking_chars':len(thinking), 'requested_seed':seed}
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            raise ProviderError('Malformed provider response', raw) from None
        stop = data.get('stop_reason')
        if stop == 'max_tokens' or not texts:
            # Paid tokens still count towards the spend cap.
            raise ProviderError(f'Truncated or empty output (stop_reason={stop})', raw, usage)
        if stop == 'refusal':
            raise ProviderError('Refusal (stop_reason=refusal)', raw, usage)
        return ''.join(texts), raw, stamp_prices(usage, self.c)


def adapter_for(c):
    provider = c['provider']
    if provider == 'cerebras': return CerebrasAdapter(c)
    if provider == 'anthropic': return AnthropicAdapter(c)
    return OpenAIAdapter(c)


def messages_for(obs, c):
    root = Path(c['prompt_dir'])
    with_notes = 'own_notes' in obs
    suffix = (root / ('with_notes.txt' if with_notes else 'no_notes.txt')).read_text()
    if with_notes:
        suffix += '\nMaximum notes characters: '+str(c['notes_max_chars'])
    return [{'role':'system','content':(root/'system.txt').read_text()},
            {'role':'user','content':render(obs)+'\n\n'+suffix}]


def strict_output(text, notes, bounds, max_chars, overflow='reject'):
    def pairs(items):
        d = {}
        for k,v in items:
            if k in d: raise ValueError('Duplicate JSON key')
            d[k] = v
        return d
    value = json.loads(text, object_pairs_hook=pairs,
                       parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
    expected = {'price','notes'} if notes else {'price'}
    if not isinstance(value,dict) or set(value) != expected:
        raise ValueError('Wrong schema')
    p = value['price']
    if type(p) not in (int,float) or not math.isfinite(p) or not bounds[0] <= p <= bounds[1]:
        raise ValueError('Invalid price')
    text_notes = value.get('notes','')
    if notes and not isinstance(text_notes,str):
        raise ValueError('Invalid notes')
    truncated = False
    if notes and len(text_notes) > max_chars:
        if overflow != 'truncate': raise ValueError('Invalid notes')
        text_notes, truncated = text_notes[:max_chars], True
    result = {'price': float(p), 'notes': text_notes}
    if truncated: result['notes_truncated'] = True
    return result


def request_seed(context):
    """Same seed for the same prefix, period and firm in every arm (best-effort determinism only)."""
    raw = f"{context.get('seed')}|{context.get('phase')}|{context.get('period')}|{context.get('firm')}"
    return int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)


class LLMAgent:
    """Stateless between requests: everything it knows arrives in the observation."""
    def __init__(self, c, adapter, logger):
        self.c, self.adapter, self.logger = c, adapter, logger
    def __deepcopy__(self, memo):
        # Forks copy agents. The adapter and the run logger (lock, spend, circuit breaker)
        # must be shared by every branch, never duplicated.
        return LLMAgent(self.c, self.adapter, self.logger)
    def act(self, obs, market, firm, previous_price, context):
        if self.adapter.live: guard()
        if hasattr(self.logger,'check'): self.logger.check()
        messages = messages_for(obs, self.c)
        with_notes = 'own_notes' in obs
        schema = response_schema(with_notes, market.bounds); seed = request_seed(context)
        for attempt in range(2):
            raw = text = None
            usage = {}
            try:
                if getattr(self.adapter,'accepts_options',False):
                    # A retry gets a new seed: an identical request would reproduce the same failure.
                    text, raw, usage = self.adapter.complete(messages, schema=schema, seed=seed+attempt)
                else:
                    text, raw, usage = self.adapter.complete(messages)
                result = strict_output(text, with_notes, market.bounds, self.c['notes_max_chars'],
                                       self.c.get('notes_overflow','reject'))
                error = None
            except (ValueError, TypeError, ProviderError) as exc:
                if isinstance(exc,ProviderError): raw, usage = exc.raw, exc.usage
                error = str(exc)
                result = None
            carried = result is None and attempt==1
            self.logger.write(**context, attempt=attempt, raw_input=messages, observation=obs,
                              raw_output=raw, response_text=text, usage=usage,
                              failure=error, carried_previous=carried,
                              notes_truncated=bool(result and result.get('notes_truncated')))
            # Spend is counted after the call is logged, so a paid response is never lost.
            if usage and hasattr(self.logger,'add_spend'): self.logger.add_spend(usage)
            if result is not None:
                if hasattr(self.logger,'record_decision'): self.logger.record_decision(False)
                result.pop('notes_truncated', None)
                return result
            # A transport failure produced no reply: resend the same request unchanged.
            if attempt == 0 and text is not None:
                # Do not retransmit malformed output or privileged hidden state.
                messages = messages + [{'role':'assistant','content': text or ''},
                    {'role':'user','content':(Path(self.c['prompt_dir'])/'retry.txt').read_text()}]
        if hasattr(self.logger,'record_decision'): self.logger.record_decision(True)
        # The previous price is carried; the agent's previous notes stay as they were.
        prior = obs.get('own_notes') or []
        return {'price':float(previous_price), 'notes': prior[-1]['text'] if prior else '', 'carried': True}
