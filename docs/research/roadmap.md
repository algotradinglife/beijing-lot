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

Updated: **2026-08-25 (#378 N6/N7 portfolio closed; #388 cutoff hardening ready to land; #383 next)**

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
#292 calibrated dynamic joint optimizer (Done; development OOF complete,
     low-N core fails and high-N tail is one-jackpot dependent; no promotion)
             |
             v
#296 candidate-warm expert mixture (Done; raw 2023 positive but unstable,
     validation fallback retains frozen static control; no promotion)
             |
             v
#299 exact BEST_FULL + learned residual (Done; +11.65pp matched 2023
     lift, but still negative and below exposure-matched random median)
             |
             v
#302 hierarchical keep/skip + dynamic expert mixture (Done; 2023
     keep/skip +2.63%, but causal expert funding scale is 0%; no promotion)
             |
             v
#305 dedicated keep/skip correction (Done; 2023 -7.11% vs FULL -20.75%,
     but exact same-exposure placement percentile 42.71%; no selection Edge)
             |
             v
#306 matched-exposure within-issue ticket composition (Done; interface retained,
     post-merge exact-support correction withdraws positive action-value claim)
             |
             v
#312 explicit selector/outcome/protection action cube (Done; NO_INCREMENT;
     hard action-MLP argmax loses to exact-support fixed N7/WOR)
             |
             v
#314 CORE/TAIL soft-MoE + explicit depth-1/2 coverage + dynamic exposure
     (Done; NO_LEARNABLE_INCREMENT)
             |
             v
#318 historical Beijing-SP/proxy admissibility audit
     (Done; NO_CAUSAL_PRICE_SUPPORT)
             |
             v
#319 probability-only Top-2 N7 stable center
     (Done; chronology/recovery correction merged, terminal
     PRICE_DATA_INSUFFICIENT and capital totals unchanged)
             |
             v
#324 full 2x2x2 selector × outcome-support × allocator ablation
     (Done; NO_INCREMENT, joint point signal is largest-issue-dependent)
             |
             v
#328 learned S1O1 allocator mixture
     (Done; ENDPOINT_RETAINED, memoryless dynamic lambda collapses to A0)
             |
             v
#330 causal lagged regime state ledger
     (Done; SPARSE_RESPONSE_REDESIGN, fast regime gate not established)
             |
             v
#332 fixed-expert causal multitask MoE
     (Done; NO_EXPERT_MIX_SIGNAL, accepted Top-2 baseline retained)
             |
             v
#334 neural Top-2 residual action-value learner
     (Done; neural arm rejected, value-anchor support signal retained for replication)
             |
             v
#336 QEU support-depth attribution
     (Done; R3 transfers positively but is classified QEU_TAIL_ONLY because
     2023 development lift is almost entirely one issue; freeze for forward test)
             |
             v
#338 QEU raw/z threshold activation on fixed N7
     (Done; every absolute threshold loses in 2023; R3 remains the relative rule)
             |
             v
#340 QEU within-issue dynamic support depth R
     (Done; prequential RF learns mostly R0/R1, improves R0 but loses to R3;
     fixed R3 remains the historical challenger)
             |
             v
#342 conservative pre-event value veto × fixed R3
     (Done; 0/833 incumbent legs satisfy strict interval dominance;
     point-value clues remain descriptive, fixed R3 unchanged)
             |
             v
#345 paired candidate-incumbent value selection × fixed R3
     (Done; fair paired uncertainty produces actions but every selector loses
     to S0R3 on the primary matched capital comparison; fixed R3 unchanged)
             |
             v
#348 native multi-N probability Top-2 R0 baselines
     (Done; fixed CNY1,024 and exact ticket designs across N3–N10)
             |
             v
#349 development-frozen support depth R_N
     (Done; no new non-N7 fixed-R increment transfers)
             |
             v
#352 N3–N6 × full-R annual retrospective diagnostic
     (Done; exposed N6 payoff signal is year-dependent; no R reselection)
             |
             v
#354 strictly-prior low-N selector panel
     (Done; 134,822 causal rows, transfer calibration frozen through 2021)
             |
             v
#355 low-N fixed-Top2 coverage selector
     (Done; logistic selection changes matches but does not improve both OOF
     calibration scores; N4 financial clue is bootstrap-uncertain; no promotion)
       |                         |
       v                         v
#358 causal 10h European      #359 coverage × value selector
average-odds proxy (Done)     (Done; historical signal, no deployment claim)
       \_________________________/
                    |
                    v
#356 selective third-outcome protection
     (Done; added coverage raises hit rate but loses matched capital)
             |
             v
#210 held-out/prospective validation  <--- still blocked by open #218
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
| 16 | [#292] calibrated dynamic joint optimizer | Closed / Done | M3 | #291 closed; no open blocker | Full N3–N10/K8–512 development OOF complete: dynamic and low-N core lose to cash; tail/barbell are one-jackpot dependent; retain architecture, no promotion |
| 17 | [#296] candidate-warm expert mixture | Closed / Done | M3 | #292 closed; blocks #210 | Learned expert/cash weights are meaningful, but 2022 validation fails, warm start trails both initialization controls, and all seeds are negative ex-largest; safety gate falls back to static control |
| 18 | [#299] BEST_FULL-anchored residual optimizer | Closed / Done | M3 | #296 closed; blocks #210 | Exact matched residual learning improves 2023 BEST_FULL from -20.75% to -9.10%, but remains below cash and only the 38.3rd percentile of exposure-matched random placement; retain architecture, no promotion |
| 19 | [#302] hierarchical dynamic expert mixture | Closed / Done | M3 | #299 closed; blocks #210 | Expanding keep/skip ends 2023 +2.63% versus exact BEST_FULL -20.75%; expert funding adds zero under the causal OOF gate and placement misses falsification, so retain only development evidence |
| 20 | [#305] dedicated keep/skip correction | Closed / Done | M3 | #302 closed; blocks #306 | Independent keep/skip ends 2023 at -7.11%, but its eight funded issues rank only 42.71% among 23,535,820 exact same-exposure placements and change materially with alpha; classify as exposure reduction, not issue-selection Edge |
| 21 | [#306] matched-exposure within-issue ticket composition | Closed / Done | M3 | #305 closed; predecessor of #312 | Interface and matched-exposure mechanics retained. Post-merge EV found broader-support drift; on inherited exact-B0 support the selected family changes and positive `ACTION_VALUE_SIGNAL` does not reproduce |
| 22 | [#312] explicit joint action cube | Closed / Done | M3 | #306 closed; blocks #314 | Exact-support 2023 JOINT_PRIMARY CNY70,795.72 versus fixed N7/K512/WOR CNY87,984.27; hard action-conditioned MLP/argmax is rejected, while protection remains a weak parameter clue. Label-safe five-year replay changed no result |
| 23 | [#314] CORE/TAIL soft-MoE, coverage and exposure | Closed / Done | M3 | #312 closed; blocks #210 | Full MoE rejected: 2023 validation loses 31/31 seeds and 2024 raw ends CNY34,373.99 versus portable fixed CNY81,882.32. Protection beats no-protection (+CNY1,048.49) but loses to matched random placement (−CNY594.31); `NO_LEARNABLE_INCREMENT`, no promotion |
| 24 | [#318] historical Beijing-SP/proxy audit | Closed / Done | M1 | No open blocker; predecessor of #319 | All six frozen sources consumed. Historical SP is timestamp-unproven; strict/proxy overlap is only one 2026 issue and fails every fidelity threshold. `NO_CAUSAL_PRICE_SUPPORT`; #319 must be probability-only |
| 25 | [#319] probability-only Top-2 N7 stable center | Closed / Done | M3 | #318 closed | Exact 128-ticket/CNY256 center executed. Primary 10h ends 2023 CNY93,901.88 (capital return -6.10%) and 2024 CNY103,567.30 (+3.57%). Post-merge correction orders paths by event timestamp and separates completed recovery from the open underwater tail; capital totals and `PRICE_DATA_INSUFFICIENT` are unchanged |
| 26 | [#324] Top-2 selector × support × allocator factorial | Closed / Done | M3 | Parent #202; predecessor of #328; blocks #210 | Post-merge EV corrected the calendar-year settlement join: primary common support is 45/54, and corrected two-year matched lifts are CNY+16,800 for `S1O1A0` and CNY+24,642 for `S1O1A1`. Routing remains `NO_INCREMENT`; old 2023 denominator and metrics are quarantined |
| 27 | [#328] learned S1O1 allocator mixture | Closed / Done | M3 | Parent #202; predecessor of #210 | Corrected endpoint parity passes. Static lambda lift rises toward A1, but Ridge/HGBR issue-only lambdas collapse near zero and reproduce A0. The OOF allocator response has only one positive-delta issue in each of 2021/2022; retain A0/A1 as fixed experts and add lagged regime state before another MoE. `ENDPOINT_RETAINED`; no promotion |
| 28 | [#330] causal lagged regime state ledger | Closed / Done | M2 | Parent #202; predecessor of #332; blocks #210 | 282 issue-level rows establish stable European calibration and a very sparse A1-A0 response. Post-merge EV quarantines its current settlement-availability feature and anchor-surrogate lag timestamps; #332 rebuilds only the usable targets behind a conservative latest-kickoff+4h availability gate. Retain `SPARSE_RESPONSE_REDESIGN`, not the original causal feature artifact |
| 29 | [#332] fixed-expert causal multitask MoE | Closed / Done | M3 | Parent #202; predecessor of the next direct-value learner; blocks #210 | Eight frozen N7-N10 experts, 512 matched tickets and 11 nuisance seeds. Dense hit/near-miss labels are moderately learnable, but lagged/current/static mixtures all fail the strongest fixed and accepted Top-2 controls. Against accepted Top-2, lagged MoE is +CNY1,364 raw but −CNY3,007 ex-largest in 2023, then −CNY48,666 in 2024. `NO_EXPERT_MIX_SIGNAL`; retain Top-2 and learn residual match/outcome/ticket value directly |
| 30 | [#334] neural Top-2 residual action-value learner | Closed / Done | M3 | Parent #202; blocks #210 | The 2023-selected neural match selector is +CNY7,941 raw / +CNY2,579 ex-largest, but reverses to −CNY35,278 / −CNY31,787 on frozen 2024 and is rejected. The interpretable `q_eu/q_line` value anchor produces a distinct long-tail clue: support-only lift is +CNY50,723 in 2023 and +CNY49,393 in 2024; 2024 ex-largest remains +CNY23,919, while 2023 ex-largest is −CNY1,158. Retain as `ANCHOR_SHRINKAGE_SIGNAL_NOT_YET_PROMOTED`, with exact #319 Top-2 as fallback |
| 31 | [#336] QEU support-depth attribution | Closed / Done | M3 | Parent #202; closed predecessor of #338/#210 | On 105 exact-common settled issues, 2023 selects R3. Matched lift is CNY+61,344 in 2023 and +66,812 in 2024; 2024 ex-largest remains +29,498 with 88.55% positive issue-bootstrap draws. But 2023 ex-largest is only +406 (0.66% of raw lift), so classify `QEU_TAIL_ONLY`. Post-merge audit found a formula/domain implementation error; #338 independently recomputes the written `1e-4` rule and shows no action difference on the current 2023/2024 panel |
| 32 | [#338] QEU threshold activation on fixed N7 | Closed / Done | M3 | Parent #202; native predecessor #336; not a #210 blocker | All fourteen raw/z/dual candidates lose to R0 in 2023. The selected failed candidate `RAW_Q80` is CNY−12,899 vs R0 in 2023 and −24,916 in 2024. R3 remains materially stronger because it is issue-relative; no threshold replaces or unblocks #210 |
| 33 | [#340] within-issue dynamic QEU R | Closed / Done | M3 | Parent #202; native predecessor #338; not a #210 blocker | Eleven strictly-prior RF seeds learn a per-issue R from ranks/gaps/dispersion. The full policy is +CNY45,950/+27,788 vs R0, but 2023 learned decisions alone are CNY−2,080 vs R0 and the apparent gain comes from R3 cold start. It loses to fixed R3 by CNY−15,395/−39,024; ex-largest is also negative. `FIXED_R3_REMAINS_BEST` |
| 34 | [#342] conservative value veto × fixed R3 | Closed / Done | M3 | Parent #202; native predecessor #340; not a #210 blocker | Exact #338 R0/R3 parity on 105 issues. 2023/2024 contain 342/371 and 420/462 point-positive leg challengers, but 0/833 pass the deliberately over-conservative paired-tail screen; `NO_INCREMENT`, fixed R3 unchanged |
| 35 | [#345] paired value selection × fixed R3 | Closed / Done | M3 | Parent #202; no open blockers; not a #210 blocker | Same-issue 2022 paired SP-value errors replace #342's unfair marginal-tail comparison. All six predeclared selectors act, but none beats S0R3 in both years on raw and ex-largest lift. On 96 exact-all-cell common issues S0R3 ends at CNY232,211 with 17.46% max drawdown and 19 consecutive losing issues; `PAIR_L10R3` ends at CNY193,741 with 28.94% drawdown and 18 losses. `NO_INCREMENT`; preserve R3 and carry paired value only as a diagnostic/risk feature into the planned N3–N10 baseline scan |
| 36 | [#348] native multi-N probability Top-2 R0 baselines | Closed / Done | M3 | Parent #202; native predecessor of #349; not a #210 blocker | Fixed CNY1,024/issue and ticket-level-once 0.65 establish N3–N10 centers. N3 is the smoothest (62.62% hit, −10.11% capital, 20.48% drawdown, 5-loss run); N7 is near break-even (+0.74%, 25.96% drawdown, 12-loss run). N9's +5.23% is dominated by one payout (52.08% share) and a 44-loss run; N10 collapses. These are risk baselines, not a raw-capital cross-N ranking |
| 37 | [#349] development-frozen multi-N support depth | Closed / Done | M3 | Parent #202; blockedBy closed #348; not a #210 blocker | Complete 2022 R=0..N curves freeze R0 for N3–N6/N8/N10, accepted R3 for N7, and R1 for N9. N9's development +CNY14,729 raw/armwise-ex-largest reverses to −69,409 in 2023 and −7,281 in 2024. Only the already accepted N7 R3 is positive in both exposed years; no new non-N7 fixed-R increment. Phase A exact parity and #338 R3 parity both pass |
| 38 | [#352] N3–N6 full-R annual diagnostic | Closed / Done | M3 | Parent #202; no dependency or routing changes | Complete 88-row N×R×period matrix preserves #349 construction and receipt. Every nonzero R reduces realized leg inclusion versus probability Top-2, but N6/R3 raises exposed capital by CNY27,265 in 2023 and CNY37,462 in 2024 while lowering hit rate, showing a payoff/tail rather than accuracy signal. Its 2022 lift is CNY−16,015. The inherited candidate gate was confirmed with 2023 labels, so all rows are conditional retrospective evidence, not chronology-clean; no pooled reselection and #349/#210/#218 remain unchanged |
| 39 | [#354] strictly-prior low-N selector data | Closed / Done; chronology superseded | M1 | Parent #202; historical handoff to #355 | Post-merge EV found that latest-kickoff year routing shifted 62 issues and admitted future labels. Probability arithmetic remains descriptive, but the original annual/causal handoff is superseded by #360 |
| 40 | [#360] low-N chronology and outcome-grain correction | Closed / Done | M1 | Parent #202; corrective blocker for #355/#358 | Registry-year routing, explicit 10h decision and conservative label-availability timestamps, issue-unit coverage and exact M×3 cells close all three #354 known errors. The corrected 132,408-fixture panel is the only authorized #355 input |
| 41 | [#355] fixed-Top2 low-N match selector | Closed / Done | M3 | Parent #202; #354/#360 closed; blocks #359/#356 | Corrected replay keeps S2 only by tiny OOF calibration gains. On 151 matched N4 issues its all-transfer lift is CNY+2,308, but annual lift reverses to CNY−7,683 in 2024, bootstrap p05 is negative, and matched drawdown/loss run worsens from 27.35%/8 to 27.69%/13. N3/N5 lifts are negative. `NO_PROMOTION`; preserve S0 and carry only the weak value clue into #358/#359 |
| 42 | [#358] causal 10h European-average-odds value proxy | Closed / Done | M1 | Parent #202; #360 closed; predecessor of #359 | Corrected `EUROPEAN_AVERAGE_ODDS_PROXY` uses `sum_Top2(p×odds)/2` per-stake leg contribution and applies 0.65 once to the complete N-fold proxy. All 397,224 M×3 cells carry source/quality receipts; it is not official Beijing SP or an exact payout claim |
| 43 | [#359] low-N coverage × European-value frontier | Closed / Done | M3 | Parent #202; #355/#358 closed; blocks #356 | Exact S0 and #355 diagnostic parity. N3 value-only lifts matched 2022–2024 PnL by CNY4,792; N4 coverage+value lifts by CNY6,663 and remains +CNY8,086 ex-largest. Both bootstrap p05 values cross zero and absolute capital remains below CNY100k. `HISTORICAL_SIGNAL`, not deployable Edge; gap-only has no repeatable increment |
| 44 | [#356] selective third-outcome protection | Closed / Done | M3 | Parent #202; #355/#359 closed | Development-frozen additive P fails transfer: every primary S0 P>0 arm loses matched 2022–2024 capital; recovered miss payouts are smaller than incumbent-hit dilution. `NO_INCREMENT`; retain P0 |
| 45 | [#366] corrected N7 chronology synchronization | Closed / Done | M3 | Parent #202; #360 closed; blocks #367/#369 | Rebuilt fixed R0/R3 from corrected registry-year and fixture-relative 10h inputs. R3 ends at CNY132,689 versus R0 CNY84,006 on 151 settled issues, but its CNY48,683 lift becomes CNY−12,255 ex-largest and bootstrap p02.5 is CNY−67,786. Twenty-two of 208 common legacy issue-arm PnLs change. Corrected R3 is the canonical historical long-tail challenger, not a stable promotion |
| 46 | [#367] corrected N4 versus N7 expert diagnostic | Open / Blocked | M3 | Parent #202; blocked by #366 and closed #359 | Recompute complementarity only from corrected-N7 evidence. The legacy-anchor temporary correlation is non-canonical and cannot authorize MoE membership |
| 47 | [#369] corrected N7 support-shape factorial | Closed / Done | M3 | Parent #202; #366 closed | Eight-cell replay preserves CNY1,024 and exact #366 CONTROL parity. R3 BOTH ends at CNY170,886 versus CONTROL CNY132,689; its actual lift is CNY38,197 and ideal-fractional lift CNY24,644. The interaction is positive but borderline: actual-unit bootstrap p05 CNY6,576 versus ideal-fractional p05 only about CNY141 (effectively zero at Monte Carlo resolution). BOTH lift bootstrap p05 is CNY−115,247, so no new arm passes standalone-positive robustness admission. This is a useful historical synergy mechanism, not a new expert or #210 promotion |
| 48 | [#373] corrected N7 R3 support-transfer count grid | Closed / Done | M3 | Parent #202; #369 closed; not a #210 blocker | Full C0–C2 × E0–E3 retrospective mechanism map under complete Cartesian coverage and fixed CNY1,024. C1E3 ends at CNY132,798 versus CONTROL CNY132,689, while reducing observed max drawdown from 33.17% to 21.90% and longest profitable-issue losing run from 19 to 7. Its matched-lift moving-block p05 remains CNY−135,691, so no cell enters the expert pool; C1E2/C1E3 remain future-freeze mechanism hypotheses only |
| 49 | [#376] corrected N6 chronology synchronization | Closed / Done | M3 | Parent #202; #360 closed; blocks #377 | Rebuilt N6 R0/R3 from the corrected registry-year and fixture-relative 10h source instead of reusing #352. On 152 settled issues R3 improves R0 by CNY21,211, but remains standalone-negative at CNY−12,300; ex-largest lift is CNY−3,473 and bootstrap p02.5 is CNY−45,895. Twenty-seven of 304 common legacy issue-arm PnLs change. This is the canonical N6 interface, not an admitted expert |
| 50 | [#377] corrected N6 R3 support-transfer count grid | Closed / Done | M3 | Parent #202; #376 closed | No arm passes standalone-positive robustness admission; retained only as exposed mechanism evidence |
| 51 | [#382] shared cutoff-driven historical learning | Closed / Done | M2 | Parent #202; #354 closed; blocks #381/#383 | Generic cutoff/availability/partition/weight/ESS/cache/receipt/walk-forward library landed; mapping and non-mapping clients; static governance and adversarial evidence |
| 52 | [#381] corrected N6 complete R0–R6 surface | Closed / Done | M3 | Parent #202; blockedBy closed #382/#376; blocks #378 | Rebuilt through shared cutoff client with 48,658-cell exact parity. All R0–R6 are standalone-negative; best point estimate R1 is CNY−5,447, fixed R3 remains CNY−12,300, and no R is admitted or replaces R3 |
| 53 | [#378] corrected N6 versus N7 portfolio diagnostic | Open / PI Review | M3 | Parent #202; blockedBy closed #381/#373/#377 | Complete #381 surface confirms no positive N6 expert. N6 R3 and N7 CONTROL are strongly synchronized (Pearson 0.754; both lose 76.2%); 50/50 PnL CNY10,195 is pure dilution versus N7-only stake reduction, so no N6 arm enters the expert pool |
| 54 | [#388] shared cutoff-learning hardening | Closed / Done | M2 | Parent #202; blockedBy closed #382; blocks #383 | Shared API now excludes exact target identity, binds transitive imports, enforces exact AST occurrences in `src/`/`scripts/`, separates diagnostic proxies from prospective availability, and implements a true convex recent-state blend; #382 mapping parity remains exact across 48,658 rows |
| 55 | [#383] issue-level walk-forward recency diagnostic | Open / Blocked | M2 | Parent #202; blockedBy #388 and closed #382 | Compare equal expansion, exponential recency and bounded recent-state blend through the hardened shared API before prospective adaptive reuse |
| 56 | [#210] held-out/forward validation | Open / Blocked | M4 | #218 remains the only open blocker | Preserve #319 probability Top-2 R0 as incumbent and bind QEU support-depth R3 as the sole historical challenger. Do not spend prospective Cohort-B evidence until #218 supplies genuine support |
| 57 | [#211] message overlay | Open | M4 | Blocked by #210 and #182 | Incremental timestamped message evidence on the frozen policy |

### #336 QEU support-depth attribution decision

- The experiment isolates outcome-support depth: every arm uses the exact same
  #319-selected seven matches, 128 distinct tickets, 512 CNY2 units and
  CNY1,024 per issue. Only the top-R matches by label-free QEU support pressure
  switch from probability Top-2 to `log(q_eu/q_line)` Top-2.
- The curve has a real interior sweet spot. R1/R2 do not improve reliably; R3
  reaches matched lift CNY+61,344 in 2023 and CNY+66,812 in 2024. Expanding to
  R4/R7 remains positive but adds no further lift. This supports the user's
  view that divergence belongs in the shared feature layer and should alter
  selected support depth rather than replace every outcome decision.
- The adversarial qualification is important: one 2023 issue contributes
  CNY60,938 of R3's CNY61,344 lift, leaving only CNY406 ex-largest. In 2024 the
  evidence is broader: ex-largest lift is CNY29,498 and 88.55% of 2,000
  issue-cluster bootstrap draws are positive. Historical evidence therefore
  identifies a plausible R3 challenger but does not establish a stable Edge.
- #190 Z100/K1 and QEU are the same broad divergence hypothesis but not the
  same policy. They use different match denominators and actions; the overlap
  diagnostic must not be presented as an independent replication.
- Forward disposition: keep R0 as incumbent, freeze R3 without further tuning,
  and compare them in #210 only after #218's genuine prospective support is
  available. Report: [`Issue-QEU-Support-Depth.md`](Issue-QEU-Support-Depth.md).

The asynchronous post-merge audit found that the #336 implementation clipped
both probability sources at `1e-9` instead of clipping only `q_line` at the
written `1e-4`, omitted strict positive-domain checks and used the wrong exact-
pressure tie source. #338 corrects all three before settlement and commits the
outcome-cell probability primitives. On the actual 32,765 complete 2023/2024
match actions, the corrected and legacy supports/pressures are identical, so
the current 105-issue R3 totals do not change. The audit's 105/119 complete-case
warning remains material and prevents candidate promotion.

### #338 fixed-N7 QEU threshold decision

- N, matches, support width, tickets and funding remain frozen: exact #319 N7,
  128 distinct tickets and CNY1,024 per issue. Only QEU activation changes.
- A 29,974-action 2020–2022 causal reference freezes raw pressure quantiles and
  robust `(lost outcome, gained outcome)` z scores. Six raw, five z and three
  dual thresholds are selected on 2023 only and read through on 2024.
- Every absolute threshold candidate loses to R0 in 2023. The lexicographic
  best-of-failed candidate, `RAW_Q80` (`pressure >= 0.22307`), is CNY−12,899
  versus R0 in 2023 and CNY−24,916 in 2024; its ex-largest lifts are also
  negative and only 8.85% of transfer bootstrap draws are positive.
- Some 2024-only rows look positive (`RAW_Q90` raw lift +CNY13,587 and
  `Z_GE_1P5` +CNY4,134), but both are negative after removing their largest
  issue. They cannot overturn the frozen development failure.
- The mechanism is informative. The decisive 2023 R3 issue required three
  issue-relative actions with pressures 0.1766, 0.1225 and 0.1131. A global
  Q50 cutoff (0.1307) kept only one; stricter thresholds kept none. Thus the
  evidence supports **relative within-issue divergence rank**, not a universal
  raw/z magnitude threshold.
- Verdict: `FIXED_R3_REMAINS_BEST`. Keep N7 and R3 as historical forward-test
  identities; do not add #338 as a #210 dependency and do not reopen N.
  Report: [`Issue-QEU-Threshold-N7.md`](Issue-QEU-Threshold-N7.md).

### #340 causal within-issue dynamic-R decision

- The experiment retains exact #319 N7 matches, probability Top-2 support,
  128 distinct tickets and CNY1,024 exposure. It completes the fixed R0–R7
  curve and learns only the number of issue-relative QEU support swaps.
- Eleven shallow random forests use ranks, within-issue percentiles, adjacent
  gaps, cutoff cliffs, dispersion, prefix pressure and strictly-prior expanding
  z context. The first 16 issues use an explicit R3 cold start; all 89 later
  predictions are fitted only on earlier settled issues. Eight R
  counterfactual rows retain total issue weight one.
- The full ensemble policy appears to beat R0 by CNY45,950 in 2023, but the
  first 16 R3 cold-start issues supply CNY48,030; learned 2023 decisions are
  actually CNY2,080 below R0. The all-learned 2024 path is CNY27,788 above R0.
  It loses to R3 by CNY15,395 and CNY39,024 respectively. Ex-largest lift versus
  R3 is also negative (CNY−6,249/−4,373), with bootstrap positivity only
  8.2%/18.1%. None of the 11 seeds has positive raw lift versus R3 in either
  year.
- The learner mostly selects R0/R1 after cold start; the simple prior mean-by-R
  control selects R3 and reproduces R3 exactly. This is evidence that the
  current issue-shape features do not add reliable timing information beyond
  the unconditional interior R3 sweet spot. Lower learned R improves 2024
  drawdown and losing-run risk, but gives up too much capital.
- `FIXED_R3_REMAINS_BEST`. Dynamic-R architecture remains a useful interface,
  but there is no historical candidate to rebind or unlock #210. Report:
  [`Issue-QEU-Dynamic-R-N7.md`](Issue-QEU-Dynamic-R-N7.md).

### #342 conservative value-veto × fixed-R3 decision

- The four-cell design reproduces the exact corrected #338 R0 and R3 actions,
  supports and gross settlement on all 105 issues. N7, 128 distinct tickets,
  CNY1,024 exposure and A0 equal allocation remain fixed.
- Hyperparameters use 2014–2020/2021 selection, SP models fit through 2021 and
  use 2022 only for out-of-fit residual calibration. A match may replace a #319-selected leg only if its expected-leg
  lower bound exceeds the incumbent upper bound and Top-2 retained mass falls
  by no more than five percentage points.
- Point estimates contain many value clues: 342/371 incumbent legs in 2023 and
  420/462 in 2024 have an admissible higher-point-value challenger. But none of
  the 833 legs has positive robust margin; the closest is still −0.1551. The
  hard veto therefore makes zero replacements and all SV cells equal S0.
- Verdict: `NO_INCREMENT`. This rejects the current worst-candidate-versus-best-
  incumbent marginal screen, not relative value ranking itself. The screen
  ignores within-issue paired error correlation and is too conservative for a
  fair value comparison. Keep fixed R3 and do not change #210/#218. The next
  causal experiment should model the paired `candidate - incumbent` difference,
  or use its probability as a relative/soft value weight. Report:
  [`Issue-342-Value-Veto-R3-N7.md`](Issue-342-Value-Veto-R3-N7.md).

### #345 paired-value selection × fixed-R3 decision

- The experiment implements the fair follow-up requested after #342: 2022
  supplies an issue-balanced distribution of same-issue candidate-minus-
  incumbent log-value error. Six frozen selectors (`POINT`, P50–P80 and
  `PAIR_L10`) first replace matches one-for-one, then corrected R3 is recomputed
  only inside the final seven matches.
- The accepted #338 R0/R3 actions and gross settlement reproduce exactly on
  the 96-issue all-cell common denominator. The original 105-issue baseline is
  reported separately, so denominator shrink is not mislabeled as improvement.
- No value selector advances the matched capital frontier. `S0R3` ends at
  CNY232,211 with 17.46% maximum drawdown and 19 consecutive losing issues.
  The closest stack, `PAIR_L10R3`, ends at CNY193,741 with 28.94% drawdown and
  18 consecutive losses. It is CNY−38,471 raw versus S0R3. The legacy
  largest-absolute-paired-delta sensitivity is CNY+22,468, while literal
  armwise ex-largest-payout lift is CNY−72,820; neither supports promotion.
- `P70R3` lowers maximum drawdown to 13.54% and the longest losing run to 13,
  but terminal capital falls to CNY113,324. No selector dominates S0R3 jointly
  on capital, drawdown and losing runs.
- R3 itself remains material: it adds CNY140,550 over S0R0 on the matched
  denominator and its issue-bootstrap p05 is positive. Even inside `PAIR_L10`,
  R3 adds CNY112,227. This confirms that value selection and outcome support
  are interacting layers, not additive improvements.
- Verdict: `NO_INCREMENT`. Freeze R3, do not change #210/#218, and do not tune
  a replacement cap after outcomes. The next near-term historical cycle should
  compare N3–N10, each against its own probability Top-2/R3 baseline, before
  constructing a multi-N MoE. Report:
  [`Issue-Paired-Value-R3-N7.md`](Issue-Paired-Value-R3-N7.md).

### #354/#355 low-N coverage-selector decision

- #354 freezes a strictly temporal 10h panel with 134,822 fixture rows. The
  2019–2021 expanding predictions see only earlier labels; the 2022–2024
  transfer model and all prior-calibration features are frozen through 2021.
  Annual Top-2 coverage remains close to 74–75%, so coverage reliability is a
  legitimate model target, but the data package itself does not prove Edge.
- #355 compares raw retained Top-2 mass, monotone calibration, logistic and
  shallow HGB selectors while keeping q_eu Top-2/R0 support, full Cartesian
  tickets, CNY1,024 per issue and ticket-level-once 0.65 fixed. Logistic wins
  the predeclared log-loss ordering (0.570336 versus 0.570583 for raw mass) but
  slightly loses on Brier (0.191271 versus 0.191257), so calibration evidence
  is mixed.
- On the corrected exact-common settlement denominator, coverage-only lift is
  CNY−452/+2,308/−5,914 for N3/N4/N5. N4 is the only positive clue, but its
  2024 lift is CNY−7,683, issue-bootstrap p05 remains below zero, and path risk
  worsens from 26.50%/8 to 27.69%/13. This supersedes the earlier provisional
  CNY20,555 figure, which was produced before the chronology/settlement repair.
- Verdict: `NO_PROMOTION`, not “selection is useless.” Freeze raw-mass S0 as
  the safe coverage baseline. Separate the missing return axis into #358 and
  #359: causal 10h European average odds may proxy value only under the label
  `EUROPEAN_AVERAGE_ODDS_PROXY`; it is not Beijing official SP or an exact
  deployable payout calibration. #356 waits until that two-axis selector is
  settled. #210 and #218 remain untouched.
- Reports: [`Issue-354-LowN-Selector-Data.md`](Issue-354-LowN-Selector-Data.md)
  and [`Issue-355-LowN-Match-Selector.md`](Issue-355-LowN-Match-Selector.md).

### #358/#359 low-N European-value selector decision

- #358 turns calibrated outcome probability and causal 10h European average
  odds into a per-stake Top-2 leg factor `sum_Top2(p×odds)/2`. The complete
  N-fold screen is `0.65 × product(leg factor)`, so the 0.65 burden is applied
  once per complete winning ticket, never once per leg. The source remains a
  European proxy with retrospective-relative timing, not Beijing official SP.
- #359 keeps Top-2/R0 outcome support fixed and tests the complete C×V×G
  factorial for N3–N5. `C0V0G0` exactly reproduces #355 S0; `C1V0G0` exactly
  reproduces the #355 coverage diagnostic. This isolates match selection from
  outcome replacement.
- Two exposed-history signals survive the preregistered screen. N3 value-only
  (`C0V1G0`) adds CNY4,792 versus S0 over matched 2022–2024 issues and remains
  +CNY7,618 after each arm's largest payout is removed. N4 coverage+value
  (`C1V1G0`) adds CNY6,663 and remains +CNY8,086 ex-largest; it is positive in
  2022/2023 but loses CNY9,018 versus S0 in 2024. Their issue-bootstrap p05
  values are negative, and absolute ending capital remains below CNY100,000.
- N5's largest raw clue is concentrated in 2023 and fails cross-year and
  largest-paired-delta stability. The gap factor has no repeatable standalone
  increment at the frozen cutoffs. Verdict: `HISTORICAL_SIGNAL`, not a
  deployable Edge. Preserve S0, carry N3 value-only and N4 coverage+value as
  explicitly exposed candidates into later design work, and keep #210/#218
  unchanged.
- Reports: [`Issue-358-LowN-European-Value-Data.md`](Issue-358-LowN-European-Value-Data.md)
  and [`Issue-359-LowN-European-Value-Selector.md`](Issue-359-LowN-European-Value-Selector.md).

### #356 selective third-outcome protection decision

- #356 keeps each frozen N3/N4/N5 match set and Top-2 support unchanged, then
  appends the omitted outcome on P=0..N fixtures in strictly-prior predicted
  miss order. It enumerates the full `2^(N-P) × 3^P` support while preserving
  exactly CNY1,024 per BET issue and applying 0.65 once per winning ticket.
- The 2019–2021 gate selects P2/P3/P5 for the primary S0 N3/N4/N5 lanes, but
  all three reverse on exposed 2022–2024 transfer: matched lift is
  CNY−19,871/CNY−17,008/CNY−39,011. Their maximum drawdown rises from
  28.32%/26.50%/26.53% at P0 to 40.20%/32.74%/53.43%, and longest losing runs
  rise from 15/8/8 to 21/16/18.
- Protection works mechanically but not economically. The selected arms
  recover CNY57,192/CNY82,437/CNY84,235 on baseline misses, while dilution of
  already-winning Top-2 tickets costs CNY77,063/CNY99,445/CNY123,246. Even the
  closest shallow transfer arms, N4/P2 and N5/P2, remain CNY−3,507 and
  CNY−1,382 versus P0 and are negative after largest-payout removal.
- The frozen rank does not order transfer misses monotonically: rank 1 has the
  highest predicted miss probability but a lower realized miss rate than rank
  2 in every primary N lane. Verdict: `NO_INCREMENT`. Keep P0 as the stable
  center; do not reinterpret higher support-hit rate as better capital return,
  and do not change #210/#218.
- Report: [`Issue-356-LowN-Third-Outcome-Protection.md`](Issue-356-LowN-Third-Outcome-Protection.md).

### #334 neural residual and value-anchor decision

- A bounded MLP learns a development-year match-selection lane, but it does not
  generalize: the 2023 `S1O0` median lift of CNY7,940.53 becomes
  −CNY35,277.96 on frozen 2024; its Brier score is also slightly worse than the
  European-market baseline. Neural capacity is therefore not the current Edge.
- The adversarial label-shuffle unexpectedly exposed a simpler mechanism. The
  causal value anchor `q_eu / q_line` ranks outcomes by European fair-market
  probability relative to the Beijing handicap-line probability. On the exact
  #319 matches, retaining the top two outcomes by this ratio and keeping equal
  funding yields +CNY50,722.52 in 2023 and +CNY49,393.45 in 2024 versus the
  matched probability Top-2 baseline.
- This is a long-tail candidate, not a stable center: it pays on 7/47 and 13/58
  issues, and the 2023 ex-largest lift is −CNY1,157.66 even though frozen 2024
  ex-largest is +CNY23,919.12. Issue-cluster bootstrap positivity is 70.5% and
  82.0%, respectively. It has not crossed the promotion gate.
- Allocation-only is smaller but directionally stable (+CNY2,074/+CNY6,068
  raw; +CNY4,339/+CNY7,972 ex-largest). Combining support replacement and
  value-weighted allocation is weaker than support replacement alone. Selection,
  outcome support and allocation must therefore remain separately attributable.
- Next scientific action: freeze the simple value-ranked support rule, retain
  exact #319 Top-2 as fallback, and replicate without neural fitting. #210 must
  not inherit the obsolete #209 policy identity.
- Report: [`Issue-Neural-Top2-Residual.md`](Issue-Neural-Top2-Residual.md).

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

### #292 dynamic joint-optimizer decision

- The complete feasible action surface spans N3–N10, seven K anchors and
  TOP/WR/WOR ticket generation, with cash as an explicit choice. Expanding
  2019–2023 OOF and 2024+ sealing are preserved.
- The learned low-N N3–N6 core is not near break-even: the always-active row is
  −92.17%, while predicted-mean gates from −5% to 0% are about −99% to −100%.
- The high-N tail returns +265.39% in total but has one positive year, a
  217-issue losing run, bootstrap p2.5 of −100%, and ex-largest P&L of
  −CNY4,288. The best 20%-cap barbell returns +8.03%, but ex-largest is
  −CNY14,406.71 because the core remains structurally negative.
- Post-hoc fixed N6/N7/N8/N10 clues reverse across the five nuisance ticket
  streams. N6/K8/WOR is positive in only one seed; N7/K16/WR and N8/K32/WR are
  positive in three seeds but positive ex-largest in only two and one,
  respectively. No fixed action becomes a baseline.
- Retain the two-sleeve architecture, but make sparse activation and
  ticket-level hit/payoff calibration the next development target. Do not open
  #210/2024+ until a learned policy beats cash and its matched control.
- Report: [`Issue-292-Dynamic-Joint-Optimizer.md`](Issue-292-Dynamic-Joint-Optimizer.md).

### #296 candidate-warm expert-mixture decision

- Six trusted issue-level expert ledgers are aligned to the 269-issue causal
  feature calendar. The positive #292 N7/K16/WR clue is registry-only because
  no trusted issue path exists; it is not converted into fabricated labels.
- A PyTorch expert-plus-cash gate learns issue-dependent bankroll weights from
  2019–2021, uses 2022 only for validation/fallback, and replays 2023 without
  opening any 2024+ rows. Candidate-warm, neutral, identity-shuffled and
  scikit-learn Ridge controls use the same causal state.
- The raw warm ensemble reaches CNY128,864 from CNY100,000 in 2023 (+28.86%)
  versus +54.11% neutral and +88.69% identity-shuffled. It fails 2022
  validation (-38.68%), has 61.08% 2023 max drawdown, and is negative
  ex-largest (-CNY118,016). Only 3/5 warm seeds are positive, every seed is
  negative ex-largest, and median seed growth is +17.39%.
- The hard worst-case fallback therefore rejects all neural allocations before
  opening the 2023 replay and retains the frozen static control. Its independent
  2023 path ends at CNY104,143 (+4.14%), with 52.70% max drawdown and negative
  ex-largest P&L. This is a diagnostic control, not a new accepted baseline.
- Retain the expert-mixture interface and large dynamic cash allocation, but
  decompose the next learner into conditional payout/downside estimation plus
  a separately validated risk/cash gate. Do not activate #210 or spend the
  2024+ holdout on the current model.
- Report: [`Issue-296-Expert-Mixture.md`](Issue-296-Expert-Mixture.md).

### #299 BEST_FULL-anchored residual decision

- The accepted #167/#170 `B0_BEST_FULL` is reproduced exactly on 227 matched
  2019-2023 issues; 42 feature-only issues without exact baseline evidence are
  explicitly excluded rather than imputed as NO_BET.
- The 2023 raw residual learner improves CNY100k growth from -20.75% to -9.10%,
  reduces maximum drawdown from 28.50% to 13.55%, and retains +CNY6,739 matched
  lift after removing the largest incremental issue.
- About +7.28pp comes from skipping baseline exposure and +4.36pp from additive
  sleeves. The path remains below cash, a Ridge control nearly collapses to
  cash, and actual action placement ranks only at the 38.3rd percentile of
  1,000 exposure-matched random permutations in 2023.
- Retain `exact BEST_FULL + learned residual + hard fallback`, but split the
  next learner into incumbent keep/skip and conditional sleeve value heads.
  Keep #210 and 2024+ sealed.
- Report: [`Issue-299-BEST-FULL-Residual.md`](Issue-299-BEST-FULL-Residual.md).

### #302/#305 issue-selection attribution correction

- #302's shared action-conditioned hierarchy ended 2023 at +2.63% while exact
  BEST_FULL ended at -20.75%, but causal OOF expert funding was 0%. The full
  lift therefore came from sparse BEST_FULL exposure, not expert allocation.
- #305 refit a genuinely expert-label-invariant keep/skip head. It ended 2023
  at -7.11% after funding 8 of 35 active issues, a +13.64pp matched lift versus
  FULL and materially lower drawdown.
- That lift does not identify issue selection. The selected eight issues rank
  at only the 42.71st percentile of all 23,535,820 exact same-exposure
  placements; the null median terminal capital is higher than the model. Alpha
  sensitivity changes the funded set from 10 issues to none. #302's legacy six
  funded issues rank at the corrected exact 78.51st percentile, also below the
  95% signal boundary.
- Controlling interpretation: reducing exposure to a negative FULL baseline
  reduces loss, but neither model learns which issue to bet. Do not pass this
  as selection alpha or allow a future model to win by choosing cash.
- #306 therefore keeps every mechanically eligible issue active and moves the
  learning target inside each issue: N/K, match subset, outcome direction,
  WR/WOR, selective protection and complementary expert/ticket composition at
  matched exposure. Stage-4 bankroll sizing remains separate.
- Reports: [`Issue-302-Hierarchical-Dynamic-Expert-Mixture.md`](Issue-302-Hierarchical-Dynamic-Expert-Mixture.md)
  and [`Issue-305-Dedicated-Keep-Skip-Correction.md`](Issue-305-Dedicated-Keep-Skip-Correction.md).

### #306 matched-exposure ticket-composition signal

- #306 removes issue abstention and provides a useful physical N/K/generator
  interface, but its post-merge EV found that the apparent positive mapping
  used a broader #209 support set rather than inherited exact-B0 common support.
- On the correct 2023 support the selected family changes and the positive
  matched-lift result does not reproduce. `ACTION_VALUE_SIGNAL` is withdrawn;
  #306 is retained only as interface/mechanics evidence.
- #312 absorbed the correction instead of reopening the historical PR. Its
  development and terminal selection use exact-B0 support, while #306 appears
  only as a secondary interface comparator.
- Report: [`Issue-306-Matched-Exposure-Ticket-Composition.md`](Issue-306-Matched-Exposure-Ticket-Composition.md).

### #312 joint-action decision and #314 successor

- #312 evaluates explicit N, K, match selector, candidate pool, outcome
  direction, TOP/WR/WOR and bounded protection actions. The 2023 primary ends
  at CNY70,795.72 versus CNY87,984.27 for fixed N7/K512/WOR, with only 5/31
  paired seed wins and a 13.6th same-exposure permutation percentile. The
  difference of seed medians is CNY−17,188.55; the correctly paired-seed median
  lift is CNY−18,163.94.
- The action-conditioned MLP retains weak average ranking information but hard
  argmax amplifies top-action error and long-tail winner's curse. It is rejected
  as the decision rule; this does not reject M×3 learning or soft expert mixing.
- PI review found a read-before-filter implementation defect. Parquet year
  predicate pushdown and issue-restricted SQLite reads replaced it before merge;
  a complete 2019–2023 replay reproduced all 556,274 action×seed ledger rows,
  the frozen allocation SHA and the terminal decision SHA.
- Protection adds a weak paired clue but is not independent Edge. #285 already
  rejected blanket protection, so #314 learns selective depth-1/2 coverage and
  retains no protection plus same-budget random protection as controls.
- Post-merge EV narrowed the matched factor claim: #312 reset only selector,
  outcome direction and protection. N/K, generator and candidate-pool marginals
  are descriptive only. #314 therefore requires complete matched resets, separates
  source and experiment temporal roles, and binds its external source plus ticket-
  level replay receipt without committing the large databases.
- #314 replaces fixed K512 with learned dynamic K/exposure under natural
  bankroll, uniqueness and marginal-value limits. It uses a soft CORE/TAIL MoE,
  excludes three-result full coverage, validates on 2023, freezes, then runs a
  model-unseen 2024 terminal evaluation with issue-level d=1/d=2 failure
  attribution. #210 now waits on #314 rather than #312.
- Reports: [`Issue-312-Explicit-Joint-Action-Cube.md`](Issue-312-Explicit-Joint-Action-Cube.md)
  and [`Issue-314-Core-Tail-MoE.md`](Issue-314-Core-Tail-MoE.md).

### #314 CORE/TAIL MoE terminal decision

- The 2022 screen selected Ridge with a 5% TAIL sleeve at low exposure, but the
  refit mapped every 2023/2024 issue to K2048. On exact #312 support the 2023
  raw MoE ends at CNY−57.78 versus CNY87,984.27 for the frozen N7/K512/WOR
  control, with zero paired seed wins. The mandatory fallback was therefore
  frozen before 2024 settlement.
- On 66 terminal 2024 issues the unauthorized raw challenger ends at
  CNY34,373.99 after CNY270,336 turnover. The guarded portable N7/K512/WOR
  control ends at CNY81,882.32 after CNY67,584 turnover. Dynamic exposure did
  not find Edge; it amplified an unstable K boundary.
- Fully matched factor resets reject the learned selector and outcome direction.
  Selective depth-1/2 protection is the only stable local signal: median paired
  lift +CNY1,048.49 with 80.65% positive seeds, but it loses to same-budget random
  placement by CNY594.31 at the paired median (45.16% positive). This is
  `NO_LEARNABLE_INCREMENT`, not evidence that protection placement was learned.
- #210 remains Blocked because #314 is non-promotable and prospective support
  #218 is still open. The next model iteration should isolate pre-event
  protection targeting and constrain marginal K instead of enlarging MoE
  capacity.

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
[#318]: https://github.com/algotradinglife/beijing-lot/issues/318
[#319]: https://github.com/algotradinglife/beijing-lot/issues/319
[#324]: https://github.com/algotradinglife/beijing-lot/issues/324
[#328]: https://github.com/algotradinglife/beijing-lot/issues/328
[#330]: https://github.com/algotradinglife/beijing-lot/issues/330
[#332]: https://github.com/algotradinglife/beijing-lot/issues/332
[#334]: https://github.com/algotradinglife/beijing-lot/issues/334
[#336]: https://github.com/algotradinglife/beijing-lot/issues/336
[#338]: https://github.com/algotradinglife/beijing-lot/issues/338
[#340]: https://github.com/algotradinglife/beijing-lot/issues/340
[#342]: https://github.com/algotradinglife/beijing-lot/issues/342
[#345]: https://github.com/algotradinglife/beijing-lot/issues/345
[#348]: https://github.com/algotradinglife/beijing-lot/issues/348
[#349]: https://github.com/algotradinglife/beijing-lot/issues/349
[#352]: https://github.com/algotradinglife/beijing-lot/issues/352
[#354]: https://github.com/algotradinglife/beijing-lot/issues/354
[#355]: https://github.com/algotradinglife/beijing-lot/issues/355
[#356]: https://github.com/algotradinglife/beijing-lot/issues/356
[#358]: https://github.com/algotradinglife/beijing-lot/issues/358
[#359]: https://github.com/algotradinglife/beijing-lot/issues/359
[#360]: https://github.com/algotradinglife/beijing-lot/issues/360
[#366]: https://github.com/algotradinglife/beijing-lot/issues/366
[#367]: https://github.com/algotradinglife/beijing-lot/issues/367
[#369]: https://github.com/algotradinglife/beijing-lot/issues/369
[#373]: https://github.com/algotradinglife/beijing-lot/issues/373
[#376]: https://github.com/algotradinglife/beijing-lot/issues/376
[#377]: https://github.com/algotradinglife/beijing-lot/issues/377
[#378]: https://github.com/algotradinglife/beijing-lot/issues/378
[#381]: https://github.com/algotradinglife/beijing-lot/issues/381
[#382]: https://github.com/algotradinglife/beijing-lot/issues/382
[#383]: https://github.com/algotradinglife/beijing-lot/issues/383
[#388]: https://github.com/algotradinglife/beijing-lot/issues/388

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
