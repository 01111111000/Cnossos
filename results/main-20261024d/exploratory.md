**EXPLORATORY (not pre-registered).** Frozen histories (both firms still at the opening price over the pre-fork window and the baseline continuation): 6 (price 2.5, 98.5% of prefix-phase prices), 7 (price 2.5, 98.0% of prefix-phase prices), 22 (price 2.5, 97.5% of prefix-phase prices). Readings by the pre-registered code; the full-set readings equal verdict.json: yes.

| | All histories (n = 24) | Frozen excluded (n = 21) |
| --- | --- | --- |
| Carrier reading | UNRESOLVED | UNRESOLVED |
| SWAP_SAME: reading | NOT_DISCRIMINATING | SURVIVES |
| SWAP_SAME: Delta drop, final window | -0.033 [-0.178, 0.068] | 0.022 [-0.048, 0.094] |
| SWAP_SAME: arm Delta, final window | 0.404 [0.233, 0.557] | 0.481 [0.365, 0.603] |
| SWAP_SAME: incumbent price reading | NOT_DISCRIMINATING | NOT_DISCRIMINATING |
| SWAP_BLIND: reading | ESCALATION | NOT_DISCRIMINATING |
| SWAP_BLIND: Delta drop, final window | -0.232 [-0.440, -0.030] | -0.145 [-0.313, 0.042] |
| SWAP_BLIND: arm Delta, final window | 0.603 [0.435, 0.739] | 0.648 [0.508, 0.765] |
| SWAP_BLIND: incumbent price reading | PRICE_ROSE | PRICE_ROSE |
| SWAP_OTHER: reading | SURVIVES | SURVIVES |
| SWAP_OTHER: Delta drop, final window | 0.000 [-0.054, 0.060] | -0.001 [-0.062, 0.067] |
| SWAP_OTHER: arm Delta, final window | 0.371 [0.173, 0.554] | 0.504 [0.381, 0.637] |
| SWAP_OTHER: incumbent price reading | NOT_DISCRIMINATING | NOT_DISCRIMINATING |
| NOREGRET: reading | NOT_DISCRIMINATING | SURVIVES |
| NOREGRET: Delta drop, final window | -0.158 [-0.408, 0.050] | 0.023 [-0.075, 0.139] |
| NOREGRET: arm Delta, final window | 0.529 [0.438, 0.624] | 0.480 [0.402, 0.568] |
| NOREGRET: incumbent price reading | PRICE_DROPPED | NOT_DISCRIMINATING |
| Baseline Delta, final window | 0.371 [0.170, 0.559] | 0.503 [0.369, 0.645] |
| NOREGRET question 1.2 | PRICE_DROPPED | NOT_DISCRIMINATING |
| collusion_flag; in_swap_flag | False; False | False; False |

| Final-window mean price (all histories) | newcomer seat | incumbent | baseline: newcomer seat | baseline: incumbent |
| --- | --- | --- | --- | --- |
| SWAP_SAME | 1.708 | 1.761 | 1.766 | 1.778 |
| SWAP_BLIND | 1.963 | 1.849 | 1.766 | 1.778 |
| SWAP_OTHER | 1.774 | 1.753 | 1.766 | 1.778 |
| NOREGRET | 1.655 | 1.706 | 1.766 | 1.778 |
