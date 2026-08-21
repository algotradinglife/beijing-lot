# Beijing-lot Research Roadmap v1.0

## Project Positioning

Beijing-lot is a research system for studying:

- market information efficiency;
- decision chains;
- portfolio construction;
- long-term forward validation.

The objective is not to find a guaranteed prediction method, but to establish an auditable evidence chain.

```
Market Information
        ↓
Decision Information
        ↓
Portfolio Decision
        ↓
Forward Validation
```

## Integrated planning control plane

The historical Phase 0–5 record below remains the narrative research history.
GitHub planning uses a complementary cross-Project maturity roadmap:

| Layer | Responsibility |
| --- | --- |
| Project | The one durable functional home of an Issue; membership determines the responsible role |
| Milestone | The one PI-owned cross-Project maturity stage advanced by an Issue |
| Native Issue Graph | `blockedBy` / `blocking` dependencies and `parent` / `subIssues` decomposition |
| Issue Type | The authoritative kind of work |
| Project Status | The authoritative lifecycle state |
| Labels | Non-authoritative domain and work-type taxonomy only |
| Local Research OS | Derived cache or execution notes; never the planning source of truth |

The three Projects are:

- **BJ Data Platform** — sources, provenance, immutable datasets, freezes, and
  settlement truth;
- **BJ Prediction & Betting** — probability, models, decision chains,
  portfolios, and paper-only betting research;
- **BJ Product & Operations** — product workflows, runtime operations,
  observability, reliability, and the Research OS control plane.

The integrated maturity stages are:

| Milestone | Lifecycle | Stage question or goal |
| --- | --- | --- |
| M0 — Controlled Research Foundation | Completed | Is the auditable control plane needed to conduct research in place? |
| M1 — Research Data Readiness | Active | Which historical and forward assets support which claims under which provenance, time, and quality boundaries? |
| M2 — Probability and Model Evidence | Planned | Do market information and timestamp-safe football context add calibrated, reproducible probability information? |
| M3 — Decision and Portfolio Paper Evaluation | Planned | Do decision-chain and portfolio layers add separately measurable paper-only value? |
| M4 — Forward Operational Validation | Planned | Can frozen candidates operate prospectively and repeatedly under real collection, timing, and settlement conditions? |
| M5 — Release Readiness and Continuous Research | Planned | Has any candidate earned a separate controlled release review? |

Only PI may define, activate, close, rename, or change the lifecycle of a
Milestone. `Active` does not make every Issue in a stage executable, and
`Planned` is not dispatch or release authority. Each Issue still requires its
own contract and routing state. No Milestone authorizes execution, frontend
selectability, ROI claims, or automatic promotion to a later stage.

See
[`github_milestone_governance.md`](github_milestone_governance.md)
for the operating contract and
[`github_milestone_governance_receipt.md`](github_milestone_governance_receipt.md)
for the initial live mapping.

## Current unified-model roadmap

Updated: **2026-08-21 19:43 HKT (#291 rare-event value heads isolated a base Top-64 candidate; protection remains rejected and #292 awaits scope review)**

The active program is [#202], which turns each issue's match × outcome tensor
into a four-stage decision path: probability/value representation, constrained
ticket construction, bankroll policy, and forward validation. Native GitHub
Issue Graph edges below are the execution authority; this section records the
PI interpretation and does not replace those edges or Project states.

```text
#203 causal M×3 tensor (Done)
             |
             v
#204 market-anchored probability/SP PoC (Done; market baseline retained)
             |
             v
#205 M×3 value matrix + fixed-N7 calibration (Done; market baseline retained)
             |
             v
#206 fixed-N7 ticket learning (Done; learned policy rejected, baseline unresolved)
             |
             v
#207 ¥100k active bankroll + separate NO_BET safety lane (Done; no overlay Edge)

#208 dynamic N×K risk-conditioned frontier (Cancelled; superseded by #209)

#229 divergence causal-data profile (Done; BLOCKED_DATA_DEFECT)
             |
             v
#232 restore causal SP-backed divergence support (Done; proxy handoff accepted)
  ├─ #234 source/schema freeze (Done)
  ├─ #235 historical native-SP recovery (Cancelled)
  ├─ #236 historical European proxy (Done)
  ├─ #268 complete historical proxy backfill (Done)
  ├─ #237 power features (Inbox; deferred optional model input)
  ├─ #248 prospective multi-timepoint snapshots (Done; accumulating forward evidence)
  ├─ #249 database portability (Done)
  └─ #238 divergence materializer (Done; three historical proxy horizons accepted)
             |
             v
#209 learned action-conditioned policy (Done; dynamic mapping, no promotion)
             |
             v
#279 action-aware feature factory + 2023 issue attribution (Done)
             |
             v
#282 conditional M×3 action-value and distinct-ticket policy (Done; no learned Edge)
             |
             v
#284 issue-normalized N×3 subset and joint-action atlas (Done; conditional-K clue)
             |
             v
#285 near-miss/protection atlas (Done; blanket protection rejected)
             |
             v
#286 joint base-ticket + selective-protection learning (Done; no protection Edge)
             |
             v
#291 decomposed rare-event probability/payoff heads (Done; base candidate signal)
             |
             v
#292 calibrated dynamic joint optimizer (Inbox; held for PI/user scope review)
             |
             v
#210 held-out/prospective validation  <--- no candidate; also blocked by #218
             |
             v
#211 timestamped message overlay     <--- #182 message evidence
```

| Order | Issue | Live state | Milestone | Native dependency | Accepted or intended output |
| --- | --- | --- | --- | --- | --- |
| 1 | [#203] causal issue tensor | Closed / Done | M1 | #192 closed | Versioned issue × match × outcome data contract |
| 2 | [#204] residual probability and SP heads | Closed / Done | M2 | No open blocker | `MARKET_ONLY` retained as the safe baseline; residual model remains retrospective |
| 3 | [#205] M×3 value matrix and joint N7 calibration | Closed / Done | M2 | #204 closed | `MARKET_INDEPENDENCE` plus frozen pre-event SP is the safe #206 interface |
| 4 | [#206] fixed-N7 ticket generator | Closed / Done | M3 | #205 closed | Learned challenger rejected; no comparable accepted ticket baseline is bound, so all locked issues route to `NO_BET` |
| 5 | [#207] active bankroll + separate NO_BET safety lane | Closed / Done | M3 | #206 closed | Engine valid after R7 EV and PI adversarial review; no positive active-overlay evidence; deployable policy remains false |
| 6 | [#208] dynamic N×K frontier | Closed / Cancelled | M3 | Superseded by #209 | Scientific null retained; obsolete conflicting publication-infrastructure PR closed without merge |
| 7 | [#229] divergence data profile | Closed / Done | M1 | No predecessor | Accepted negative readiness result: all causal SP-backed independent divergence intersections are zero; `BLOCKED_DATA_DEFECT` |
| 8 | [#232] divergence-support remediation | Closed / Done | M1 | Native `blockedBy #238` is closed | Dual-track data handoff accepted: complete historical proxy, prospective interface and portable snapshot path; actual historical Beijing three-way SP remains unavailable |
| 9 | [#209] full-cycle historical evaluation | Closed / Done | M3 | #232 and #229 closed | Learned state-action policy is dynamic but fails 2023 matched capital (-0.316pp vs fixed N7/K8); retain control, keep 2024 sealed |
| 10 | [#279] action-aware feature factory | Closed / Done | M3 | Parent #202; satisfied predecessor of #282/#210 | Budget-matched distributional targets, action features and complete 2023 pre-outcome cell/ticket/leg traces |
| 11 | [#282] conditional action-value policy | Closed / Done | M3 | #279 closed; native successor #210 | End-to-end Deep Sets prototype complete; cash-only learned result, no holdout handoff; retain N8 regime hypothesis for development |
| 12 | [#284] issue-normalized subset and joint-action atlas | Closed / Done | M3 | #282 closed; parent #202 | Qualified diagnostic only: subset augmentation stabilizes expected surfaces; +1.80pp is versus internal fixed K512, while Full-HGB is −5.29pp versus the live named N7/TOP/K8 control |
| 13 | [#285] near-miss and protection atlas | Closed / Done | M3 | Parent #284; blocks #286 until merge | Equal-issue adverse-divergence localization is about +4pp versus random; dense blanket protection and corrected chronological paths are worse; advance only bounded selective learning |
| 14 | [#286] joint selective-protection policy | Closed / Done | M3 | #285 closed | Label-free 620-issue joint action interface complete; learned protection ranks better than funded controls but loses to no protection and is not promoted |
| 15 | [#291] decomposed rare-event value heads | Closed / Done | M3 | Parent #202; predecessor of #292 | Separate hit probability, conditional gross and direct-P&L ranking; preserve a base Top-64 candidate signal but no protection promotion |
| 16 | [#292] calibrated dynamic joint optimizer | Open / Inbox | M3 | Native blockedBy #291 until this PR lands | Confirm the candidate across nuisance replicas, then make cash/baseline/continuation and action parameters true competing choices |
| 17 | [#210] held-out/forward validation | Open | M4 | #282/#279/#209 closed; #218 open; no promoted candidate | Do not spend holdout until a dynamic candidate beats cash and the frozen matched control pre-2024 |
| 18 | [#211] message overlay | Open | M4 | Blocked by #210 and #182 | Incremental timestamped message evidence on the frozen policy |

### #284/#285 subset and selective-protection decision

- Sampling many `N×3` subsets is useful data augmentation, but the Beijing
  issue remains the independent unit. More subsets stabilize the pre-event
  expected surface; they do not make the realized best N or exact subset
  reproducible.
- After enforcing equal aggregate issue weight in every estimator, Full-HGB
  chooses N7/TOP/K512 in 295/328 OOF issues and K256 in 33. It adds +1.80pp
  over internal fixed K512 (+0.80pp ex-largest), but the paired bootstrap
  interval crosses zero. Against the live Issue-named N7/TOP/K8 control it is
  −5.29pp. Retain only a conditional-K clue, not baseline progress.
- N8 blanket single-flip protection remains negative after four-subset,
  five-seed nuisance integration: −13.21% at K16 and −4.87% at K64 on added
  capital. Under equal issue weight, adverse signed divergence localizes the
  wrong leg at 15.16%/15.29% for K16/K64 versus 11.23%/11.13% for random. The
  positive difference is about four points, not a twofold effect.
- Protection therefore becomes a joint action parameter in #286. The tradable
  target is counterfactual incremental P&L after added stake and deduplication;
  near-miss classification is auxiliary, and no-protection remains explicit.
- Reports: [`Issue-284-Parameter-Reliability-Pilot.md`](Issue-284-Parameter-Reliability-Pilot.md)
  and [`Issue-285-Near-Miss-Protection-Atlas.md`](Issue-285-Near-Miss-Protection-Atlas.md).

### #286 joint selective-protection decision

- A physically label-free 10h manifest freezes 1,188,800 base tickets,
  12,801,489 unique single-flip candidates and 1,188,800 same-stream
  continuation tickets across 620 issues before a separate settlement process
  opens 2014–2023 outcomes. 2024+ stays sealed.
- DATA-HGB base selection produces +CNY17,186.63 in expanding-year OOF, but
  one 2019 issue contributes +CNY34,383.29; ex-largest P&L is −CNY17,196.65.
  This is a tail clue, not stable Edge.
- Learned protection ranks better than exact-budget adverse, continuation and
  random controls, but adds −CNY7,210.65 on CNY15,806 incremental stake
  (−45.62%) relative to no protection. It also chooses 100% protection on 142
  of 269 OOF issues, violating the intended sparse behavior.
- Retain `NO_PROTECTION` and the protection score as an auxiliary feature. Do
  not expand the protection grid until base-action value and tail calibration
  improve and a new policy shows positive ex-largest incremental P&L versus
  cash.
- Report: [`Issue-286-Joint-Selective-Protection.md`](Issue-286-Joint-Selective-Protection.md).

### #291 rare-event value-head decision

- Issue-normalized expanding OOF separates hit probability, conditional winning
  gross and direct P&L on the #286 physical ticket surface. Data-linear average
  precision is 3.58× the base event rate and 2.86× the protection event rate,
  but conditional-gross error remains large and decomposed protection EV fails.
- Protection remains `NO_PROMOTION`. Its positive totals reverse ex-largest or
  remain bootstrap-negative; `NO_PROTECTION` stays controlling.
- A base `DATA_LOGIT_RIDGE / DIRECT_PNL / Top-64` candidate produces
  CNY+103,270.26 on CNY34,432 stake, CNY+61,116.73 ex-largest and four positive
  OOF years. Its bootstrap lower ROI bound is still −2.37%, and it has a
  112-issue losing streak, so classification is candidate signal only.
- The candidate allocates 74.0% to N9, 54.9% to K64, 59.0% to
  divergence-weighted subsets and 92.1% to weighted-WR; profitable tickets also
  occur at N7/N8. Preserve dynamic N rather than freezing N9.
- Before #292 runs, require nuisance/seed/subset confirmation and true
  cash/no-protection/continuation/frozen-baseline competition with a
  conservative lower-bound gate. Keep #210 sealed.
- Report: [`Issue-291-Rare-Event-Value-Heads.md`](Issue-291-Rare-Event-Value-Heads.md).

### #282 conditional-policy prototype decision

- The complete `M×3 → (S,O,N,G,K,R,W) → distinct tickets → CNY100k capital`
  path runs with 432 feasible action identities, 16 common ticket streams and
  5 neural initialization seeds. The frozen-2022 replay never opens 2024+.
- The primary Deep Sets ensemble funds zero model-selected deviations in all 53
  2023 issues and ends at cash CNY100,000. Its apparent improvement over the
  current-tensor N7/K8 market control (CNY99,719.69) is pure abstention, not a
  learned betting Edge. Linear and HGB controls also fail matched promotion.
- 2018–2022 expanding-window OOF confirms underactivity: Deep funds only two
  deviations and has aggregate matched lift CNY−2,394.25. The #210 handoff gate
  therefore fails and the outcome seal remains intact.
- A post-outcome N8 weighted-sampling cluster is retained only as hypothesis.
  `CELL_VALUE/N8/K512` is +17.56% in 2023 and +2.82% over 2014–2022, but the
  development aggregate depends on 2014 and turns negative without it. Any next
  model must learn a preregistered causal regime relation rather than promote
  the scanned row.
- Decision report: [`issue_282_conditional_policy_report.md`](issue_282_conditional_policy_report.md).

### #279 action-aware target and attribution decision

- PR #280 was PI-reviewed and merged at exact HEAD
  `a8c9e516471021026ed7abefd638609c040b20c4`.  It materializes 30,368
  action-conditioned feature/target rows for 620 independent issues while
  opening zero 2024+ outcome rows.
- Every active action is rescaled to a common CNY16 reference budget.  The
  issue-level budget-matched maximum is distributed across K8/32/128/512 at
  20.3%/27.3%/30.3%/20.5%, rather than collapsing to K512.  Parameters remain
  functions of issue Data; these outcome-aware maxima are diagnostics, not
  hard policy labels.
- Returns remain rare-hit dominated.  The best all-development mean candidate,
  N5/K8 WEIGHTED_WR, has +CNY7.24 mean but -CNY16 median, only 13.1% positive
  issues, and -CNY2.92 ex-largest mean.  Successor learning must model the
  conditional distribution, downside and positive-return probability.
- The 2023 replay freezes 43,599 cells, 265 Top-B actions, 3,264 tickets and
  20,208 legs before settlement.  It exposes final-portfolio structural
  differences, but Stage 1/2 versus Stage 3 and additive causal PnL remain
  unidentified.  No strategy was promoted.

### #229 terminal data-readiness decision and #232 handoff

- Independent candidate EV and PI adversarial review accepted #229 at exact PR
  #231 HEAD `c2d43cb7f63fdb88c15fdccea8a0cad2ac327a83` as a complete
  **negative readiness** result.
- Causal support is zero for `Q_BJ × SP`, `Q_BJ × EU × SP` and
  `Q_BJ × POWER × SP`. Raw Q_BJ presence therefore cannot be promoted to a
  divergence-model input, and #209 remains fail-closed.
- #232 replaces #229 as the open native blocker for #209. It must diagnose the
  raw-to-causal support waterfall, recover only timestamp-valid common-line
  observations, close candidate evidence debt E1-E4, and report support by
  issue and chronological role.
- Any future support greater than zero is necessary but not sufficient. PI must
  review issue-level sample adequacy and supported N/action scope before #209
  may enter `Ready`.

### #236 historical European proxy decision

- PR #265 was accepted and merged at exact reviewed HEAD
  `db5b613e2976b25aeb326a4ad370c11d8b92debe`. The hash-bound Nowscore/Titan
  lane covers 192,443 of 192,709 eligible issue slots across 701 issues and
  emits 1,731,423 de-vig 3/1/0 probability rows.
- `initial`, `10h` and `1h` remain `RETROSPECTIVE_RELATIVE_PROXY`; they are not
  exact common-epoch observations, Beijing SP movement or strict-forward
  evidence. Settlement, result, payout and the 0.65 factor remain excluded.
- Normalized line 0 permits 342,020 fixture-horizon identity translations
  (59.26%). Non-zero lines remain masked pending a score/goal-difference
  distribution. #238 must retain raw line, normalized line, provenance and the
  translation mask, and must not overclaim the upstream large-code
  normalization as fully closed raw-provider truth.
- #236 is a satisfied native predecessor of #238. #238 subsequently learned
  and confirmed a separate historical non-zero-line translator while retaining
  this upstream proxy boundary.

### #268 complete historical proxy backfill decision

- PR #270 was PI-reviewed and merged at exact HEAD
  `713949ef347d4a16f2f42c929606390ec0128148`. The versioned SQLite candidate
  represents all 808 frozen issues / 213,263 fixtures and contains 9,596,835
  normalized European quote triplets.
- The #236-compatible Parquet view has valid probabilities for 212,994 fixtures
  (99.874%). All 269 unavailable fixtures remain explicit: 266 inherited from
  #236, one from the 2026 extension and two from the recovered lane.
- The accepted #236 surface is preserved exactly across all 1,731,423
  probability rows. #268 extends the baseline and does not silently rewrite it.
- SQLite is the durable normalized ingestion/QA layer; Parquet is a rebuildable
  analysis view. The complete 808-row issue disposition and 639,789-row
  fixture×horizon disposition matrices distinguish source absence from invalid
  odds without loading the full quote union into pandas.
- `initial`, `10h` and `1h` remain `RETROSPECTIVE_RELATIVE_PROXY`. #268 removes
  the historical coverage blocker but does not create strict common-decision-
  epoch evidence. #238 preserves this boundary in its modelability report.

### #238 chronological divergence-materializer decision

- PR #272 was PI-reviewed and merged at exact HEAD
  `97b7767a0ac371fed5d2b1bcca4e923b1ec8a981`. It materializes 638,792
  fixture×horizon European triplets (1,916,376 M×3 cells) across all 808
  issues; 636,632 fixture×horizon rows have a supported native-line mapping.
- The fixed EU-plus-line logistic translator beats the chronological line-only
  control on log loss, Brier and ECE at `initial`, `10h` and `1h` in both 2022
  tune and untouched 2023 confirmation. Every issue-blocked log-loss/Brier
  bootstrap interval is below zero.
- This is a positive **representation** result, not positive EV. The line-only
  control is a coarse handicap prior; actual historical pre-event
  `Q_BJ_SP_DEVIG` remains unavailable. Half-lines and sparse ±4/±5 rows are
  masked rather than extrapolated.
- All 808 issues retain N7 capacity at every horizon, but neither N=7 nor ticket
  overlap is fixed by this data result. #209 may learn from raw EU probability,
  line-only prior, translated native probability and their signed divergence as
  separate inputs.
- 2024+ contains 188 issues / 43,531 inventory fixtures and remains physically
  feature-only. Its outcomes cannot be opened until #209 freezes the learning
  loss, accepted baseline, ablations and fallback constraint.

### #249 portability and #232 terminal data handoff

- PR #275 was PI-reviewed and merged at exact HEAD
  `d454f1ae92d5a6ee46e5484c4807277e7e0bc104`. The first complete external
  snapshot contains 464 assets / 35,538,877,815 bytes and is bound by manifest
  SHA-256 `fada8656907ebe4dcb9f2b493e06699c52b095e22159bf23b9a26af4c45f3d6f`.
- Independent external read-back and a real isolated ext4 restore both passed.
  Live SQLite stays on ext4; the removable drive is versioned snapshot storage,
  addressed through `BEIJING_LOT_DATA_ROOT`.
- #232 is terminally closed under its v2 dual-track rule. #268 supplies the
  complete retrospective proxy panel, #238 supplies the accepted EU-plus-line
  representation, #248 supplies the prospective collection interface and #249
  supplies portability. None of these results fabricates historical Beijing
  three-way SP or upgrades relative-horizon proxies to strict causal evidence.
- Per the user-approved scope, #237 POWER features remain a later optional
  model input. #209 is active without waiting for POWER or for prospective
  sample accumulation.

### #209 first-cycle activation boundary

- The first historical model cycle uses `Q_EU_RAW_1X2`,
  `Q_LINE_ONLY_CONTROL`, `Q_EU_BJLINE`, signed EU-versus-line divergence and
  their horizon/availability/provenance masks as separate channels.
- The line-only prior is not observed Beijing three-way capital probability;
  historical `Q_BJ_SP_DEVIG` remains null. POWER is optional and masked.
- `initial/10h/1h` retain `RETROSPECTIVE_RELATIVE_PROXY` grade. All 2024
  outcomes stay sealed until the Gate-A loss, model budget, baselines,
  ablations, policy and fallback are frozen and PI-reviewed.

### #205 terminal decision and downstream contract

- The dependence challenger improved locked joint log loss and payout MAE, but
  it was slightly worse than model independence on chronological CV and worse
  than market on locked Brier. It is promising retrospective evidence, not a
  validated edge.
- The controlling disposition is `INHERIT_EXACT_MARKET_BASELINE`. #206 may use
  only `control_probability` (`MARKET_ONLY`, `FROZEN_SAFE_BASELINE`) with the
  frozen pre-event SP head and `MARKET_INDEPENDENCE` as its safe lane.
- All `LOGISTIC_RESIDUAL` values are explicitly `experimental_*`,
  `RETROSPECTIVE_PROXY_METHOD_CORRECTION`, `promoted=false`, and ablation-only
  until #210 confirmation. They cannot silently replace the safe control.
- Closing #205 removes the native blocker from #206, but does not itself
  authorize execution. PI/user review must place #206 into an executable
  Project state.

The baseline ladder remains mandatory: every downstream model reports both
absolute performance and matched lift against its inherited frozen control.
No improvement is accepted when it arises only from lower stake, cash
retention, fewer tickets, post-outcome parameter choice, or an ungraded
retrospective feature.

### #206 research decision and Stage-3 handoff

- Every requested identity has exactly seven distinct matches, while each
  ticket selects its own subset from the complete issue pool. The #205
  first-seven calibration roster is not reused as the action universe.
- Chronology is CV-2021 train, CV-2022 policy/K selection and CV-2023 final
  historical evaluation. LOCKED_TEST 2025/2026 labels remain embargoed; its
  output is a label-blind requested-ticket ledger only.
- The best local matched comparator was MARKET_WR at K=8, but #205 accepted a
  probability scorer rather than a comparable Stage-3 ticket policy. MARKET_WR
  is therefore diagnostic and is not inherited as a deployable frozen baseline.
- The same-K LEARNED_MLP challenger had CV-2022 point matched realized lift
  +0.875233, but its Bonferroni-adjusted one-sided lower bound was -2.403563.
  Raw independence × predicted-SP expected utility is diagnostic only. The
  controlling disposition is `LEARNED_POLICY_REJECTED_BASELINE_UNRESOLVED`.
- Every locked issue deterministically routes to `NO_BET` with zero requested
  tickets/stake until PI binds a comparable accepted ticket baseline. This is a
  Stage-3 request decision, not final bankroll or position-sizing authority.
- The exploratory LOGISTIC_BASELINE/K16 row returned +67.88% realized pre-tax
  net on CV-2023 after -68.70% on CV-2022. It uses K16 turnover rather than the
  selected K8 matched budget and is consistent with one sparse payout, so it is
  a non-promotable follow-up clue rather than stable edge evidence.
- The negative result is scoped to the bounded 55,042-candidate generator and
  current feature/calibration contract; it does not reject ticket-subset learning
  generally. Closing #206 clears its native blocker, but #207 is not activated
  until PI adjusts its contract so the zero-request handoff does not collapse
  Stage 4 into a cash-only tautology or silently promote the local comparator.
- Evidence: [`issue_206_fixed_n7_ticket_policy.md`](issue_206_fixed_n7_ticket_policy.md).

### #207 active Stage-4 bankroll decision

- Lane A reconstructs 68,880 exact #206 research-only requests for the frozen
  five-policy K8 controlling panel plus K16/K32 sensitivities. Lane B retains
  #206 NO_BET and cash separately as `LOWER_EXPOSURE_ONLY`.
- CV-2021 fits the simple logistic controller before the bounded neural
  ablation; CV-2022 freezes risk fractions and selects `BOUNDED_NEURAL`;
  CV-2023 is the sole terminal historical evaluation for that frozen learned
  choice. LOCKED_TEST labels remain embargoed.
- The strongest absolute K8 path is MARKET_WOR/native ¥2: ending capital
  ¥99,312.89, still a loss.
- The strict split-local matched-active rule has no qualifying K8 row, so
  `ACTIVE_OVERLAY_EVIDENCE=false`. The previously reported positive
  MARKET_WOR/K8 simple-controller same-window result is retained only as a
  historical sensitivity and is non-evidentiary.
- `ENGINE_VALID=true` only after publication state, reason traces, required
  rolling aggregates, schema semantics and all conclusion surfaces verify;
  `DEPLOYABLE_POLICY=false`. The negative freeze is `NATIVE_2_YUAN`; cash does
  not answer the active question. After R7 EV and PI terminal review, #207 was
  closed and #208 was explicitly activated as the dynamic N×K research step.
- Evidence: [`issue_207_fixed_n7_bankroll.md`](issue_207_fixed_n7_bankroll.md).

[#182]: https://github.com/algotradinglife/beijing-lot/issues/182
[#192]: https://github.com/algotradinglife/beijing-lot/issues/192
[#202]: https://github.com/algotradinglife/beijing-lot/issues/202
[#203]: https://github.com/algotradinglife/beijing-lot/issues/203
[#204]: https://github.com/algotradinglife/beijing-lot/issues/204
[#205]: https://github.com/algotradinglife/beijing-lot/issues/205
[#206]: https://github.com/algotradinglife/beijing-lot/issues/206
[#207]: https://github.com/algotradinglife/beijing-lot/issues/207
[#208]: https://github.com/algotradinglife/beijing-lot/issues/208
[#209]: https://github.com/algotradinglife/beijing-lot/issues/209
[#279]: https://github.com/algotradinglife/beijing-lot/issues/279
[#210]: https://github.com/algotradinglife/beijing-lot/issues/210
[#211]: https://github.com/algotradinglife/beijing-lot/issues/211
[#218]: https://github.com/algotradinglife/beijing-lot/issues/218
[#229]: https://github.com/algotradinglife/beijing-lot/issues/229
[#232]: https://github.com/algotradinglife/beijing-lot/issues/232
[#234]: https://github.com/algotradinglife/beijing-lot/issues/234
[#235]: https://github.com/algotradinglife/beijing-lot/issues/235
[#236]: https://github.com/algotradinglife/beijing-lot/issues/236
[#237]: https://github.com/algotradinglife/beijing-lot/issues/237
[#238]: https://github.com/algotradinglife/beijing-lot/issues/238
[#248]: https://github.com/algotradinglife/beijing-lot/issues/248
[#249]: https://github.com/algotradinglife/beijing-lot/issues/249
[#286]: https://github.com/algotradinglife/beijing-lot/issues/286
[#291]: https://github.com/algotradinglife/beijing-lot/issues/291
[#292]: https://github.com/algotradinglife/beijing-lot/issues/292

---

## Historical Phase 0–5 record

# Phase 0: Research Infrastructure (Completed)

## Data Foundation

- Beijing-lot live database
- SP snapshots
- settlement data
- as-of information boundary

## Strategy Archaeology

- Historical strategy audit
- Evidence classification
- Failed direction archive

## Freeze System

Completed:

- Freeze Protocol v1
- Freeze Automation v1
- Forward Dataset Pipeline

Purpose:

Create reproducible and auditable forward research samples.

---

# Phase 1: Market Information Research

Research question:

> How much information is contained in Beijing-lot market prices?

## SP-EFF-001 (Completed)

Question:

Does SP contain calibrated probability information?

Conclusion:

SP contains directional probability information. This does not prove exploitable betting advantage.

## Multi-Market Data Audit

Goal:

Determine research readiness of different markets:

- Handicap 3/1/0
- Correct Score
- Total Goals
- Half/Full Time

Check:

- data availability;
- pre-event snapshot;
- freeze support;
- settlement support.

## SP-CONSISTENCY-001

Study whether different markets represent a consistent probability space.

Example:

Correct Score distribution → win/draw/loss probability → compare with handicap market.

## SP-MOVEMENT-001

Study whether SP movement contains incremental information.

---

# Phase 2: Decision Chain Research

Research question:

> Can structured football reasoning improve decisions beyond market information?

Decision Chain is not a pure prediction model. It converts information into a structured decision process.

Inputs:

- market information;
- match context;
- risk assessment.

Outputs:

- primary decision;
- confidence;
- reasoning chain;
- protection requirements.

## Decision Chain Framework

Versions:

- v3.3.3
- v4.2

Research goal:

Compare:

SP only

vs

SP + Decision Chain

---

# Phase 3: Portfolio Construction Research

Research question:

> Given a decision, how should selections be combined into N-leg structures?

Focus:

- N-leg construction;
- protection legs;
- risk management;
- stake allocation.

Protection legs are studied as failure-risk reduction mechanisms, not as independent predictions.

Metrics:

- failure rate;
- survival rate;
- drawdown;
- risk-adjusted performance.

---

# Phase 4: Forward Validation

Use Freeze Automation to accumulate:

- 100 issues;
- 500 issues;
- 1000 issues.

Validate:

- market findings;
- decision chains;
- portfolio methods.

---

# Phase 5: Advanced Modeling

Potential directions:

- football probability models;
- Bayesian models;
- multi-market fusion;
- advanced portfolio optimization.

---

# Research Principles

1. Observation is not a law.
2. Backtest is not forward validation.
3. Single-period profit is not evidence.
4. All experiments require freeze, registry and review.
5. Probability information, decision quality and portfolio construction must be evaluated separately.
