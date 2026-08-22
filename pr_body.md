Closes #306

# Issue #306 — state-dependent expert composition and dynamic funding intensity

## Verdict: EXPERT_VALUE_SIGNAL / NO PROMOTION

Dynamic policy (Stage A keep/skip + Stage C composition + Stage C intensity):
2023 terminal **CNY109,091.87 (+9.09%)** vs exact B0_BEST_FULL
**CNY79,248.96 (-20.75%)** → matched lift **+29.84pp / +29,842.90 CNY**;
beats cash, #299 residual, static mixture, issue-block shuffle and
expert-identity shuffle on identical 227-issue support.

**Decomposition** (the interesting finding):

- Stage A keep/skip alone: **+10,373 CNY** (frozen head funds 11/35 active issues)
- Composition at a *fixed* intensity: **+0 CNY** — the fixed funding fraction
  selected on earlier expanding OOF folds collapses to **0%**, exactly
  reproducing #302's "global funding scalar → zero" result
- **Dynamic (state-dependent) intensity: +19,470 CNY** — the learned
  state-dependent funding fraction deploys non-zero exposure on 46% of 2023
  issues and is where the expert layer adds value

**Falsification**: exact executed-exposure null percentile **0.75 < 0.95**
barrier; the same bundle copies placed randomly beat the primary in the tail.
No promotion, no #210 access, 2024+ stays sealed.

## Stage A note for PI

`stage_a_source = LOCAL_REFERENCE_FIT_PENDING_305` — #305 is a PI-owned
in-flight correction; until its frozen output lands at
`results/issue-305/keep_skip_predictions.csv`, this delivery uses a local
reference fit with identical semantics (issue features + BEST_FULL labels only;
`expert_label_inputs=0` in every receipt; byte-invariant to expert-label
mutation, proven by test). Re-running after #305 merges is ≈40 s.

## Deliverables

- Executed notebook: `notebooks/research/issue-306/bj306_dynamic_moe.ipynb`
- Package: `src/issue306/` (panel / stage_a / value_model / portfolio /
  evaluation / controls / experiment)
- Focused tests: `tests/issue306/` — 15 passed incl. Stage-A invariance and
  tamper self-tests (manifest hash drift, settlement tamper, sealed 2024)
- Artifacts: `results/issue-306/` (28 files, manifest-verified)
- Decision report: `docs/research/Issue-306-State-Dependent-Expert-Composition.md`
- Roadmap update: `docs/research/roadmap.md`