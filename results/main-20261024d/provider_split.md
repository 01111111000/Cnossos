**EXPLORATORY (D-060, D-062): not pre-registered; serving stack confounded with prefix number.** Intervals: expanded_percentile bootstrap, 0.95, 10000 resamples, seed 1729, within each group.

| SWAP_OTHER (newcomer: gpt-oss-120b) | cerebras | modal-vllm | all |
| --- | --- | --- | --- |
| Prefixes (n) | 18: 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17 | 6: 18,19,20,21,22,23 | 24: 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23 |
| Baseline final-window Delta | 0.318 [0.103, 0.516] | 0.530 [-0.148, 0.948] | 0.371 [0.170, 0.559] |
| SWAP_OTHER final-window Delta | 0.331 [0.114, 0.522] | 0.491 [-0.172, 0.944] | 0.371 [0.173, 0.554] |
| Delta drop vs baseline, final window | -0.012 [-0.080, 0.061] | 0.039 [-0.004, 0.149] | 0.000 [-0.054, 0.060] |
| Delta drop vs baseline, early window | -0.064 [-0.107, -0.024] | 0.019 [-0.001, 0.077] | -0.043 [-0.079, -0.010] |
| Newcomer final-window price | 1.746 [1.611, 1.919] | 1.859 [1.605, 2.262] | 1.774 [1.653, 1.923] |
| Newcomer price drop vs the replaced firm's baseline | -0.014 [-0.046, 0.020] | 0.011 [-0.013, 0.060] | -0.008 [-0.033, 0.019] |
| Incumbent price drop vs its baseline | 0.021 [-0.019, 0.086] | 0.036 [-0.001, 0.117] | 0.025 [-0.009, 0.071] |
| Share of branch periods the newcomer priced below the incumbent | 0.236 | 0.208 | 0.229 |
| SWAP_OTHER_UNDERCUT: signature rate; matched-cut rate | 0.222; 0.500 | 0.167; 0.333 | 0.208; 0.458 |
| SWAP_OTHER_RAISE: signature rate; matched-cut rate; matched-raise rate | 0.111; 0.111; 0.389 | 0.167; 0.167; 0.167 | 0.125; 0.125; 0.333 |

Newcomer calls by endpoint, per prefix: {"0": {"api.cerebras.ai": 38}, "1": {"api.cerebras.ai": 38}, "2": {"api.cerebras.ai": 38}, "3": {"api.cerebras.ai": 38}, "4": {"api.cerebras.ai": 38}, "5": {"api.cerebras.ai": 38}, "6": {"api.cerebras.ai": 38}, "7": {"api.cerebras.ai": 38}, "8": {"api.cerebras.ai": 38}, "9": {"api.cerebras.ai": 38}, "10": {"api.cerebras.ai": 38}, "11": {"api.cerebras.ai": 38}, "12": {"api.cerebras.ai": 38}, "13": {"api.cerebras.ai": 38}, "14": {"api.cerebras.ai": 38}, "15": {"api.cerebras.ai": 38}, "16": {"api.cerebras.ai": 38}, "17": {"api.cerebras.ai": 38}, "18": {"redacted-modal-endpoint.invalid": 38}, "19": {"redacted-modal-endpoint.invalid": 38}, "20": {"redacted-modal-endpoint.invalid": 38}, "21": {"redacted-modal-endpoint.invalid": 38}, "22": {"redacted-modal-endpoint.invalid": 38}, "23": {"redacted-modal-endpoint.invalid": 38}}
Prefixes whose newcomer calls disagree with the recorded stack: none
