import copy
import hashlib
import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import yaml
from agents.llm import endpoint_override
from env.market import Market


def deep_merge(base, override):
    out = copy.deepcopy(base)
    for k, v in override.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def read_config(path):
    """A config may `extends:` another file (path relative to itself) and override keys."""
    path = Path(path); c = yaml.safe_load(path.read_text())
    parent = c.pop('extends', None)
    return deep_merge(read_config(path.parent/parent), c) if parent else c


def load_config(path='config/main.yaml', synthetic=False):
    c = read_config(path)
    if synthetic:
        c['market'].update(c['synthetic'].get('market') or {})
        if 'shock_shift' in c['synthetic']: c['competence']['shock_shift'] = c['synthetic']['shock_shift']
        c['experiment'].update(c['synthetic'].get('experiment', {}))
        c['purpose'] = 'synthetic_validation_only'
    validate(c)
    return c


def competence_enabled(c):
    """Competence tasks measure the Track 1.5 cost of a restriction (D-031). The screen design
    (D-046) ranks no restriction and does not run them."""
    return bool(c.get('competence', {}).get('enabled', True))


def validate(c):
    e, a, o = c['experiment'], c['analysis'], c['observations']
    enums = [(e['gate_policy'], ('exclude','include')), (e['restricted_roles'], ('both','one_random')),
             (e['branch_rng'], ('shared','independent')), (e['initial_price'], ('nash','monopoly')),
             (e.get('fork_rule','gate'), ('gate','fixed')),
             (e.get('branch_schedule','sequential'), ('sequential','interleaved')),
             (o['notes_policy'], ('all','latest')), (o['market_information'], ('full','own','cost_only')),
             (o.get('sham_format','drop_profit'), ('columns','reversed_rows','drop_profit')),
             # Ranking settings (D-031) have defaults: the screen design (D-046) ranks nothing.
             (a.get('eligibility','upper_bound'), ('point','upper_bound')), (a.get('contrast_adjustment','bonferroni'), ('none','bonferroni')),
             (a.get('singleton_policy','winner'), ('winner','top_set')), (a.get('invalid_share_policy','exclude_prefix'), ('exclude_prefix','error')),
             (a.get('ranking_metric','share'), ('share','removal')),
             (c['llm']['provider'], ('openai','anthropic','cerebras'))]
    for val, choices in enums:
        if val not in choices: raise ValueError(f'Invalid config value {val}; expected {choices}')
    primary = a.get('primary_arm')
    if primary is not None and primary not in ('R1','R2','R3','R4'):
        raise ValueError('primary_arm must be one of R1-R4')
    ids = e.get('prefix_ids')
    if ids is not None and (not ids or any(not 0 <= int(i) < e['prefixes'] for i in ids) or len(set(ids)) != len(ids)):
        raise ValueError('prefix_ids must be distinct indices below experiment.prefixes')
    window = o.get('history_window')
    if window is not None and window < 1:
        raise ValueError('history_window must be positive or null')
    if min(e['window'], e['prefixes'], e['branch_periods'], e['max_prefix']) < 1:
        raise ValueError('Positive run sizes required')
    if e['window'] > min(e['max_prefix'], e['branch_periods']):
        raise ValueError('W must fit prefix and branch')
    if competence_enabled(c) and not 0 < c['competence']['shock_at'] < c['competence']['periods']:
        raise ValueError('Shock must be inside task')
    from env.costs import enabled as costs_enabled, validate_spec
    from env.observations import NOTICE_ARMS
    from run.fork import arms, NESTED_PROBES, nested_start
    validate_spec(c)
    listed = arms(c)
    if costs_enabled(c) and 'NOREGRET' in listed:
        raise ValueError('NOREGRET assumes constant costs (its payoffs use one market); disable it with a cost process')
    if any(x in NESTED_PROBES for x in listed):
        start = nested_start(c)
        if start < 1 or start + c['identification']['recovery_horizon'] >= e['branch_periods']:
            raise ValueError('A nested probe (D-050) needs B - W >= 1 and B - W + recovery_horizon < B')
    for arm in listed:
        if arm in NOTICE_ARMS and not ((o.get('notices') or {}).get(arm) or (arm == 'OVERSIGHT' and o.get('oversight_notice'))):
            raise ValueError(f'Arm {arm} needs a notice text in observations.notices')
    from run.fork import SWAP_ARMS
    swaps = [x for x in listed if x in SWAP_ARMS]
    if swaps:
        if e.get('restricted_roles') != 'both': raise ValueError('Swap arms assume both firms see the baseline interface')
        if any(SWAP_ARMS[x]['agent']=='alt' for x in swaps) and not c.get('llm_alt'):
            raise ValueError('SWAP_OTHER needs an llm_alt section (provider, model) for the newcomer (D-053)')
        if c.get('llm_alt') and c['llm_alt'].get('provider') not in ('openai','anthropic','cerebras'):
            raise ValueError('llm_alt.provider must be openai, anthropic or cerebras')
    w = a.get('swaps')
    if w:
        if not swaps and 'NOREGRET' not in listed: raise ValueError('analysis.swaps needs a swap arm or NOREGRET in experiment.arms')
        if w['control'] not in listed or any(x not in listed for x in w['arms']):
            raise ValueError('analysis.swaps.control and arms must be run')
        if not 0 < w['delta_margin'] < 1 or not 0 <= w['competitive_delta'] < 1 or w.get('price_margin', 0.01) <= 0:
            raise ValueError('analysis.swaps margins must be positive (delta margins below 1)')
        if w.get('stage_one') and not (2 <= w['stage_one']['prefixes'] and 0 <= w['stage_one']['min_baseline_delta'] < 1):
            raise ValueError('analysis.swaps.stage_one: prefixes >= 2 and 0 <= min_baseline_delta < 1')
    s = a.get('screens')
    if s:
        salience = s.get('salience_controls') or {}
        wanted = [s['control'], s['primary'], *s['disclosed'], *salience.values()]
        if any(x not in listed for x in wanted) or s['primary'] not in s['disclosed']:
            raise ValueError('analysis.screens arms must be run, and the primary must be a disclosed screen')
        if any(k not in s['disclosed'] for k in salience):
            raise ValueError('analysis.screens.salience_controls must be keyed by disclosed screens')
        if not costs_enabled(c) and any(v['statistic'] == 'movement_ratio' for v in s['disclosed'].values()):
            raise ValueError('A movement-ratio screen needs a cost process (D-045)')
        if not 0 < s['delta_margin'] < 1 or any(v['margin'] <= 0 or v.get('cluster_band', 1) <= 0 for v in s['disclosed'].values()):
            raise ValueError('Screen margins and bands must be positive (delta_margin below 1)')
        if any(not isinstance(v.get('evadable', True), bool) for v in s['disclosed'].values()):
            raise ValueError('analysis.screens.disclosed.*.evadable must be true or false')
        st = s.get('stage_one')
        if st and not (st['prefixes'] >= 2 and 0 <= st['min_baseline_delta'] < 1):
            raise ValueError('analysis.screens.stage_one needs prefixes >= 2 and min_baseline_delta in [0, 1)')
    if o.get('delay_k', 2) < 1 or a['bootstrap_resamples'] < 1 or not 0<a['confidence']<1:
        raise ValueError('Invalid delay or bootstrap settings')
    if not 0 < a.get('eligibility_confidence', a['confidence']) < 1 or not 0 < a.get('noregret_survival_margin', 0.1) < 1:
        raise ValueError('eligibility_confidence and noregret_survival_margin must lie in (0, 1)')
    if c['identification']['recovery_window'] < 1 or c['identification']['recovery_window'] > c['identification']['recovery_horizon']-1:
        raise ValueError('Recovery window must fit the post-punishment horizon')
    if len(e['agents']) != 2:
        raise ValueError('Exactly two agent kinds required')
    if c['identification']['recovery_horizon'] >= e['branch_periods']:
        raise ValueError('Branch must cover H periods after intervention')


def require_live(c):
    if os.environ.get('ALLOW_LIVE_CALLS') != '1':
        raise RuntimeError('Live calls locked: ALLOW_LIVE_CALLS=1 is required')
    if c['purpose'] == 'synthetic_validation_only':
        raise RuntimeError('Synthetic fixture cannot be used for live calls')
    if not all(c['review'].values()) or not c['llm']['model']:
        raise RuntimeError('Resolve every review flag in config (sources, design, budget, rules) and the exact model ID first')
    Market.from_config(c['market'])
    if competence_enabled(c) and c['competence']['shock_shift'] is None:
        raise ValueError('Unresolved competence shock TODO(SOURCES.md)')


def config_hash(c):
    return hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()


def metadata(c, live=False):
    try:
        sha = subprocess.check_output(['git','rev-parse','HEAD'], stderr=subprocess.DEVNULL, text=True).strip()
    except subprocess.CalledProcessError:
        sha = 'UNCOMMITTED'
    try:
        dirty = bool(subprocess.check_output(['git','status','--porcelain'], text=True))
    except subprocess.CalledProcessError:
        dirty = True
    prompt_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(Path(c['llm']['prompt_dir']).glob('*.txt'))}
    alt = c.get('llm_alt') or {}
    meta = {'provider': c['llm']['provider'] if live else 'mock',
            'model_id': c['llm']['model'] if live else 'configured_synthetic_agents',
            'alt_provider': alt.get('provider') if live and alt else None,
            'alt_model_id': alt.get('model') if live and alt else None,
            'reasoning_effort': c['llm'].get('reasoning_effort') if live else None,
            'date': datetime.now(timezone.utc).isoformat(), 'temperature': c['llm']['temperature'],
            'seed': c['experiment']['seed'], 'git_sha': sha, 'git_dirty': dirty,
            'config_hash': config_hash(c), 'prompt_hashes': prompt_hashes, 'synthetic': not live}
    override = endpoint_override() if live else None
    if override:
        # D-060: every request of the cerebras provider goes to this endpoint instead.
        meta['endpoint_override'] = {'replaces_provider': 'cerebras', 'host': override['host'],
                                     'served_model': override['served_model']}
    return meta


def jsonable(x):
    if isinstance(x,np.ndarray): return x.tolist()
    if isinstance(x,np.generic): return x.item()
    raise TypeError(type(x).__name__)


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, default=jsonable, allow_nan=False)+'\n')


class CircuitBreakerTripped(RuntimeError):
    """Raised when too many consecutive LLM decisions fall back to a carried price."""


class SpendCapReached(CircuitBreakerTripped):
    """Raised when the run's estimated provider spend reaches its cap."""


class CallLogger:
    def __init__(self, path, meta, max_consecutive_carries=None, spend_cap=None, prices=None):
        self.path, self.meta = Path(path), meta
        self.lock = threading.Lock()
        self.max_consecutive_carries = max_consecutive_carries
        self.consecutive_carries = 0
        self.spend_cap, self.prices = spend_cap, prices or (0., 0.)
        self.spend = 0.
        self.stopped = None
    def check(self):
        """Called before every live request: once any worker trips, every worker stops."""
        if self.stopped: raise self.stopped
    def stop(self, exc):
        if self.stopped is None: self.stopped = exc
    def _stop(self, exc):
        self.stop(exc)
        raise exc
    def add_spend(self, usage):
        # D-053: a run may call two providers; an adapter configured with its own prices stamps them on usage.
        prices = usage.get('unit_prices') or self.prices
        cost = (usage.get('prompt_tokens',0)*prices[0] + usage.get('completion_tokens',0)*prices[1])/1e6
        with self.lock:
            self.spend += cost
            over = self.spend_cap is not None and self.spend >= self.spend_cap
        if over: self._stop(SpendCapReached(f'Estimated spend ${self.spend:.2f} reached the cap ${self.spend_cap:.2f}'))
    def write(self, **entry):
        line = json.dumps({**self.meta, **entry}, default=jsonable, allow_nan=False)+'\n'
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a') as f:
                f.write(line)
    def record_decision(self, carried):
        """Run-level circuit breaker: a provider outage must stop the run, not fill it with carried prices."""
        with self.lock:
            self.consecutive_carries = self.consecutive_carries+1 if carried else 0
            tripped = self.max_consecutive_carries and self.consecutive_carries >= self.max_consecutive_carries
        if tripped:
            self._stop(CircuitBreakerTripped(f'{self.consecutive_carries} consecutive carried decisions; stopping the run'))


def clone_config(c): return copy.deepcopy(c)
