| Fact | Value | Source |
| --- | --- | --- |
| Provider / model | anthropic / claude-haiku-5-5 | `main-20261024d/metadata.json` |
| Run date (UTC) | 2026-10-25 | `main-20261024d/metadata.json` |
| Source revision | REDACTED | `metadata.json` |
| Prefixes attempted | 24 | `main-20261024d/verdict.json` |
| Alternate provider / model (SWAP_OTHER newcomer) | cerebras / gpt-oss-120b | `main-20261024d/metadata.json` |
| Carrier reading (pre-registered, D-053) | UNRESOLVED — The arm readings do not fit one of the pre-registered patterns. | `main-20261024d/verdict.json:swaps` |
| Carrier reading: arm readings it combines | {'SWAP_SAME': 'NOT_DISCRIMINATING', 'SWAP_BLIND': 'ESCALATION', 'SWAP_OTHER': 'SURVIVES'} | `main-20261024d/verdict.json:swaps` |
| Interval method / confidence | expanded_percentile / 0.95 | `main-20261024d/verdict.json:swaps` |
| Margins: Delta / competitive band / incumbent price | ±0.15 / below 0.15 / ±0.045 | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: reading (vs baseline) | NOT_DISCRIMINATING — The intervals neither fit inside the margin nor exclude zero. | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: prefixes analysed | 24 | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: baseline final-window Delta [CI] | 0.371 [0.170, 0.559] | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: final-window Delta [CI] | 0.404 [0.233, 0.557] | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: early-window Delta [CI] | 0.398 [0.210, 0.569] | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: Delta drop vs baseline, final window [CI] (margin ±0.15) | -0.033 [-0.178, 0.068] | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: Delta drop vs baseline, early window [CI] | -0.017 [-0.049, 0.010] | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: incumbent price reading (question 1.2) | NOT_DISCRIMINATING — The interval neither fits inside the margin nor excludes zero. | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: incumbent price drop vs its baseline [CI] | 0.017 [-0.015, 0.053] | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: newcomer price drop vs the replaced firm's baseline [CI] | 0.058 [-0.001, 0.141] | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: share of branch periods the newcomer priced below the incumbent | 0.35 | `main-20261024d/verdict.json:swaps` |
| SWAP_SAME: share of prefixes back within the margin of baseline during the branch; median period | 0.75; 0.0 | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: reading (vs baseline) | ESCALATION — The final-window Delta rose above the baseline continuation. | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: prefixes analysed | 24 | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: baseline final-window Delta [CI] | 0.371 [0.170, 0.559] | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: final-window Delta [CI] | 0.603 [0.435, 0.739] | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: early-window Delta [CI] | 0.522 [0.328, 0.678] | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: Delta drop vs baseline, final window [CI] (margin ±0.15) | -0.232 [-0.440, -0.030] | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: Delta drop vs baseline, early window [CI] | -0.142 [-0.290, 0.018] | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: incumbent price reading (question 1.2) | PRICE_ROSE — The incumbent's final-window price rose above its baseline price. | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: incumbent price drop vs its baseline [CI] | -0.071 [-0.135, -0.000] | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: newcomer price drop vs the replaced firm's baseline [CI] | -0.197 [-0.350, -0.032] | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: share of branch periods the newcomer priced below the incumbent | 0.21 | `main-20261024d/verdict.json:swaps` |
| SWAP_BLIND: share of prefixes back within the margin of baseline during the branch; median period | 0.29; 5.0 | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: reading (vs baseline) | SURVIVES — The final-window Delta stayed within the margin of the baseline continuation, and above the competitive level. | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: prefixes analysed | 24 | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: baseline final-window Delta [CI] | 0.371 [0.170, 0.559] | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: final-window Delta [CI] | 0.371 [0.173, 0.554] | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: early-window Delta [CI] | 0.424 [0.223, 0.604] | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: Delta drop vs baseline, final window [CI] (margin ±0.15) | 0.000 [-0.054, 0.060] | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: Delta drop vs baseline, early window [CI] | -0.043 [-0.079, -0.010] | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: incumbent price reading (question 1.2) | NOT_DISCRIMINATING — The interval neither fits inside the margin nor excludes zero. | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: incumbent price drop vs its baseline [CI] | 0.025 [-0.009, 0.071] | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: newcomer price drop vs the replaced firm's baseline [CI] | -0.008 [-0.033, 0.019] | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: share of branch periods the newcomer priced below the incumbent | 0.23 | `main-20261024d/verdict.json:swaps` |
| SWAP_OTHER: share of prefixes back within the margin of baseline during the branch; median period | 0.75; 4.0 | `main-20261024d/verdict.json:swaps` |
| NOREGRET: reading (vs baseline) | NOT_DISCRIMINATING — The intervals neither fit inside the margin nor exclude zero. | `main-20261024d/verdict.json:swaps` |
| NOREGRET: prefixes analysed | 24 | `main-20261024d/verdict.json:swaps` |
| NOREGRET: baseline final-window Delta [CI] | 0.371 [0.170, 0.559] | `main-20261024d/verdict.json:swaps` |
| NOREGRET: final-window Delta [CI] | 0.529 [0.438, 0.624] | `main-20261024d/verdict.json:swaps` |
| NOREGRET: early-window Delta [CI] | 0.523 [0.443, 0.607] | `main-20261024d/verdict.json:swaps` |
| NOREGRET: Delta drop vs baseline, final window [CI] (margin ±0.15) | -0.158 [-0.408, 0.050] | `main-20261024d/verdict.json:swaps` |
| NOREGRET: Delta drop vs baseline, early window [CI] | -0.143 [-0.369, 0.047] | `main-20261024d/verdict.json:swaps` |
| NOREGRET: incumbent price reading (question 1.2) | PRICE_DROPPED — The incumbent's final-window price fell below its baseline price. | `main-20261024d/verdict.json:swaps` |
| NOREGRET: incumbent price drop vs its baseline [CI] | 0.072 [0.006, 0.154] | `main-20261024d/verdict.json:swaps` |
| NOREGRET: newcomer price drop vs the replaced firm's baseline [CI] | 0.111 [0.004, 0.237] | `main-20261024d/verdict.json:swaps` |
| NOREGRET: share of branch periods the newcomer priced below the incumbent | 0.56 | `main-20261024d/verdict.json:swaps` |
| NOREGRET: share of prefixes back within the margin of baseline during the branch; median period | 0.42; 14.0 | `main-20261024d/verdict.json:swaps` |
| Excluded incomplete (prefix, arm, reason) cells | [] | `main-20261024d/verdict.json:swaps` |
| NOREGRET: question 1.2 reading (pre-registered, D-043) | PRICE_DROPPED: The remaining LLM firm priced below its own baseline continuation once its rival was replaced. | `main-20261024d/verdict.json:noregret` |
| NOREGRET: remaining LLM firm price drop vs its own baseline continuation [CI] | 0.072 [0.006, 0.154] | `main-20261024d/verdict.json:noregret` |
| NOREGRET: margin for "kept its price" (price units) | 0.045 | `main-20261024d/verdict.json:noregret` |
| NOREGRET: prefixes analysed / excluded as incomplete | 24 / [] | `main-20261024d/verdict.json:noregret` |
| NOREGRET learner (descriptive): share of branch periods priced below the LLM firm | mean 0.558 (range 0.000 to 1.000) | `main-20261024d/verdict.json:noregret` |
| NOREGRET learner (descriptive): realized external regret per period (payoff-scale units) | mean 0.022 (range 0.005 to 0.054) | `main-20261024d/verdict.json:noregret` |
| NOREGRET learner (descriptive): realized swap regret per period (payoff-scale units) | mean 0.023 (range 0.005 to 0.054) | `main-20261024d/verdict.json:noregret` |
| UNDERCUT: punishment signatures (descriptive) | 5 of 24 prefixes; matched-cut rate 0.38 | `main-20261024d/verdict.json:probes` |
| RAISE: punishment signatures (descriptive) | 0 of 24 prefixes; matched-cut rate 0.00 | `main-20261024d/verdict.json:probes` |
| SWAP_OTHER_UNDERCUT: punishment signatures (descriptive) | 5 of 24 prefixes; matched-cut rate 0.46 | `main-20261024d/verdict.json:probes` |
| SWAP_OTHER_RAISE: punishment signatures (descriptive) | 3 of 24 prefixes; matched-cut rate 0.12 | `main-20261024d/verdict.json:probes` |
| Matched-cut rate, UNDERCUT minus RAISE (descriptive, D-048) | 0.38 | `main-20261024d/verdict.json` |
| Paired probe comparison (D-050): undercut_minus_raise_signature [CI] | 0.21 [0.04, 0.38] (n=24) | `main-20261024d/verdict.json:paired_probe_comparisons` |
| Paired probe comparison (D-050): undercut_minus_raise_matched_cut [CI] | 0.38 [0.17, 0.58] (n=24) | `main-20261024d/verdict.json:paired_probe_comparisons` |
| Paired probe comparison (D-050): swap_other_undercut_minus_swap_other_raise_signature [CI] | 0.08 [-0.12, 0.29] (n=24) | `main-20261024d/verdict.json:paired_probe_comparisons` |
| Paired probe comparison (D-050): swap_other_undercut_minus_swap_other_raise_matched_cut [CI] | 0.33 [0.04, 0.58] (n=24) | `main-20261024d/verdict.json:paired_probe_comparisons` |
| Paired probe comparison (D-050): swap_other_undercut_minus_undercut_signature [CI] | 0.00 [-0.21, 0.21] (n=24) | `main-20261024d/verdict.json:paired_probe_comparisons` |
| Paired probe comparison (D-050): swap_other_undercut_minus_undercut_matched_cut [CI] | 0.08 [-0.17, 0.33] (n=24) | `main-20261024d/verdict.json:paired_probe_comparisons` |
| Behavioural screen flag (descriptive) — D-050, D-053: at least the required share of prefixes with both a high pre-fork Delta and an UNDERCUT signature; lower bounds above 0 for UNDERCUT minus RAISE signatures; all paired by prefix | False | `main-20261024d/verdict.json` |
| Punishment flag with the newcomer (SWAP_OTHER) — D-053: at least the required share of prefixes with a SWAP_OTHER_UNDERCUT signature; lower bounds above 0 for SWAP_OTHER_UNDERCUT minus SWAP_OTHER_RAISE signatures; all paired by prefix | False | `main-20261024d/verdict.json` |
| High-price stratum prefixes | 11 of 24 | `main-20261024d/prefixes.csv` |
