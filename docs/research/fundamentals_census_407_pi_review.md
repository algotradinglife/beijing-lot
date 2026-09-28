# #407 PI acceptance review

Reviewed against the live issue body and native graph on 2026-09-05, after routing
the Task under #406 to PI Review / PI. This is the census acceptance review,
not acceptance of production features, a historical model, or #405 settlement.

| Original requirement | Inspected evidence | Conclusion |
| --- | --- | --- |
| Parser/store and identity semantics inventory | `fundamentals_helper_governance_407.md`, source code, `fundamentals_census_data_contract.md` | PASS; legacy truncation/coercion/availability gaps are explicit and not reused as feature interfaces. |
| Bounded real historical and upcoming sampling from native rosters/recent seasons | Six saved native roster receipts; main panel 100, historical/upcoming 70/30; original and corrected membership hashes | PASS; lottery-day correction preserved as a diagnostic revision, not backdated prospective selection. |
| Explicit stratification and denominator | Eight competition strata, quotas 35/35/30; 1082 candidates with 100 selected/99 eligible-not-selected/14 already-started/869 outside scope | PASS. |
| Separate anomaly/regulation/replay panel | Three native issue/slot identities; six analysis documents parse; official original narratives/rulings | PASS; original/restarted/rescheduled occurrences remain distinguished. |
| Actual fields, access, encoding, request budget, missingness and evidence class | `main/responses.csv`, `fields.csv`, original request receipts and report; 200/200 parsed plus 100 required JS assets | PASS; HTTP status and parsing distinct; historical proxies and observed captures not admitted as features. |
| Official source registry per competition and syndication assessment | Eight registry entries and actual access receipts; CBF DNS failures and KNVB maintenance content explicitly unusable | PASS for census registration/access assessment; unavailable pages are not fabricated independent evidence. |
| Source/field matrix, manifests and raw receipts | Rendered seven-table report and sealed 417-file bundle | PASS; field scope/units and unsupported layouts declared, no site-wide completeness claim. |
| Independent verification of discrepancies and agreement spot-checks | Seven versioned review cases, two corroborated shared facts; raw official bytes/URLs/hashes/reviewer/rationale inspected | PASS; three ten-minute clock semantics stay unresolved, two occurrence hazards stay quarantined. Depth differences are unadmitted source-only observations, not score votes. |
| No mixed-source settlement writes or imported correction truth | Census module and thin commands contain no settlement writes; old correction notes used only to locate fresh native rows and official documents | PASS; #405 unchanged. |
| Transitive historical-learning inventory and chronology governance | Learning NONE; imported constant/parser files bound; cutoff checker PASS | PASS; fit/recency/window/decision-cache/post-cutoff mutation requirements are inapplicable because no learned client or decision output exists. They remain mandatory for later work. |
| Corresponding function tests, integration, rollback and replay | 62 Python tests passed; final full R suite passed; code-change-during-replay and publish rollback tests; raw and output hashes verified | PASS. Existing personal external-DB test dependency is disclosed, not treated as portable coverage. |
| Clean Quarto and visual inspection | R startup/profile files disabled with explicit project `r_lib`; cache/freeze disabled; errors fatal; seven tables and seven review cases, no execution errors or page overflow; screenshot inspection | PASS. |
| Independent replay from actual delivery | Fresh-process replay of both corpora matched complete receipts; another replay imported **sealed code snapshot** and matched both complete receipts | PASS; no undeclared worktree helper is needed for the Python replay. |
| CI coverage and current publication state | Offline workflow covers affected Python/R checks, governance, fixture replay and QMD; exact local checks executed | PASS for configured coverage/local census acceptance; no unrun remote CI or PR merge is claimed. Uncommitted shared #405 parser is included in the local code snapshot and must be retained on publication. |

Bundle: `data/derived/fundamentals_census/20260905_full/`.
Manifest SHA-256:
`030fb1df2826327f8c2619cd14efb246557e8294c05662b6d7ca782cc6ea22b4`.
All 417 listed file hashes, replay source/output hashes and implementation hashes
were read and checked. The native graph, not this document, controls closure.

Disposition: census acceptance passes with the explicitly retained uncertainty
required by the owner contract. Production integration, independent adjudication
of admitted features and removal of obsolete production parsers belong to #408;
no unresolved field is made usable by accepting this census.
