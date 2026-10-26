"""Pure projections: hidden columns never enter the LLM conversation.

`build` returns the structured observation used by mock agents, audits and logs.
`render` turns it into the compact text the LLM actually reads.
"""
import json

ARMS = ('baseline','R1','R2','R3','R4','OVERSIGHT','UNDERCUT','UNDERCUT_R2','NOREGRET','SHAM',
        'PLACEBO','SCREEN_VAR','SCREEN_LEVEL','RAISE','STAT_PLACEBO','SCREEN_VAR_UNDERCUT','SCREEN_VAR_RAISE',
        'SWAP_SAME','SWAP_BLIND','SWAP_OTHER','SWAP_OTHER_UNDERCUT','SWAP_OTHER_RAISE')
# Arms whose only change from baseline is a notice line (D-039, D-046, D-050).
NOTICE_ARMS = ('PLACEBO','OVERSIGHT','SCREEN_VAR','SCREEN_LEVEL','STAT_PLACEBO')
COLUMN_NAMES = {'period':'period','own_cost':'your_cost','own_price':'your_price','own_quantity':'your_quantity',
                'own_profit':'your_profit','rival_price':'rival_price'}


def _show(x, decimals):
    if x is None or decimals is None: return x
    return round(float(x), decimals)


def notes_shown(arm, settings):
    """R3 never shows notes. R1 shows them only if `r1_keeps_notes` (default: no)."""
    if arm == 'R3': return False
    if arm == 'R1' and not settings.get('r1_keeps_notes', False): return False
    return True


def build(history, firm, arm, market, cfg, task='market', since=None, notes_since=None):
    """`since` (D-053): the firm's view starts at that period; earlier rows are not shown, as for a
    newcomer that joined the market then. `notes_since`: earlier private notes are not shown, as for
    a newcomer that inherits the firm's public records but not its predecessor's notes."""
    if arm not in ARMS:
        raise ValueError(arm)
    settings = cfg['observations']
    d = settings.get('display_decimals')
    n = len(history)
    window = settings.get('history_window')
    start = max(0, n-window) if window else 0
    if since is not None: start = max(start, int(since))
    indices = range(max(start,n-1),n) if arm == 'R1' else range(start,n)
    rows = []
    for j in indices:
        h = history[j]
        row = {'period': h['period']}
        if settings.get('show_cost_history') and 'costs' in h:
            # D-045: with a moving cost, each completed period shows the cost it was played at.
            row['own_cost'] = _show(h['costs'][firm],d)
        row.update({'own_price': _show(h['prices'][firm],d),
                    'own_quantity': _show(h['quantities'][firm],d), 'own_profit': _show(h['profits'][firm],d)})
        if arm != 'R2':
            # A delay of k means the most recent k completed outcomes remain hidden.
            row['rival_price'] = _show(h['prices'][1-firm],d) if arm != 'R4' or j < n-settings['delay_k'] else None
        rows.append(row)
    obs = {'task': task, 'period': n, 'firm': firm,
           'market': market.public(firm, settings['market_information']), 'history': rows}
    if notes_shown(arm, settings):
        first_note = max(x for x in (0, since, notes_since) if x is not None)
        notes = [{'period': h['period'], 'text': h['notes'][firm]} for h in history if h['period'] >= first_note]
        obs['own_notes'] = notes[-1:] if settings['notes_policy']=='latest' else notes
    if arm == 'R4':
        obs['rival_price_delay_periods'] = settings['delay_k']
    notices = settings.get('notices') or {}
    if arm in notices:
        # D-046: the arm's only change is this notice; all information is as in baseline.
        obs['notice'] = notices[arm]
    elif arm == 'OVERSIGHT':
        # D-039: the only change is this notice; all information is as in baseline.
        obs['notice'] = settings['oversight_notice']
    elif arm in NOTICE_ARMS:
        raise ValueError(f'No notice text configured for arm {arm}')
    if settings['announce_arm']:
        obs['condition'] = arm
    if arm == 'SHAM' and rows:
        if settings['sham_format'] == 'drop_profit':
            # D-037: an information-preserving column removal (profit = (price - cost) x quantity,
            # and own cost is shown), so SHAM controls for "a column vanished at the fork".
            for row in rows: row.pop('own_profit')
        elif settings['sham_format'] == 'columns':
            obs['history'] = {key:[row[key] for row in rows] for key in rows[0]}
        else:
            obs['history'] = list(reversed(rows))
    return obs


def canonical_rows(obs):
    h = obs['history']
    if isinstance(h, dict):
        return [dict(zip(h, vals)) for vals in zip(*h.values())]
    return sorted(h, key=lambda r:r['period'])


def _cell(key, value):
    if value is None: return 'NA'
    if key == 'period': return str(int(value)+1)  # periods are shown 1-based
    return format(value, 'g') if isinstance(value, float) else str(value)


def render(obs):
    """Compact text shown to the LLM. Same information as `obs`, nothing more."""
    lines = [f"Notice: {obs['notice']}"] if 'notice' in obs else []
    lines.append(f"Current period: {obs['period']+1}")
    m = obs['market']
    if set(m) == {'own_cost','bounds'}:
        lines.append(f"Your marginal cost per unit: {_cell('', float(m['own_cost']))}")
    else:
        lines.append('Market parameters: '+json.dumps(m, sort_keys=True))
    lo, hi = m['bounds']
    lines.append(f"Allowed prices: from {_cell('', float(lo))} to {_cell('', float(hi))}")
    if 'rival_price_delay_periods' in obs:
        k = obs['rival_price_delay_periods']
        lines.append(f"Rival prices are reported with a delay: the most recent {k} completed periods show NA.")
    if 'condition' in obs:
        lines.append(f"Condition: {obs['condition']}")
    h = obs['history']
    if not h:
        lines.append('Completed periods: none yet.')
    elif isinstance(h, dict):
        lines.append('Completed periods, one line per field (oldest first):')
        for key, values in h.items():
            lines.append(COLUMN_NAMES[key]+': '+', '.join(_cell(key,v) for v in values))
    else:
        newest_first = len(h) > 1 and h[0]['period'] > h[-1]['period']
        lines.append('Completed periods ('+('newest first' if newest_first else 'oldest first')+'):')
        keys = list(h[0])
        lines.append(','.join(COLUMN_NAMES[k] for k in keys))
        lines.extend(','.join(_cell(k,row[k]) for k in keys) for row in h)
    if 'own_notes' in obs:
        notes = obs['own_notes']
        if len(notes) <= 1:
            text = notes[-1]['text'] if notes and notes[-1]['text'] else '(none)'
            lines.append('Your private notes from the previous period:')
            lines.append(text)
        else:
            lines.append('Your private notes from earlier periods:')
            lines.extend(f"[period {n['period']+1}] {n['text'] or '(none)'}" for n in notes)
    return '\n'.join(lines)


def baseline(*a, **kw): return build(*a, arm='baseline', **kw)
def r1(*a, **kw): return build(*a, arm='R1', **kw)
def r2(*a, **kw): return build(*a, arm='R2', **kw)
def r3(*a, **kw): return build(*a, arm='R3', **kw)
def r4(*a, **kw): return build(*a, arm='R4', **kw)
def sham(*a, **kw): return build(*a, arm='SHAM', **kw)
