# N5: two singles, three doubles, uncapped reuse, 25% single swaps

Same exposed 48-issue sample 100402–100607. This is a historical diagnostic,
not new clean acceptance or a learned deployment policy. No expert or score
protection; no seed optimization. GitHub #419 remains blocked by #421.

## Results

45 active issues each spend CNY1,024; three no-bet issues. All N5 arms spend
CNY46,080 on 2,880 groups, exactly twice the N6 group count at equal investment.

|Strategy|Net CNY|ROI|Hit issues /48|Winning groups|Max drawdown CNY|
|---|---:|---:|---:|---:|---:|
|N6 uncapped, no swap|37,636.65|81.68%|20|223 /1,440|7,563.98|
|N5 uncapped, no swap|22,401.47|48.61%|22|505 /2,880|7,433.45|
|N5 25% single swap, 100-seed mean|9,894.18|21.47%|30.87|346.36 /2,880|7,660.90 (median)|

Random-seed ROI median21.47%, 5th–95th percentiles11.21%–33.11%. All100 seeds
have positive net return, but none beats the same-group N5 no-swap control.
Mean rescued issues8.91, lost issues0.04. These are randomization distributions
on exposed history, not future uncertainty intervals or probabilities of profit.
Winning at least one group in a period is not the same as a profitable period.

The swap version distributes wins over more issues but reduces total winning
groups and net payout. Relative to N5 no-swap, mean net falls CNY12,507.29; it
does not improve median drawdown. On this sample it is a hit-period improvement,
not a return/drawdown improvement. N6 remains ahead in net return at equal stake.

## Contract

- Fixed CNY1,024 issue budget, CNY2 basic units, N=5 and two singles imply
  eight basic tickets per group (CNY16), at most 64 funded groups.
- Reuse the authoritative consensus assembler with roles 2A/2D/1C. Initial
  singles require p/q Top1 agreement and market Top1 probability at least .5.
  Singles ranked by market probability; doubles use baseline Top2. Exclude
  zero-handicap Top2 disagreements. One more D double is removed from the
  N6 role quota; groups are rebuilt from the full eligible candidate pool.
- First disjoint groups, then expand with pair overlap P4. No effective U cap:
  passing max_uses64 cannot prevent any placement before funding is exhausted.
  Identical five-fixture sets are not repurchased; insufficient groups leave cash.
- First fixture appearance remains unchanged regardless of role. Each later
  occurrence that is a single independently switches from market Top1 to market
  Top2 with probability .25. Doubles never switch. The common deterministic
  hash(seed, issue, group, slot) mechanism is reused; no cascading replacements.
- Predeclare all seeds 0–99. Assemble once per issue and keep identical groups,
  costs and cash in the N5 no-swap control and all 100 random variants.
- Compare with previously sealed N6 uncapped and N7 U3/U6 no-swap results,
  whose actual investment and overlap policies differ. No isolated-N claim.
- Ticket payout uses actual settlement SP and one .65 factor. Final SP is never
  used in group selection or randomization. All 48 plans and seeds seal before
  this run opens settlement labels. Prior historical exposure remains explicit.

## Reusable interfaces and reproduction

`independent_consensus_portfolio(..., group_size=5, max_uses=64,
max_pair_overlap=4, ...)` now supports N5 alongside N6/N7, using the existing
solver and role logic. `random_reuse_plan(..., single_probability=.25,
double_probability=0, group_size=5, ...)` uses explicit role-specific rates.
All current callers/tests use these two parameters; there is no old-signature
compatibility wrapper. Existing .3/.3 studies retain their behavior on replay.
Old sealed report packages remain archived evidence; changed implementation
hashes correctly prevent presenting them as current-code live replays.

Thin entry point `scripts/n5_single_swaps.py freeze|settle --study NEW`.
QMD `quarto/114_n5_single_swaps.qmd` performs R analysis using the existing
report reader and equity functions. It shows controls, all-seed distributions,
per-issue net/ROI/hits, and equity/drawdown curves. The seed0 curve is designated
in advance, not chosen as a winner. No new dependencies or chronology helpers.

## Validation

- N5 function tests cover 64 groups funded, 64 uses of a fixture, P4, 2A/2D/1C,
  eight basic tickets per group, first-use preservation, deterministic seeds,
  single rates 0/.25/1, doubles always unchanged, invalid probabilities/cutoffs,
  unchanged input and budget. Existing N6/N7 regression tests are retained.
- Tests: `python -m pytest tests/test_fundamentals_n5_single_swaps.py tests/test_fundamentals_reuse_random.py tests/test_fundamentals_consensus_portfolio.py tests/test_fundamentals_n6_uncapped.py tests/test_fundamentals_consensus_n6_n7.py tests/test_fundamentals_double_source.py -q`.
- Existing R equity and report tests passed 31 assertions; cutoff governance
  scan passed. Full-repository/remote-CI execution is not claimed.
- `scripts/check_n5_single_swaps.py --study STUDY` independently recomputes
  physical support, all seed decisions, actual ticket payouts and R financial
  metrics. It also verifies that external N6/N7 controls remain byte-equivalent
  as decoded records. No settlement routine is imported by this checker.
- All 31 Python tests passed. Physical audit passed 290,880 groups, 138,172
  single swaps and maximum fixture reuse64; all 4,848 N5 rows and 104 policy
  financial summaries reconciled independently against actual tickets.
- Live `n5-single-swaps-v1` and portable `n5-single-swaps-archive-v1` both
  rendered freshly with execution enabled, cache disabled and fatal errors.
  Five CSVs matched byte-for-byte; both HTML reports contain tables with
  4/1/1/1/48 rows plus two visually inspected equity/drawdown plots, no errors.
  The portable fixture is committed and the CI render step is configured.
- Final independent Codex review passed without actionable defects, after the
  initially missing CI fixture was supplied. Reviewer reran 31 Python tests,
  31 R assertions and the full physical audit, and verified fixture/receipt
  bindings, archive equality and reported interpretation. Root ran the fresh
  renders; reviewer inspected their outputs without rerendering. Review log:
  `data/derived/fundamentals_417/n5-single-swaps-final-review.txt`.
