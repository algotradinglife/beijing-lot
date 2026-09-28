# Initial fundamentals capability probe

Execution evidence for [#407](https://github.com/algotradinglife/beijing-lot/issues/407),
under [#406](https://github.com/algotradinglife/beijing-lot/issues/406).
This is a seven-request capability probe, not the approximately 100-fixture
census, a source-error-rate estimate, a completed crosswalk or an accepted release.

## Observed results

Captured on 2026-09-05 between 09:27:43 and 09:28:18 UTC, with at least five
seconds between top-level requests and a 25-second request timeout.

| Request | Result | Interpretation |
| --- | --- | --- |
| Nowscore current SPF roster | HTTP 200, selected issue 26092, 388 visible fixture rows | Source-native candidate inventory; not certified complete coverage |
| Nowscore issue 20064 SPF roster | HTTP 200, selected issue 20064, 313 visible fixture rows | Historical regression discovery |
| Nowscore analysis 3000054 | Connection reset | No analysis payload; not field absence |
| Titan analysis candidate 3000054 | HTTP 442, empty body | Unusable response; cross-source identity unverified |
| Nowscore analysis 1870517 | Connection reset | No analysis payload; not field absence |
| Titan analysis candidate 1870517 | HTTP 442, empty body | Unusable response; cross-source identity unverified |
| Exeter City original club match report | HTTP 200, titled Exeter City 3 Colchester United 1 | First-party historical evidence candidate, raw bytes preserved |

Current-roster first candidate is slot 62, 藤枝MYFC / 八户云罗里, Nowscore ID
3000054. No claim that the first displayed fixture is still pre-decision.
Regression slot 20064/293 identifies 埃克塞特 / 科切斯特, Nowscore ID 1870517,
and currently displays full-time 2–1 and half-time 1–0. Equal numeric Titan IDs
were probed as candidates only; no mapping was admitted.

The saved [club report](https://www.exetercityfc.co.uk/news/2020/june/-match-report-exeter-city-3--colchester-united-1)
is dated 22 June 2020. Its title gives 3–1; the narrative places Ryan Bowman's
winning goal in extra time after describing the end of 90 minutes. Together
these support the distinction between regulation 2–1 and after-extra-time 3–1.
This is a semantic regression example, **not evidence that the freshly fetched
Nowscore score is wrong**. No Titan score was acquired, no disagreement was
adjudicated, and no lottery/SP conclusion or correction was made. The old local
correction list supplied a discovery lead only; its values were not imported.

The official club source is first-party for its match report. Its relevance is
the original narrative, not an assumption that all embedded statistics have an
independent upstream feed. Preserve that distinction in the future adjudicator.

## Artifacts and checks

Local data run: `data/derived/fundamentals_census/20260905_initial/`.
It contains `manifest.json`, `raw/<sha256>`, `candidates.json`, the exact executed
`probe.py` and `verification.json`. Raw hash verification passed for all five
HTTP response entries, including two empty error responses sharing one hash.
The two connection failures have error entries and no fabricated raw receipts.

- Manifest SHA256: `574336de021b0ddfaefffe87aa9ef6eede12bacbb0daaa88f0edb73cde20328a`.
- Probe program SHA256: `47ae938302c7dfd540b96401e272c3926badc3eddf99accad7061c49460dca90`.
- Seven attempts: three HTTP 200, two HTTP 442, two transport failures.
- No historical learning, feature fitting, model-facing admission or settlement mutation.

## Outstanding census acceptance

Diagnose analysis-page access using documented source entrances and capture
supported responses before treating either adapter as usable. Expand the saved
source-native sample across competitions/seasons and genuinely upcoming fixtures;
measure populated fields rather than text markers. Obtain identity-bound
independent evidence for actual dual-source discrepancies. Produce the full
source/field/independence matrix and denominator-based census; this first probe
does not satisfy those acceptance requirements.
