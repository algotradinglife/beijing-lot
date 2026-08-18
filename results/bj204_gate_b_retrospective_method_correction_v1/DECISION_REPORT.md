# #204 Gate B — bounded market-residual model decision

## Scope

This is the single PI-authorized RETROSPECTIVE_METHOD_CORRECTION. It tests a conservative one-direction-plus-scalar anchored residual control, not a fully joint learned residual encoder and not every possible neural residual hypothesis. It is proxy-grade research only and grants no betting, ROI, ticket, production, #205, or #210 authority.

## Frozen selection

The development-only expanding-CV rule selected `LOGISTIC_RESIDUAL`. No locked-test metric selected a model or hyperparameter.

## Locked 75-issue result

- Matched market-label rows: 16833.
- Model-only log loss: 1.143112; market: 1.147860; lift: -0.004748.
- Model-only Brier: 0.696018; market: 0.696426.
- Model-only ECE: 0.123924; market: 0.099572.
- Model-only Top1/Top2: 0.401770 / 0.707955; market: 0.399513 / 0.687697.

## Residual ablation versus the matched market baseline

Negative log-loss/Brier/ECE lift is better. These one-shot retrospective values cannot authorize promotion without #210.
| Residual family | log-loss lift vs market | Brier lift | ECE lift | mean delta-logit L1 |
|---|---:|---:|---:|---:|
| HIST_GRADIENT_RESIDUAL | -0.005100 | -0.000724 | +0.028173 | 0.322149 |
| ISSUE_CONTEXT_SUMMARY_MLP_RESIDUAL | -0.009524 | -0.002857 | +0.035777 | 0.598036 |
| LOGISTIC_RESIDUAL | -0.004748 | -0.000409 | +0.024352 | 0.268521 |

## Fitted anchored scale

Alpha is fitted on the corresponding training window only with the frozen market offset inside the loss.
| Residual family | Seed | fitted alpha | market train log loss | anchored train log loss |
|---|---:|---:|---:|---:|
| HIST_GRADIENT_RESIDUAL | 204001 | 0.53595290 | 1.15661516 | 1.14918532 |
| HIST_GRADIENT_RESIDUAL | 204002 | 0.53279076 | 1.15661516 | 1.14931209 |
| HIST_GRADIENT_RESIDUAL | 204003 | 0.54394923 | 1.15661516 | 1.14908592 |
| ISSUE_CONTEXT_SUMMARY_MLP_RESIDUAL | 204001 | 0.53348926 | 1.15661516 | 1.14677212 |
| ISSUE_CONTEXT_SUMMARY_MLP_RESIDUAL | 204002 | 0.57464683 | 1.15661516 | 1.14576287 |
| ISSUE_CONTEXT_SUMMARY_MLP_RESIDUAL | 204003 | 0.60800551 | 1.15661516 | 1.14550265 |
| LOGISTIC_RESIDUAL | 204001 | 0.44515601 | 1.15661516 | 1.15108044 |
| LOGISTIC_RESIDUAL | 204002 | 0.44515601 | 1.15661516 | 1.15108044 |
| LOGISTIC_RESIDUAL | 204003 | 0.44515601 | 1.15661516 | 1.15108044 |

## Safe fallback interpretation

The frozen OOD rule marked 0 of 16968 market-eligible locked-test rows as OOD; model output was used on 16968 and exact market fallback on 0. The fallback-mixed log loss is 1.143112.
The issue-context summary MLP used learned output on 0 of 16968 market-eligible locked-test rows; 16968 fell back and 16968 were OOD. When model-used coverage is zero, its raw MODEL_ONLY_COVERED score is diagnostic only and its safe-mixed path supplies no learned-model evidence.
Expected missing predicted-SP inputs are median-imputed with indicators and do not become synthetic OOD. This retrospective method correction cannot promote a probability or SP model; #210 remains the sole strict confirmation.

## Decision

`RETROSPECTIVE_METHOD_CORRECTION_PENDING_PI_TERMINAL_REVIEW`: retain the frozen market/NO_BET fallback, do not retune or rerun, and submit this one-shot package to PI.
