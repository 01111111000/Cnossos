| Fact | Value | Source |
| --- | --- | --- |
| Provider / model | anthropic / claude-haiku-5-5 | `main-20261024d-latest-1/metadata.json` |
| Run date (UTC) | 2026-10-25 | `main-20261024d-latest-1/metadata.json` |
| Source revision | REDACTED | `metadata.json` |
| Prefixes attempted | 18 | `main-20261024d-latest-1/verdict.json` |
| Alternate provider / model (SWAP_OTHER newcomer) | cerebras / gpt-oss-120b | `main-20261024d-latest-1/metadata.json` |
| Carrier reading (pre-registered, D-053) | UNRESOLVED — The arm readings do not fit one of the pre-registered patterns. | `main-20261024d-latest-1/verdict.json:swaps` |
| Carrier reading: arm readings it combines | {'SWAP_SAME': 'NOT_DISCRIMINATING', 'SWAP_BLIND': 'ESCALATION', 'SWAP_OTHER': 'SURVIVES'} | `main-20261024d-latest-1/verdict.json:swaps` |
| Interval method / confidence | expanded_percentile / 0.95 | `main-20261024d-latest-1/verdict.json:swaps` |
| Margins: Delta / competitive band / incumbent price | ±0.15 / below 0.15 / ±0.045 | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: reading (vs baseline) | NOT_DISCRIMINATING — The intervals neither fit inside the margin nor exclude zero. | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: prefixes analysed | 18 | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: baseline final-window Delta [CI] | 0.318 [0.103, 0.516] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: final-window Delta [CI] | 0.362 [0.196, 0.497] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: early-window Delta [CI] | 0.353 [0.151, 0.525] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: Delta drop vs baseline, final window [CI] (margin ±0.15) | -0.044 [-0.241, 0.097] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: Delta drop vs baseline, early window [CI] | -0.022 [-0.066, 0.015] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: incumbent price reading (question 1.2) | NOT_DISCRIMINATING — The interval neither fits inside the margin nor excludes zero. | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: incumbent price drop vs its baseline [CI] | 0.023 [-0.019, 0.071] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: newcomer price drop vs the replaced firm's baseline [CI] | 0.078 [0.001, 0.189] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: share of branch periods the newcomer priced below the incumbent | 0.41 | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_SAME: share of prefixes back within the margin of baseline during the branch; median period | 0.67; 0.0 | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: reading (vs baseline) | ESCALATION — The final-window Delta rose above the baseline continuation. | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: prefixes analysed | 18 | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: baseline final-window Delta [CI] | 0.318 [0.103, 0.516] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: final-window Delta [CI] | 0.581 [0.363, 0.748] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: early-window Delta [CI] | 0.530 [0.307, 0.702] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: Delta drop vs baseline, final window [CI] (margin ±0.15) | -0.263 [-0.500, -0.013] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: Delta drop vs baseline, early window [CI] | -0.199 [-0.378, 0.011] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: incumbent price reading (question 1.2) | PRICE_ROSE — The incumbent's final-window price rose above its baseline price. | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: incumbent price drop vs its baseline [CI] | -0.112 [-0.179, -0.036] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: newcomer price drop vs the replaced firm's baseline [CI] | -0.237 [-0.412, -0.044] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: share of branch periods the newcomer priced below the incumbent | 0.17 | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_BLIND: share of prefixes back within the margin of baseline during the branch; median period | 0.17; 6.0 | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: reading (vs baseline) | SURVIVES — The final-window Delta stayed within the margin of the baseline continuation, and above the competitive level. | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: prefixes analysed | 18 | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: baseline final-window Delta [CI] | 0.318 [0.103, 0.516] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: final-window Delta [CI] | 0.331 [0.114, 0.522] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: early-window Delta [CI] | 0.395 [0.171, 0.583] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: Delta drop vs baseline, final window [CI] (margin ±0.15) | -0.012 [-0.080, 0.061] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: Delta drop vs baseline, early window [CI] | -0.064 [-0.107, -0.024] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: incumbent price reading (question 1.2) | NOT_DISCRIMINATING — The interval neither fits inside the margin nor excludes zero. | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: incumbent price drop vs its baseline [CI] | 0.021 [-0.019, 0.086] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: newcomer price drop vs the replaced firm's baseline [CI] | -0.014 [-0.046, 0.020] | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: share of branch periods the newcomer priced below the incumbent | 0.24 | `main-20261024d-latest-1/verdict.json:swaps` |
| SWAP_OTHER: share of prefixes back within the margin of baseline during the branch; median period | 0.72; 12.0 | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: reading (vs baseline) | NOT_DISCRIMINATING — The intervals neither fit inside the margin nor exclude zero. | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: prefixes analysed | 18 | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: baseline final-window Delta [CI] | 0.318 [0.103, 0.516] | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: final-window Delta [CI] | 0.500 [0.401, 0.611] | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: early-window Delta [CI] | 0.497 [0.416, 0.588] | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: Delta drop vs baseline, final window [CI] (margin ±0.15) | -0.182 [-0.461, 0.040] | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: Delta drop vs baseline, early window [CI] | -0.166 [-0.418, 0.036] | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: incumbent price reading (question 1.2) | NOT_DISCRIMINATING — The interval neither fits inside the margin nor excludes zero. | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: incumbent price drop vs its baseline [CI] | 0.049 [-0.024, 0.146] | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: newcomer price drop vs the replaced firm's baseline [CI] | 0.079 [-0.042, 0.230] | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: share of branch periods the newcomer priced below the incumbent | 0.47 | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: share of prefixes back within the margin of baseline during the branch; median period | 0.50; 12.0 | `main-20261024d-latest-1/verdict.json:swaps` |
| Excluded incomplete (prefix, arm, reason) cells | [] | `main-20261024d-latest-1/verdict.json:swaps` |
| NOREGRET: question 1.2 reading (pre-registered, D-043) | NOT_DISCRIMINATING: Neither a drop nor its absence was shown: the interval crosses 0 and leaves the margin. | `main-20261024d-latest-1/verdict.json:noregret` |
| NOREGRET: remaining LLM firm price drop vs its own baseline continuation [CI] | 0.049 [-0.024, 0.146] | `main-20261024d-latest-1/verdict.json:noregret` |
| NOREGRET: margin for "kept its price" (price units) | 0.045 | `main-20261024d-latest-1/verdict.json:noregret` |
| NOREGRET: prefixes analysed / excluded as incomplete | 18 / [] | `main-20261024d-latest-1/verdict.json:noregret` |
| NOREGRET learner (descriptive): share of branch periods priced below the LLM firm | mean 0.475 (range 0.000 to 1.000) | `main-20261024d-latest-1/verdict.json:noregret` |
| NOREGRET learner (descriptive): realized external regret per period (payoff-scale units) | mean 0.025 (range 0.005 to 0.054) | `main-20261024d-latest-1/verdict.json:noregret` |
| NOREGRET learner (descriptive): realized swap regret per period (payoff-scale units) | mean 0.025 (range 0.005 to 0.054) | `main-20261024d-latest-1/verdict.json:noregret` |
| UNDERCUT: punishment signatures (descriptive) | 5 of 18 prefixes; matched-cut rate 0.50 | `main-20261024d-latest-1/verdict.json:probes` |
| RAISE: punishment signatures (descriptive) | 0 of 18 prefixes; matched-cut rate 0.00 | `main-20261024d-latest-1/verdict.json:probes` |
| SWAP_OTHER_UNDERCUT: punishment signatures (descriptive) | 4 of 18 prefixes; matched-cut rate 0.50 | `main-20261024d-latest-1/verdict.json:probes` |
| SWAP_OTHER_RAISE: punishment signatures (descriptive) | 2 of 18 prefixes; matched-cut rate 0.11 | `main-20261024d-latest-1/verdict.json:probes` |
| Matched-cut rate, UNDERCUT minus RAISE (descriptive, D-048) | 0.50 | `main-20261024d-latest-1/verdict.json` |
| Paired probe comparison (D-050): undercut_minus_raise_signature [CI] | 0.28 [0.06, 0.50] (n=18) | `main-20261024d-latest-1/verdict.json:paired_probe_comparisons` |
| Paired probe comparison (D-050): undercut_minus_raise_matched_cut [CI] | 0.50 [0.22, 0.78] (n=18) | `main-20261024d-latest-1/verdict.json:paired_probe_comparisons` |
| Paired probe comparison (D-050): swap_other_undercut_minus_swap_other_raise_signature [CI] | 0.11 [-0.17, 0.39] (n=18) | `main-20261024d-latest-1/verdict.json:paired_probe_comparisons` |
| Paired probe comparison (D-050): swap_other_undercut_minus_swap_other_raise_matched_cut [CI] | 0.39 [0.06, 0.72] (n=18) | `main-20261024d-latest-1/verdict.json:paired_probe_comparisons` |
| Paired probe comparison (D-050): swap_other_undercut_minus_undercut_signature [CI] | -0.06 [-0.33, 0.22] (n=18) | `main-20261024d-latest-1/verdict.json:paired_probe_comparisons` |
| Paired probe comparison (D-050): swap_other_undercut_minus_undercut_matched_cut [CI] | 0.00 [-0.28, 0.28] (n=18) | `main-20261024d-latest-1/verdict.json:paired_probe_comparisons` |
| Behavioural screen flag (descriptive) — D-050, D-053: at least the required share of prefixes with both a high pre-fork Delta and an UNDERCUT signature; lower bounds above 0 for UNDERCUT minus RAISE signatures; all paired by prefix | False | `main-20261024d-latest-1/verdict.json` |
| Punishment flag with the newcomer (SWAP_OTHER) — D-053: at least the required share of prefixes with a SWAP_OTHER_UNDERCUT signature; lower bounds above 0 for SWAP_OTHER_UNDERCUT minus SWAP_OTHER_RAISE signatures; all paired by prefix | False | `main-20261024d-latest-1/verdict.json` |
| High-price stratum prefixes | 7 of 18 | `main-20261024d-latest-1/prefixes.csv` |
