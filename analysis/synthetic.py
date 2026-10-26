"""Known scripted fixtures only. Outputs are never experimental evidence."""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm
from agents.mock import PriorHighAgent
from env.market import Market
from env.observations import build
from run.common import load_config,write_json
from run.cli import execute
from analysis.pipeline import analyze,infer,interval


FIXTURE_KEYS=('market','competence','competence_offset','high_fraction','track_markup','noise_amplitude','level_markup',
              'partial_slope','cost_reference','rigid_price','join_periods','punishment_periods')


def scenario_config(base,name):
    c=copy.deepcopy(base); spec=c['mock']['scenario_effects'][name]
    kind=spec['kind']; c['experiment']['agents']=[kind,kind]
    c['experiment']['prefixes']=c['synthetic']['prefixes']
    c['mock'][kind]=copy.deepcopy(c['mock'][kind])
    for k in FIXTURE_KEYS:
        if k in spec: c['mock'][kind][k]=spec[k]
    if 'swap_newcomers' in spec: c['mock']['swap_newcomers']=dict(spec['swap_newcomers'])  # D-053
    return c


def validate_swap_scenarios(c,out):
    """D-053: every pre-registered replacement reading and carrier pattern on a fixture whose answer is
    known before it runs; the incumbent's price reading and the probe flag where the fixture states them."""
    out=Path(out); verdicts={}
    for name,spec in c['mock']['scenario_effects'].items():
        run=out/name
        execute(scenario_config(c,name),run)
        verdict=analyze(run)
        got={arm:r['reading'] for arm,r in verdict['swaps']['arms'].items()}
        for arm,expected in spec['expected_readings'].items():
            assert got[arm]==expected,(name,arm,got[arm],verdict['swaps']['arms'][arm])
        if 'expected_carrier' in spec:
            assert verdict['swaps']['carrier']['reading']==spec['expected_carrier'],(name,verdict['swaps']['carrier'])
        for arm,expected in (spec.get('expected_incumbent_price') or {}).items():
            r=verdict['swaps']['arms'][arm]
            assert r['incumbent_price_reading']==expected,(name,arm,r['incumbent_price_reading'],r['incumbent_price_drop'])
        if 'expected_collusion_flag' in spec:
            assert verdict['collusion_flag']==spec['expected_collusion_flag'],(name,verdict['probes'],verdict.get('paired_probe_comparisons'))
        verdicts[name]=verdict
        print(f"{name}: {got}; carrier={verdict['swaps']['carrier']['reading']}; collusion_flag={verdict.get('collusion_flag')}",flush=True)
    write_json(out/'verdicts.json',verdicts)
    return verdicts


def swap_power(c,out):
    """Operating characteristics of the replacement reading (D-053) under planted paired effects.

    Per prefix: a baseline Delta, a paired final-window drop and a paired early-window drop, each drawn
    from a declared normal distribution. The decision is the production rule `swap_reading` with the
    production interval. The SDs are assumptions, not LLM estimates.
    """
    from analysis.swaps import swap_reading
    from analysis.pipeline import bootstrap_mean
    s=c['synthetic']['swap_power']; a=copy.deepcopy(c['analysis']); a['bootstrap_resamples']=s['bootstrap_resamples']
    w=a['swaps']; rng=np.random.default_rng(s['seed']); rows=[]
    # truth -> (final drop mean, early drop mean); collapse sets the arm's final Delta at collapse_delta.
    truths={'survives':(0.,0.),'erosion':(s['erosion_drop'],s['erosion_drop']),'collapse':(None,None),
            're_forms':(0.,s['reform_early_drop']),'escalation':(-s['escalation_rise'],-s['escalation_rise'])}
    for n in s['n']:
        for sd in s['sd_delta']:
            for truth,(drop_mean,early_mean) in truths.items():
                counts={}
                for rep in range(s['replications']):
                    a['bootstrap_seed']=s['seed']+rep
                    control=rng.normal(s['control_delta'],s['control_delta_sd'],n)
                    if truth=='collapse':
                        arm=rng.normal(s['collapse_delta'],sd/2,n); drop=control-arm; early=drop.copy()
                    else:
                        drop=rng.normal(drop_mean,sd,n); early=rng.normal(early_mean,sd,n); arm=control-drop
                    reading=swap_reading(n,bootstrap_mean(control,a),bootstrap_mean(arm,a),bootstrap_mean(drop,a),
                                         bootstrap_mean(early,a),w['delta_margin'],w['competitive_delta'],
                                         a.get('feasibility_min_delta',0.))
                    counts[reading]=counts.get(reading,0)+1
                for reading,k in sorted(counts.items()):
                    rows.append({'synthetic_only':True,'truth':truth,'n_prefixes':n,'paired_sd_delta':sd,
                                 'reading':reading,'rate':k/s['replications'],'replications':s['replications'],
                                 'delta_margin':w['delta_margin'],'competitive_delta':w['competitive_delta'],
                                 'interval_method':a.get('interval_method','percentile'),'seed':s['seed']})
            print(f'swap power: n={n}, sd={sd}',flush=True)
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(out/'swap_power.csv',index=False)
    return out/'swap_power.csv'


def validate_screen_scenarios(c,out):
    """D-047, D-050: every pre-registered reading on a fixture whose answer is known before it runs,
    with the in-screen probe and the salience check where the fixture states them."""
    out=Path(out); verdicts={}
    for name,spec in c['mock']['scenario_effects'].items():
        run=out/name
        execute(scenario_config(c,name),run)
        verdict=analyze(run)
        got={arm:r['reading'] for arm,r in verdict['screens']['readings'].items()}
        for arm,expected in spec['expected_readings'].items():
            assert got[arm]==expected,(name,arm,got[arm],verdict['screens']['readings'][arm])
        if 'expected_collusion_flag' in spec:
            assert verdict['collusion_flag']==spec['expected_collusion_flag'],(name,verdict['probes'],verdict.get('paired_probe_comparisons'))
        if 'expected_in_screen_matched_cut_rate' in spec:
            rate=verdict['probes']['SCREEN_VAR_UNDERCUT']['matched_cut_rate']
            assert rate==spec['expected_in_screen_matched_cut_rate'],(name,verdict['probes'])
        if 'expected_in_screen_flag' in spec:
            assert verdict['in_screen_flag']==spec['expected_in_screen_flag'],(name,verdict['probes'],verdict['paired_probe_comparisons'])
        if 'expected_salience_check' in spec:
            r=verdict['screens']['readings'][c['analysis']['screens']['primary']]['specificity']['salience']
            assert r['reading']==spec['expected_salience_check'],(name,r)
        verdicts[name]=verdict
        print(f"{name}: {got}; collusion_flag={verdict.get('collusion_flag')}",flush=True)
    write_json(out/'verdicts.json',verdicts)
    return verdicts


def screen_power(c,out):
    """Operating characteristics of the primary reading (D-047) under planted paired effects.

    Per prefix: a control Delta, a control pass margin (negative: the screen flags the control),
    a paired Delta drop and a paired shift of the disclosed statistic, each drawn from a declared
    normal distribution. The decision is the production rule `screen_reading` with the production
    interval. The SDs are assumptions, not LLM estimates; the Friday smoke gives a first look.
    """
    from analysis.screens import screen_reading
    from analysis.pipeline import bootstrap_mean
    s=c['synthetic']['screen_power']; a=copy.deepcopy(c['analysis']); a['bootstrap_resamples']=s['bootstrap_resamples']
    spec=a['screens']; margin=spec['delta_margin']; primary=spec['disclosed'][spec['primary']]
    stat_margin=primary['margin']; evadable=bool(primary.get('evadable',True))
    rng=np.random.default_rng(s['seed']); rows=[]
    # D-050: the treated pair's pass margin is the control's plus the shift, so a shift that does not
    # carry the pair past the threshold cannot be read as EVASION.
    truths={'evasion':(0.,s['evasion_shift']),'shift_to_threshold':(0.,s['threshold_shift']),
            'small_shift':(0.,s['small_shift']),'deterrence':(s['deterrence_drop'],s['evasion_shift']),'no_response':(0.,0.)}
    for n in s['n']:
        for sd in s['sd_delta']:
            for truth,(drop_mean,shift_mean) in truths.items():
                counts={}
                for rep in range(s['replications']):
                    a['bootstrap_seed']=s['seed']+rep
                    control=rng.normal(s['control_delta'],s['control_delta_sd'],n)
                    drop=rng.normal(drop_mean,sd,n); shift=rng.normal(shift_mean,s['sd_shift'],n)
                    control_pass=rng.normal(s['control_pass'],s['control_pass_sd'],n)
                    reading=screen_reading(n,bootstrap_mean(control,a),bootstrap_mean(drop,a),bootstrap_mean(control-drop,a),
                                           bootstrap_mean(control_pass,a),bootstrap_mean(shift,a),
                                           bootstrap_mean(control_pass+shift,a),margin,stat_margin,
                                           a.get('feasibility_min_delta',0.),evadable)
                    counts[reading]=counts.get(reading,0)+1
                for reading,k in sorted(counts.items()):
                    rows.append({'synthetic_only':True,'truth':truth,'n_prefixes':n,'paired_sd_delta':sd,
                                 'reading':reading,'rate':k/s['replications'],'replications':s['replications'],
                                 'delta_margin':margin,'interval_method':a.get('interval_method','percentile'),'seed':s['seed']})
            print(f'screen power: n={n}, sd={sd}',flush=True)
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(out/'screen_power.csv',index=False)
    return out/'screen_power.csv'


def validate_scenarios(c,out):
    out=Path(out); verdicts={}
    for name,spec in c['mock']['scenario_effects'].items():
        run=out/name
        cc=scenario_config(c,name)
        execute(cc,run)
        verdict=analyze(run)
        assert verdict['verdict']==spec['expected'], (name,verdict)
        if 'expected_winner' in spec: assert verdict['winner']==spec['expected_winner'],(name,verdict)
        if 'expected_collusion_flag' in spec:
            assert verdict['collusion_flag']==spec['expected_collusion_flag'],(name,verdict)
        if 'expected_primary' in spec:
            assert verdict['primary']['status']==spec['expected_primary'],(name,verdict['primary'])
        verdicts[name]=verdict
        primary=verdict.get('primary',{}).get('status')
        print(f"{name}: {verdict['verdict']}; winner={verdict['winner']}; primary={primary}; collusion_flag={verdict['collusion_flag']}",flush=True)
    write_json(out/'verdicts.json',verdicts)
    return verdicts


def power(c,out):
    """Price-mixture Monte Carlo using mock actions; no LLM or Q-learning runs.

    Each cluster has a shared baseline and independent arm-level price-mixture
    noise. Competence cost is planted at zero. This tests verdict sensitivity
    under this artificial distribution, not expected empirical power.
    """
    settings=c['synthetic']['power']; rng=np.random.default_rng(settings['seed'])
    market=Market.from_config(c['market']); records=[]
    from analysis.pipeline import ranking_arms
    others=[x for x in ranking_arms(c) if x!='R1']
    arm_names=['baseline']+ranking_arms(c)+['SHAM','UNDERCUT']
    for n in settings['prefixes']:
        for effect in settings['effect_sizes']:
            detections=any_winner=usable=0; effects=[]
            for rep in range(settings['replications']):
                values=[]
                for pid in range(n):
                    baseline=float(rng.uniform(*settings['baseline_fraction_range'])); row={}
                    for arm in arm_names:
                        fraction=baseline if arm in ('baseline','SHAM','UNDERCUT') else float(np.clip(baseline-(effect if arm=='R1' else 0)+rng.normal(0,settings['prefix_noise']),*settings['fraction_bounds']))
                        ac=copy.deepcopy(c['mock']['PriorHighAgent']); ac['high_fraction']=fraction
                        agents=[PriorHighAgent(ac,settings['seed']+pid*2+i) for i in range(2)]
                        prices=[agent.act(build([],i,arm,market,c),market,i,market.nash[i],{'arm':arm})['price'] for i,agent in enumerate(agents)]
                        row[arm]=float(market.delta(market.profits(prices)).mean())
                    values.append(row)
                delta=pd.DataFrame(values)
                shares=delta.rsub(delta.baseline,axis=0).div(delta.baseline,axis=0)
                costs=pd.DataFrame(0.,index=delta.index,columns=[x for x in arm_names if x!='UNDERCUT'])
                _,_,v=infer(delta,shares,costs,c)
                detections+=v['verdict']=='WINNER' and v['winner']=='R1'
                any_winner+=v['verdict']=='WINNER'; usable+=1
                metric=delta.rsub(delta.baseline,axis=0)
                effects.append(float((metric.R1-metric[others].mean(axis=1)).mean()))
            rate=detections/usable
            records.append({'synthetic_only':True,'prefixes':n,'planted_price_fraction_gap':effect,
                'replications':usable,'R1_detection_rate':rate,'any_winner_rate':any_winner/usable,
                'monte_carlo_se':np.sqrt(rate*(1-rate)/usable),'mean_induced_removal_gap':np.mean(effects),
                'ranking_metric':c['analysis'].get('ranking_metric','share'),
                'bootstrap_resamples':c['analysis']['bootstrap_resamples'],'seed':settings['seed']})
            print(f'power: prefixes={n}, planted_price_fraction_gap={effect}, replications={usable}',flush=True)
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(records).to_csv(out/'power.csv',index=False)
    return out/'power.csv'


def primary_power(c,out):
    """Power of the single pre-registered contrast (D-030) under assumed paired-difference SDs.

    Paired removals are drawn as N(effect, sd); the decision is the production rule
    (percentile bootstrap lower bound > 0). The SDs are assumptions, not LLM estimates.
    """
    s=c['synthetic']['primary_power']; a=c['analysis']; rng=np.random.default_rng(s['seed']); rows=[]
    resamples=min(a['bootstrap_resamples'],2000); q=(1-a['confidence'])/2
    method=a.get('interval_method','percentile')
    for n in s['n']:
        for effect in s['effects']:
            for sd in s['sd']:
                hits=0
                for _ in range(s['replications']):
                    d=rng.normal(effect,sd,n)
                    boot=d[rng.integers(0,n,size=(resamples,n))].mean(axis=1)
                    hits+=interval(boot,a['confidence'],n,method)[0]>0
                rate=hits/s['replications']
                normal=float(norm.cdf(effect/(sd/np.sqrt(n))-norm.ppf(1-q)))
                rows.append({'synthetic_only':True,'n_prefixes':n,'effect_removal':effect,'paired_sd':sd,
                             'bootstrap_power':rate,'monte_carlo_se':np.sqrt(rate*(1-rate)/s['replications']),
                             'normal_theory_power':normal,'replications':s['replications'],
                             'bootstrap_resamples':resamples,'interval_method':method,'seed':s['seed']})
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(out/'primary_power.csv',index=False)
    return out/'primary_power.csv'


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--config',default='config/main.yaml')
    p.add_argument('--output',default='results/synthetic'); p.add_argument('--skip-power',action='store_true')
    a=p.parse_args(); c=load_config(a.config,synthetic=True)
    if c['analysis'].get('swaps'):
        validate_swap_scenarios(c,a.output)
        if not a.skip_power: print('Replacement-reading power table:',swap_power(c,a.output))
    elif c['analysis'].get('screens'):
        validate_screen_scenarios(c,a.output)
        if not a.skip_power: print('Screen-reading power table:',screen_power(c,a.output))
    else:
        validate_scenarios(c,a.output)
        if not a.skip_power:
            print('Power table:',power(c,a.output))
            print('Primary-contrast power table:',primary_power(c,a.output))
