# N7 Protected Ticket Hard Gate

## Scope

- 固定每期 `256` units。
- 当前对照：`144` N7 core + `48` original top-EV draw protected sleeve + `64` N5 overlap。
- 新规则只 gate protected sleeve；不触发时，空出的 protected 预算通过既有 fallback 进入 N5 quality/overlap。
- Gate inputs use `1h` market snapshot only: draw probability and Asian handicap line_gap. No final SP or result is used by the selector.
- Draw threshold: `0.24`; strict gap threshold: `0.5`.

## Decision

- 综合推荐分最高：`current_c144_p48_original_n5ov64`，profit `204,500`，ROI `1.19`，maxDD `-17,102`，近三年 profit `82,986`，ex-best ROI `0.66`。
- 在 maxDD 不差于当前原始方案的约束下，最好的是：`current_c144_p48_original_n5ov64`，profit `204,500`，ROI `1.19`，maxDD `-17,102`。

## Gate Raw Summary

| gate | tickets | issues | rescues | protected_hits | avg_draw_1h_p | avg_line_gap | base_raw_profit | protected_raw_profit | delta_raw_profit | base_raw_stake | protected_raw_stake | incremental_raw_stake | protected_raw_roi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| action_hcp | 567 | 567 | 3 | 6 | 0.1944 | 0.6514 | 2352.2394 | 11954.1980 | 9601.9586 | 6352.8229 | 12705.6459 | 6352.8229 | 0.9409 |
| action_hcp_lowdraw | 547 | 547 | 3 | 6 | 0.1923 | 0.6333 | 2571.1890 | 12392.0972 | 9820.9082 | 6133.8733 | 12267.7466 | 6133.8733 | 1.0101 |
| action_hcp_posgap | 564 | 564 | 3 | 6 | 0.1948 | 0.6555 | 2389.4758 | 12028.6707 | 9639.1949 | 6315.5866 | 12631.1731 | 6315.5866 | 0.9523 |
| strict | 544 | 544 | 3 | 6 | 0.1926 | 0.6374 | 2608.4254 | 12466.5699 | 9858.1446 | 6096.6369 | 12193.2739 | 6096.6369 | 1.0224 |
| strict_gap05 | 408 | 408 | 2 | 4 | 0.2015 | 0.7264 | -1796.0567 | 1315.7261 | 3111.7828 | 4554.2863 | 9108.5726 | 4554.2863 | 0.1444 |


## Same 48-Unit Protected Sleeve Comparison

| portfolio | gate | core_units | protect_units | n5_units | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_units | recent_roi | roi_ex_best_issue | profit_to_dd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_c144_p48_original_n5ov64 | original | 144.0000 | 48.0000 | 64.0000 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | -17101.6084 | 8 | 82986.4323 | 2.5129 | 0.6587 | 11.9579 |
| gate_action_hcp_lowdraw_c144_p48_n5ov64 | action_hcp_lowdraw | 144.0000 | 48.0000 | 64.0000 | 162749.0361 | 0.9503 | 0.1106 | 0.4395 | -16339.5760 | 8 | 37931.9384 | 1.1486 | 0.4146 | 9.9604 |
| gate_strict_c144_p48_n5ov64 | strict | 144.0000 | 48.0000 | 64.0000 | 162749.0361 | 0.9503 | 0.1106 | 0.4395 | -16339.5760 | 8 | 37931.9384 | 1.1486 | 0.4146 | 9.9604 |
| gate_action_hcp_c144_p48_n5ov64 | action_hcp | 144.0000 | 48.0000 | 64.0000 | 162002.9913 | 0.9459 | 0.1106 | 0.4395 | -16339.5760 | 8 | 37931.9384 | 1.1486 | 0.4102 | 9.9148 |
| gate_action_hcp_posgap_c144_p48_n5ov64 | action_hcp_posgap | 144.0000 | 48.0000 | 64.0000 | 162002.9913 | 0.9459 | 0.1106 | 0.4395 | -16339.5760 | 8 | 37931.9384 | 1.1486 | 0.4102 | 9.9148 |
| gate_strict_gap05_c144_p48_n5ov64 | strict_gap05 | 144.0000 | 48.0000 | 64.0000 | 143317.5856 | 0.8368 | 0.1181 | 0.4395 | -15367.4476 | 8 | 41127.5753 | 1.2454 | 0.3010 | 9.3261 |
| baseline_core192_n5ov64 | none | 192.0000 | 0.0000 | 64.0000 | 174357.8842 | 1.0181 | 0.1031 | 0.4380 | -17150.0609 | 10 | 40495.9388 | 1.2263 | 0.3065 | 10.1666 |


## Top Recommended Score

| portfolio | gate | core_units | protect_units | n5_units | profit_units | roi | max_drawdown_units | max_dead_streak | recent_profit_units | roi_ex_best_issue | recommended_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_c144_p48_original_n5ov64 | original | 144.0000 | 48.0000 | 64.0000 | 204499.7081 | 1.1941 | -17101.6084 | 8 | 82986.4323 | 0.6587 | 320954.7202 |
| gate_action_hcp_lowdraw_c144_p64_n5ov48 | action_hcp_lowdraw | 144.0000 | 64.0000 | 48.0000 | 171464.5098 | 1.0012 | -17954.4291 | 8 | 38562.4081 | 0.4682 | 222157.4449 |
| gate_strict_c144_p64_n5ov48 | strict | 144.0000 | 64.0000 | 48.0000 | 171464.5098 | 1.0012 | -17954.4291 | 8 | 38562.4081 | 0.4682 | 222157.4449 |
| gate_action_hcp_c144_p64_n5ov48 | action_hcp | 144.0000 | 64.0000 | 48.0000 | 170469.7834 | 0.9954 | -17954.4291 | 8 | 38562.4081 | 0.4624 | 220639.2028 |
| gate_action_hcp_posgap_c144_p64_n5ov48 | action_hcp_posgap | 144.0000 | 64.0000 | 48.0000 | 170469.7834 | 0.9954 | -17954.4291 | 8 | 38562.4081 | 0.4624 | 220639.2028 |
| baseline_core192_n5ov64 | none | 192.0000 | 0.0000 | 64.0000 | 174357.8842 | 1.0181 | -17150.0609 | 10 | 40495.9388 | 0.3065 | 213992.7033 |
| gate_action_hcp_lowdraw_c144_p48_n5ov64 | action_hcp_lowdraw | 144.0000 | 48.0000 | 64.0000 | 162749.0361 | 0.9503 | -16339.5760 | 8 | 37931.9384 | 0.4146 | 210852.3549 |
| gate_strict_c144_p48_n5ov64 | strict | 144.0000 | 48.0000 | 64.0000 | 162749.0361 | 0.9503 | -16339.5760 | 8 | 37931.9384 | 0.4146 | 210852.3549 |
| gate_action_hcp_c144_p48_n5ov64 | action_hcp | 144.0000 | 48.0000 | 64.0000 | 162002.9913 | 0.9459 | -16339.5760 | 8 | 37931.9384 | 0.4102 | 209713.6733 |
| gate_action_hcp_posgap_c144_p48_n5ov64 | action_hcp_posgap | 144.0000 | 48.0000 | 64.0000 | 162002.9913 | 0.9459 | -16339.5760 | 8 | 37931.9384 | 0.4102 | 209713.6733 |
| gate_action_hcp_lowdraw_c144_p32_n5ov80 | action_hcp_lowdraw | 144.0000 | 32.0000 | 80.0000 | 154033.5624 | 0.8994 | -15498.0310 | 8 | 37301.4688 | 0.3609 | 198155.3103 |
| gate_strict_c144_p32_n5ov80 | strict | 144.0000 | 32.0000 | 80.0000 | 154033.5624 | 0.8994 | -15498.0310 | 8 | 37301.4688 | 0.3609 | 198155.3103 |


## Top Profit

| portfolio | gate | core_units | protect_units | n5_units | profit_units | roi | max_drawdown_units | max_dead_streak | recent_profit_units | roi_ex_best_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_c144_p48_original_n5ov64 | original | 144.0000 | 48.0000 | 64.0000 | 204499.7081 | 1.1941 | -17101.6084 | 8 | 82986.4323 | 0.6587 |
| baseline_core192_n5ov64 | none | 192.0000 | 0.0000 | 64.0000 | 174357.8842 | 1.0181 | -17150.0609 | 10 | 40495.9388 | 0.3065 |
| gate_action_hcp_lowdraw_c144_p64_n5ov48 | action_hcp_lowdraw | 144.0000 | 64.0000 | 48.0000 | 171464.5098 | 1.0012 | -17954.4291 | 8 | 38562.4081 | 0.4682 |
| gate_strict_c144_p64_n5ov48 | strict | 144.0000 | 64.0000 | 48.0000 | 171464.5098 | 1.0012 | -17954.4291 | 8 | 38562.4081 | 0.4682 |
| gate_action_hcp_c144_p64_n5ov48 | action_hcp | 144.0000 | 64.0000 | 48.0000 | 170469.7834 | 0.9954 | -17954.4291 | 8 | 38562.4081 | 0.4624 |
| gate_action_hcp_posgap_c144_p64_n5ov48 | action_hcp_posgap | 144.0000 | 64.0000 | 48.0000 | 170469.7834 | 0.9954 | -17954.4291 | 8 | 38562.4081 | 0.4624 |
| gate_action_hcp_lowdraw_c144_p48_n5ov64 | action_hcp_lowdraw | 144.0000 | 48.0000 | 64.0000 | 162749.0361 | 0.9503 | -16339.5760 | 8 | 37931.9384 | 0.4146 |
| gate_strict_c144_p48_n5ov64 | strict | 144.0000 | 48.0000 | 64.0000 | 162749.0361 | 0.9503 | -16339.5760 | 8 | 37931.9384 | 0.4146 |
| gate_action_hcp_c144_p48_n5ov64 | action_hcp | 144.0000 | 48.0000 | 64.0000 | 162002.9913 | 0.9459 | -16339.5760 | 8 | 37931.9384 | 0.4102 |
| gate_action_hcp_posgap_c144_p48_n5ov64 | action_hcp_posgap | 144.0000 | 48.0000 | 64.0000 | 162002.9913 | 0.9459 | -16339.5760 | 8 | 37931.9384 | 0.4102 |
| gate_action_hcp_lowdraw_c144_p32_n5ov80 | action_hcp_lowdraw | 144.0000 | 32.0000 | 80.0000 | 154033.5624 | 0.8994 | -15498.0310 | 8 | 37301.4688 | 0.3609 |
| gate_strict_c144_p32_n5ov80 | strict | 144.0000 | 32.0000 | 80.0000 | 154033.5624 | 0.8994 | -15498.0310 | 8 | 37301.4688 | 0.3609 |


## MaxDD Not Worse Than Current

| portfolio | gate | profit_units | roi | max_drawdown_units | max_dead_streak | recent_profit_units | roi_ex_best_issue | profit_to_dd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_c144_p48_original_n5ov64 | original | 204499.7081 | 1.1941 | -17101.6084 | 8 | 82986.4323 | 0.6587 | 11.9579 |
| gate_action_hcp_lowdraw_c144_p48_n5ov64 | action_hcp_lowdraw | 162749.0361 | 0.9503 | -16339.5760 | 8 | 37931.9384 | 0.4146 | 9.9604 |
| gate_strict_c144_p48_n5ov64 | strict | 162749.0361 | 0.9503 | -16339.5760 | 8 | 37931.9384 | 0.4146 | 9.9604 |
| gate_action_hcp_c144_p48_n5ov64 | action_hcp | 162002.9913 | 0.9459 | -16339.5760 | 8 | 37931.9384 | 0.4102 | 9.9148 |
| gate_action_hcp_posgap_c144_p48_n5ov64 | action_hcp_posgap | 162002.9913 | 0.9459 | -16339.5760 | 8 | 37931.9384 | 0.4102 | 9.9148 |
| gate_action_hcp_lowdraw_c144_p32_n5ov80 | action_hcp_lowdraw | 154033.5624 | 0.8994 | -15498.0310 | 8 | 37301.4688 | 0.3609 | 9.9389 |
| gate_strict_c144_p32_n5ov80 | strict | 154033.5624 | 0.8994 | -15498.0310 | 8 | 37301.4688 | 0.3609 | 9.9389 |
| gate_action_hcp_c144_p32_n5ov80 | action_hcp | 153536.1992 | 0.8965 | -15498.0310 | 8 | 37301.4688 | 0.3580 | 9.9068 |
| gate_action_hcp_posgap_c144_p32_n5ov80 | action_hcp_posgap | 153536.1992 | 0.8965 | -15498.0310 | 8 | 37301.4688 | 0.3580 | 9.9068 |
| gate_action_hcp_lowdraw_c144_p24_n5ov88 | action_hcp_lowdraw | 149675.8255 | 0.8739 | -15077.2584 | 8 | 36986.2340 | 0.3341 | 9.9273 |
| gate_strict_c144_p24_n5ov88 | strict | 149675.8255 | 0.8739 | -15077.2584 | 8 | 36986.2340 | 0.3341 | 9.9273 |
| gate_action_hcp_c144_p24_n5ov88 | action_hcp | 149302.8031 | 0.8718 | -15077.2584 | 8 | 36986.2340 | 0.3319 | 9.9025 |


## Interpretation

- `action_hcp` tests only the structural rescue profile: `0->10` and Beidan hcp `-2`.
- `strict` additionally requires low 1h draw probability and positive line_gap.
- If strict gates lose too much profit, the observed rescue profile is better used as a diagnostic tag than as a hard production gate.
- Figure: `docs/research/figures/n7_protection_gate_equity_2026-06-28.svg`
