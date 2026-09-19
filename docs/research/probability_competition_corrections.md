# Probability quality, competition composition and restrained correction

This is a retrospective probability diagnostic on the same 484 issues / 36,140 fixtures as the independent foundation evaluation. It does not evaluate purchases or ROI, fit experts, clean source data, or claim unseen testing. RAW is mapped market probability; FROZEN is the old correction used by JOINT; DYNAMIC is the existing 49-block handicap correction. JOINT is not itself a probability model.

## Conclusions

- Competition composition does not explain most of the drawdown-segment probability deterioration. Among common competition × handicap strata, RAW's before-to-drawdown composition effect is approximately −0.000992 Brier, while within-stratum deterioration is +0.00513. Common-support exclusions are published, not imputed.
- Using 25% of the dynamic correction substantially removes its damage, but improves aggregate Brier by only 0.00000838 versus RAW and nets three additional Top2 hits. Before-segment Brier worsens. This is not sufficient evidence of a superior foundation.
- Half-strength, sparse shrinkage and the local historical-evidence gate remain worse than RAW overall. The local gate's historical draw-frequency evidence does not establish predictive benefit on new targets.
- Retain RAW as the evaluation reference. Do not promote a correction based on these tiny aggregate differences and do not change purchase strategy based on this study.

## Scope and source limits

Native competition labels match all target fixtures through exact issue/slot/provider identity in read-only SPF observations. Each admitted payload and its original source reference is retained. These are Nowscore descriptive metadata, not pre-match availability receipts or Titan team membership. The explicit competition dictionary has 62 unclassified fixtures; 1,398 league fixtures have unknown division. Ambiguous names remain unknown. Domestic cup does not imply a cross-tier match.

The registered `cross-tier-expert-v1` archive (SHA256 `718e58d99b20339db7cac7792b7ecc6efbb7f72e1ff4ccec9959432eab065ee6`) contains 23 predictions from 100101–100103, no overlap with this sample. No target team-tier linkage is supplied by the frozen inputs; cross-tier explanations remain untested, with all target cross-tier tags explicitly unknown. No comparable complete score grid is available across models; conclusions apply to handicap W/D/L.

## Fixed candidate policies

Every target calls `draw_correction_candidates` with an explicit shared Cutoff. It first invokes the existing `draw_handicap_predict`, verifying the sealed artifact, original implementation and shared chronology closure. The original 49 blocks/cadence remain unchanged; no new threshold/weight tuning occurs.

- WEAK_0.25 / WEAK_0.5: multiply the original correction by the stated fixed fraction.
- SPARSE: multiply by frozen handicap cell support `n/(n+100)`.
- LOCAL: enable full correction only for historical support n≥100 and a Wilson interval with z=1.96 excluding target RAW draw probability in the same direction as the existing correction. This is an untuned heuristic, not a significance claim or a fitted performance gate.

All preserve RAW W:L ratio and normalization. Per-issue artifacts bind Cutoff, original model seal and historical context, policies, inputs, implementation and outputs. Predictions are saved before opening target evaluation labels. Historical proxy/legacy admissibility remains false. Replay compares with source frozen probabilities independently; post-cutoff label/time mutation tests exercise fitting through all candidate outputs. No future-issue cache reuse or new private chronology machinery is introduced.

## Deliverables and tests

- `src/probability_competition_labels.py::read_competition_labels` ↔ `tests/test_probability_competition_labels.py`: exact identity, missing values, conflict failure, provenance digest, empty input and duplicate rejection.
- `r/probability_competition_diagnostic.R::{probability_competition_decomposition,probability_competition_tags}` ↔ `tests/testthat/test-probability-competition-diagnostic.R`: additive reconciliation, explicit common-support exclusions, invalid data, dictionary uniqueness and unknowns.
- `r/draw_correction_candidates.R::draw_correction_candidates` ↔ `tests/testthat/test-draw-correction-candidates.R`: fixed weights, local gate activation, normalization, W:L preservation, cutoff/label rejection, future mutation invariance and evaluation identity validation.
- `quarto/188_probability_competition_diagnostic.qmd`: three foundations, competition/type/tier/handicap scores and paired movements, composition and support ledgers.
- `quarto/189_probability_correction_candidates.qmd`: immutable per-issue candidate generation and scoring; explicitly binds evaluation QMD and scoring code as well as generation code.
- `quarto/190_probability_competition_conclusion.qmd`: hash-verified consolidated conclusions and diagnostic figures.

Targeted tests use the declared project Python and R library. Full unrelated repository tests are not claimed by this scoped diagnostic; no merge is performed. Final receipts record exact checks, independent replay, rendered reports and Codex review. Persistent outputs are under `audits/probability-competition-v2`, `audits/probability-correction-candidates-v3`, and `audits/probability-competition-conclusion-v1` in the mounted data root. Earlier candidate directories are superseded attempts, not accepted releases.
