# #133 Gate B v2 — WR baseline settlement

This is the corrected historical paper-research settlement for
`BJ-HIST-DIVERSIFIED-N7-ALLOCATOR-001`. It supersedes the inference of the
v1 settlement while retaining `results/bj133_gate_b_outcome_settlement_v1` as
an immutable diagnostic artifact. It does not authorize betting, purchasing,
or production deployment.

## Correction

Gate-A v1 froze only `Q_INFORMED_WOR_DISTINCT`: Q-weighted ticket draws without
replacement. That made the v1 comparison incapable of separating natural
probability concentration from an allocator that removes overlap.

The outcome-unexposed additive package
`results/bj133_gate_a_preoutcome_v2_wr_additive` binds the accepted v1
allocation plan (`SHA256SUMS.json`
`1fff3f904fcb9a5efed231771880be8ae0603b0d8f3c7d0365937fcfe9985e79`) and
freezes 46,980 `Q_INFORMED_WR_DUPLICATE_STAKE` rows. Each row has the same
complete-issue identity set, gate, K, M, selected portfolio IDs, allocation
status, and seed (`133001`–`133003`) as v1; it changes only the ticket sampler.
No outcome, final SP, payout, ROI, or tax realization is used in that freeze.

For WR, every draw is a separate ¥2 ticket. Duplicate code vectors remain
separate paid tickets; any winning duplicates are taxed separately at the
ticket level. WOR-distinct remains an unchanged sensitivity arm. q-delete,
match-exposure, Jaccard, and joint caps remain explicit allocation controls.

## Settlement and accounting

`results/bj133_gate_b_outcome_settlement_v2` has 99,180 policy/issue/seed
rows: the original 52,200 v1 rows plus 46,980 additive WR rows. It joins only
the two Gate-A packages and the canonical trusted final-SP outcome payload.
The result package reports per policy:

- exact draw, unique-draw, duplicate-draw, and duplicate-group counts;
- selected-identity shared-leg geometry (`unique_match_count`, leg slots,
  overlap slots, maximum match exposure, effective independent match count,
  and pairwise Jaccard);
- capital utilization versus the exact-K4 FULL reference;
- pre-tax ROI first and individual-ticket-tax ROI second; and
- matched complete-issue ROI deltas, chronology views, deterministic issue
  bootstrap, and the locked primary-family adjustment.

The tax rule is unchanged: 20% only where a *single* winning ticket gross is
at least ¥10,000. No issue, allocator, or policy receipt is aggregated to cross
the threshold.

## Corrected primary comparison

The primary question is now only `ACTIVE_CAP_WR_MINUS_WR_BASELINE`: q-delete
exposure cap 1 or 2, sampled WR, versus same-config/seed
`CONCENTRATED_TOP_SCORE` sampled WR, on exact complete-issue matched support.
There are 12 primary comparisons (M64/M128 × cap1/cap2 × three frozen seeds)
and 24 ROI metrics in the Bonferroni family. WOR-minus-WR and cap-WOR-minus-WR
are sampling sensitivities, rather than evidence that an active cap helps.

The WR baseline exhibits measurable natural duplicate concentration. For the
primary `CONCENTRATED_TOP_SCORE`, seed `133001` contains 949 duplicate draws
out of 65,024 at M64 and 3,835 out of 130,048 at M128. The corresponding
WOR arms have zero duplicate draws. Shared-leg geometry is intentionally
unchanged by the sampler for the same frozen allocation (mean effective
independent match count 7.84; maximum selected-identity match exposure 4 for
these primary summary rows).

Across the 12 primary cap-versus-WR deltas, only M64/cap1/seed133001 and
M64/cap2/seed133001 are positive pre-tax (+0.2665 and +0.0469). The other ten
are negative. Every bootstrap interval crosses zero or is negative, and all
Bonferroni-adjusted two-sided p-values are above 0.05. The terminal result is
therefore `NO_PROMOTION`, with no strict independent EV candidate.

The v1 no-promotion result must not be read as a conclusion about the natural
WR sampler. The v2 conclusion is narrower and properly identified: the two
primary q-delete caps do not show stable, adjusted support for improving the
WR probability baseline under this frozen historical contract.
