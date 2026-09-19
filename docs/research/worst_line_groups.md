# Worst-window handicap-gap group selection

Post-hoc diagnostic, not unseen validation. Select the 25 lowest-net JOINT_BASE
issues from the frozen 939-issue ledger, tie-breaking by ascending issue ID.
All have zero payout. Matrix evidence excludes 100105 and 101001, leaving 23;
missing issues are not replaced. At the -1020 boundary, five of eight tied issues
are included by that deterministic rule.

QMD: quarto/245_worst_line_groups.qmd. Config: config/worst_line_groups.json.
Artifacts: external audits/worst-line-groups-v2 and reports/worst-line-groups-v2.

Strong means an unambiguous half-grid line gap of at least one goal. Retain only
existing groups containing the required number of strong fixtures. Keep native
JOINT probabilities, state prefixes, SP gate 1.3, shared worlds, 1024 CNY cap,
2 CNY tickets and one 0.65 payout factor. This does not force single selections
or create new groups; it cannot assess those distinct interventions.

| Arm | Funded issues | Hit issues | Stake CNY | Payout CNY | Net CNY | ROI |
|---|---:|---:|---:|---:|---:|---:|
| Original JOINT |23|0|23514|0|-23514|-100%|
| Direct gap, at least 1 |12|0|11998|0|-11998|-100%|
| Conditional gap, at least 1 |8|0|7792|0|-7792|-100%|
| Conditional gap, at least 2 |4|0|3218|0|-3218|-100%|

No recovered winning issue. Every yuan of reduced loss is unspent stake, not
new payout. A strong-gap eligibility gate alone has no demonstrated rescue
benefit in this failure window. This does not establish that gaps have no value
for calibrated probabilities, reconstructed groups, or full-history selection.

Validation: exact BASE group/state ticket parity with the original sealed plans;
56 targeted test assertions passed; clean QMD execution; independent settlement
of 23,261 tickets (23 issues x four arms), with cash attribution reconciled.
The discontinuous failure window is not presented as a chronological drawdown
backtest. All outcomes selected the window, which is explicitly diagnostic.
