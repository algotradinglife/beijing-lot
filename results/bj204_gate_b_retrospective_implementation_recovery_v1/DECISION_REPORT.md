# #204 Gate B — bounded market-residual model decision

## Scope

This is a RETROSPECTIVE_IMPLEMENTATION_RECOVERY: pre-label residual corrections were frozen before the invalid v1 execution. It is proxy-grade research only and grants no betting, ROI, ticket, production, #205, or #210 authority.

## Frozen selection

The development-only expanding-CV rule selected `MARKET_ONLY`. No locked-test metric selected a model or hyperparameter.

## Locked 75-issue result

- Matched market-label rows: 16833.
- Model-only log loss: 1.147860; market: 1.147860; lift: 0.000000.
- Model-only Brier: 0.696426; market: 0.696426.
- Model-only ECE: 0.099572; market: 0.099572.
- Model-only Top1/Top2: 0.399513 / 0.687697; market: 0.399513 / 0.687697.

## Residual ablation versus the matched market baseline

Positive log-loss/Brier/ECE lift is worse; every pre-registered residual is worse on the locked test.
| Residual family | log-loss lift vs market | Brier lift | ECE lift | mean delta-logit L1 |
|---|---:|---:|---:|---:|
| HIST_GRADIENT_RESIDUAL | +0.002154 | +0.004406 | +0.053763 | 0.599276 |
| ISSUE_CONTEXT_SUMMARY_MLP_RESIDUAL | +0.015964 | +0.007880 | +0.063636 | 1.051034 |
| LOGISTIC_RESIDUAL | +0.004147 | +0.006439 | +0.057616 | 0.603206 |

## Safe fallback interpretation

The development-only rule selected the frozen MARKET_ONLY baseline. It is not a learned-model fallback event: it has zero model attempts, zero fallback substitutions, and zero OOD classifications.
Expected missing predicted-SP inputs are median-imputed with indicators and do not become synthetic OOD. This recovery cannot promote a probability or SP model; #210 remains the sole strict confirmation.

## Decision

`NO_PROMOTION_PENDING_PI_REVIEW`: retain the frozen market/NO_BET fallback and do not retune against the locked test.
