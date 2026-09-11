# N5 single10 and U3 equal-budget portfolio

Same48 historical issues100402–100607. Each strategy account starts at
CNY100,000. The new portfolio splits each CNY1,024 issue budget into two
CNY512 wallets: N5 single10 and no-swap N7 U3. This is equal budget, not
necessarily equal actual expenditure. Unused wallet money stays cash.

Keep complete groups in existing source order: at most32 N5 groups (CNY16 each)
and8 U3 groups (CNY64 each). No fractional units, refill, cross-wallet transfer,
new ranking, or simple50% scaling of old net returns. Preserve N5 seed0–99 swaps
as frozen; retain U3 supports. Within each source original reuse limits remain,
cross-source fixture overlap is allowed. One .65 factor per winning basic ticket.

All100 seeds are frozen before this run reads settlement, with native cutoff,
source hashes and implementation closure. Existing history was already exposed;
this remains retrospective description, not clean prospective acceptance.

## Results

Actual aggregate mix expenditure is38,528 CNY: N5 spends23,040 and U3 spends
15,488;10,624 of the48 issue budgets is unspent. Each side was allocated24,576
over48 issues, so actual spending is not1:1. All seeds use identical funding.

Predesignated seed0: net26,166.33, ROI67.92%, final equity126,166.33, maximum
drawdown5,826.19,28 hit issues and247 winning groups out of1,682 groups.

Across100 seeds: mean net26,945.69, ROI69.94% (5th–95th64.41%–75.46%),
mean hit issues29.34, median max drawdown5,833.80 (95th5,888.00).
Standalone N5 single10 averages net16,828.83/ROI36.52%/median DD7,539.87;
standalone N6 single10 averages27,335.95/59.32%/7,648.13. Fixed no-swap U3
has19,946.49/117.61%/DD2,057.14 and U6 has24,713.37/77.70%/DD4,416.06.
N6 no-swap remains ahead in net return37,636.65 (stake46,080), DD7,563.98.

Mixing improves the N5 single10 account in this sample, but still has greater
drawdown than either no-swap N7 control. Differences include group truncation
and actual expenditure; they cannot all be attributed to diversification.
The previous untruncated hit-set union is not the hit count of this funded mix.
Main figure is seed0, not the above random-seed average or a selected best seed.

## Reuse and checks

- `flatten_component_groups` in `src/fundamentals_missed_portfolio.py`
  translates sealed component envelopes to the existing flat group interface,
  preserving order/supports/units and binding exact source and component seals.
  It validates native cutoffs via the shared decision-chain limiter.
- Existing `fixed_n67_wallets` allocator now also accepts five-leg groups.
  The source-order, complete-unit, duplicate-holding and no-transfer allocation
  implementation is reused. Existing settlement is reused through
  `settle_n7_baseline`; no new probability or payout implementation.
- Entry point `scripts/n5_single10_u3_mix.py freeze|settle --study NEW`;
  R report `quarto/119_n5_single10_u3_mix.qmd` imports existing report/equity
  functions. One two-panel figure compares equity and negative drawdown for
  eight strategies. All random curves use predesignated seed0; separate tables
  report all100 seeds, so the example is not mistaken for the average.
- Tests17 passed: new flatten/allocation test plus existing wallet, N6 efficiency
  and high-hit filtering regression tests. Cover32+8 complete groups, cash when
  U3 is short, unchanged inputs/supports/order, actual .65 settlement, empty and
  corrupt sources, wrong N and native cutoff failures. Governance scan passed.
- Independent `scripts/check_n5_single10_u3_mix.py` checks exact32/8 original
  prefixes, full ticket settlement, wallet stakes and all404 financial curves.
  All168,200 physical groups and4,800 mixed issue rows passed; all standalone
  controls and19,796 curve observations reconciled. Existing R tests passed31
  assertions. Live/archive fresh renders passed with execution enabled, cache
  disabled and fatal errors; three CSVs and PNG are byte-identical. Both HTML
  reports contain8/4/4/1 table rows and one visually checked two-panel plot.
  The portable fixture and new CI step are included.
  Full-suite and remote-CI execution are not claimed.
- Final Codex CLI review found no actionable defects in the exact eight-file
  scope. The reviewer independently reran all17 Python tests and the168,200-group
  checker, including404 policy metrics/curves, and checked portable fixture
  contents/hashes against live outputs. The reviewer did not repeat freeze or
  rendering; those fresh-process checks were performed by the implementing agent.

GitHub #419 remains OPEN, blocked by OPEN #421; no lifecycle changes.
