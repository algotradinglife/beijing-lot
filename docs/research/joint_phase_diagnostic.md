# JOINT early drawdown and later plateau

Frozen joint-full-v3 scope784issues. No learning, allocation changes or data
cleaning. Descriptive windows: BEFORE1–305 (100708–111103), DRAWDOWN306–399
(111104–120419), AFTER400–784 (120420–140901). They are outcome-selected
historical windows, not prospective regime signals.

JOINT net/ROI: +68347.56/25.47%, −23852.02/−28.48%, +8693.14/2.45%.
Group hit rates:26.48%,21.71%,26.42%; mean model coverage~25.1% throughout.
Mean gross per winning group:760.06,525.53,550.79 CNY. Later mean group
cost142.04 implies an ex-post break-even rate25.79%, barely below26.42% actual.
Actual winning-rank median273→338→218; the later plateau does not coincide
with systematically deeper winning ranks. Same-eligible-pool hit rates share
the drawdown, weakening a selection-only explanation.

Selected-fixture corrected Top2 stays~76.5–77.0%; mean third-ranked results per
group1.62→1.57→1.53. No descriptive evidence of a third-outcome surge or
sustained probability collapse. Frozen-input qualifying fixture counts grow;
they are not full-roster market coverage counts. League/form fields absent.
Later winning-group estimated payout455.97→385.22 and actual/estimated payout
ratio1.667→1.430 both decrease: do not attribute everything to a general fall
in Beidan prices, since winning-combination composition changes too.

All four strategies lose in the94-issue drawdown. Confidence-reuse loses less
money but worse ROI(−35.22% vs JOINT−28.48%); smaller exposure is not proof of
better selection. No new default or switching strategy is proposed.

Implementation: `r/joint_phase_diagnostic.R`, reusing fixture-price, exact
return bridge, candidate/member reconciliation, rank-depth and probability
diagnostic functions. `quarto/205_joint_phase_diagnostic.qmd` declares all
paths/hashes and renders tables/figures; outputs persist under
`reports/joint-phase-diagnostic-v1`. Unit tests in
`tests/testthat/test-joint-phase-diagnostic.R`; upstream structure tests retained.
New regression checks multiple profitable issues with unequal stakes in one
phase to catch dplyr summarise name shadowing. Independent source-row totals
verify all12 phase/strategy monetary and hit-count rows.

Acceptance:18 new and45 upstream R assertions pass; cutoff governance passes.
QMD renders in a fresh R process with errors fatal and cache/freeze disabled;
figures inspected and all published code/output hashes verified. Final Codex
review finds no remaining actionable P1/P2. No remote CI or unrelated full
repository test claim. Explicit commands:

```sh
Rscript --vanilla -e 'testthat::test_file("tests/testthat/test-joint-phase-diagnostic.R");testthat::test_file("tests/testthat/test-n7-recent-structure.R")'
python scripts/check_cutoff_governance.py
quarto render /run/media/drwho1985/Sandisk/data/beijing-lot/reports/joint-phase-diagnostic-v1/report.qmd --execute-params /run/media/drwho1985/Sandisk/data/beijing-lot/reports/joint-phase-diagnostic-v1/params.json
```
