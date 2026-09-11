# No-swap N5/N6/N7 equity and drawdown

QMD entry: `quarto/116_n5_n6_n7_curves.qmd`. Same48 issues100402–100607,
four separate CNY100,000 accounts; fixed existing issue stakes, unused cash
retained, no compounding of stake size, no swaps or score protection. N5/N6
have no effective U cap; N7 retains U3/U6. Settlement already includes one .65
ticket-level payout factor. These are exposed-history descriptive curves.

|Strategy|Final equity CNY|Total stake CNY|Net CNY|Stake ROI|Max DD CNY|
|---|---:|---:|---:|---:|---:|
|N5|122,401.47|46,080|22,401.47|48.61%|7,433.45|
|N6|137,636.65|46,080|37,636.65|81.68%|7,563.98|
|N7 U3|119,946.49|16,960|19,946.49|117.61%|2,057.14|
|N7 U6|124,713.37|31,808|24,713.37|77.70%|4,416.06|

Green N6 has greatest final equity; orange U3 has smallest nominal drawdown and
also least actual investment. Equal initial bankroll does not equal invested
capital. Blue N5 and green N6 share several substantial drawdown periods.
No combined portfolio or allocation improvement is claimed by these plots.

## Evidence

- Source is the sealed `n5-single-swaps-v1` result, selecting N5_NO_SWAP and
  its three unchanged controls, exactly192 policy/issue rows. No random arms.
- Reuses `read_pure_baseline_report` and `strategy_equity_curves`; no new
  functions or historical learning. Existing R tests passed31 assertions.
- Fresh live and archive QMD renders passed with execution enabled, cache
  disabled, errors fatal. Outputs: `n5-n6-n7-curves-v1` and
  `n5-n6-n7-curves-archive-v1`. Both CSVs and both PNGs are byte-identical.
- Independent NumPy recomputation from source verified all196 observations
  (including four initial balances), equity, drawdowns and maximum drawdowns.
- Both HTML reports have four summary rows and two plots, no execution errors;
  PNGs were visually inspected for labels, units, legends and chronology.
- Provenance binds source inputs, QMD, imported R helpers, explicit parameters
  and generation time. CI uses the committed N5 fixture for offline rendering.
  Full repository tests and remote CI have not been claimed as run.
- Independent Codex review passed with no actionable defects, checking all196
  balances/drawdowns, source and code bindings, summaries, archive equality,
  plot labels and CI fixture. Root ran fresh renders and live Issue Graph reads;
  reviewer did not repeat them. Log: `n5-n6-n7-curves-review.txt` under the
  derived `fundamentals_417` directory.

Live graph: #419 OPEN blocked by #421 OPEN. No lifecycle change from this
historical visualization; it does not satisfy cutoff-safe acceptance.
