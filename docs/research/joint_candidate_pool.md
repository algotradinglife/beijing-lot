# Candidate pools and hard-support anchored purchasing

Scope: accepted 140902–150202 (50 issues), frozen corrected market probabilities.
No new training or cleaning. Source is the explicit SHA-bound
`reports/joint-next50-replay-v2/receipt.json` and its source bundles. Historical
exposure and fixture-relative clock limitations remain; no prospective claim.

## User's research hierarchy

1. A useful candidate pool should give full Top2 a meaningful baseline.
2. Compress one/two positions to singles and use freed funds to buy more groups.
3. Rank outcome combinations near those hard structures to improve efficiency.
   Do not silently replace their allocation shape with unconstrained joint p.

The original 24 groups remain, plus up to 64 from the fresh deterministic
window/swap universe. Four diversified Top2 anchor groups are included first;
other additions alternate Top2 coverage and estimated gross, with pair overlap
at most four among newly added groups. The anchor groups are not retroactively
excluded by the overlap rule. No sampled seeds/thresholds are optimized on labels.
It is a bounded candidate family, not proof of a globally optimal candidate pool.

HARD0/1/2 buy all 128/64/32 states per group. Singles are the one/two fixtures
with largest frozen Top1 probability (ties slot). All other legs use Top2.
Each full group costs CNY256/128/64; budget CNY1024. Existing allocator considers
incremental any-hit per CNY and uses the freed budget for more distinct groups.
No hard final fixture reuse ceiling is imposed.

WITHIN0/1/2 offer quarter/half/full supports ranked by probability. They cannot
purchase excluded outcomes. ANCHOR0/1/2 rank
`(1-epsilon)*normalize(p^temperature * hard_mask) + epsilon*p`, with
`temperature=.5, epsilon=.05`. Transformed scores rank tickets only; original p
still prices and simulates them. Outside-support tickets cannot exceed 5% of an
option. Each option's uniform paid-ticket marginals must be within total
variation .25 of the original hard per-leg distribution (single 100%; double
50/50). Full hard support remains available. If greedy selection's model-world
any-hit is below the hard portfolio, that hard portfolio is retained.

This safeguard is label-free and applies only to the optimization model, not
actual observed winnings or independent simulation. Defaults are fixed diagnostic
policies, not empirically fitted calibrations. The user has not approved a
production model or deployment.

JOINT_NATIVE keeps prior 25%/256 rules and its old 256-world seed. Hard/anchored
methods share 4096 selection worlds (seed42503), then use independent 4096
assessment worlds (seed42502); these assessment worlds do not pick the policy.
The old JOINT ticket ledger remains an additional reference. Original/new JOINT
isolates pool expansion; comparisons within a compression level isolate anchored
purchase logic. Cross-compression comparisons also change breadth and risk.

## Reproducibility and functions

- `r/joint_candidate_comparison.R`: `joint_candidate_expand`,
  `joint_candidate_compare`, `joint_candidate_settle`, `joint_candidate_seal`.
- Tests `tests/testthat/test-joint-candidate-comparison.R` exercise all four:
  old-group preservation, native enumeration, JSON save/reload (including no-bet), fixed support sizes, cutoff
  rejection, seal/label errors, all-cash output and official payout once .65.
- Existing `top2_fresh_groups`, `n7_probability_allocate`, `n7_core_allocate`,
  `n7_joint_worlds`, `n7_joint_returns`, `n7_sleeve_tables`, SP gate, equity and
  summary functions remain authoritative.
- QMD `quarto/225_joint_candidate_pool.qmd`, explicit config with repo/input
  receipt hash/output/Python. Freeze every plan before opening official labels;
  bind source/R/transitive Python implementation identities.

Report stake, net, ROI, drawdown, hit/profitable issues, model-vs-realized hits,
rescued/lost issues, hard fallback frequency, and results without the best issue.
Render figures in the conversation. No RDS delivery, no issue closure or merge.

The interrupted v1 run tested an earlier flat JOINT128 proposal. It was stopped
before settlement when the user clarified the hard-support hierarchy, and is
marked NOT_ACCEPTED_INTERMEDIATE. It is not a result source.

Independent audit: `scripts/check_joint_candidate_replay.py REPORT_DIR` expands
canonical states and checks hard supports, ranked prefixes, per-leg marginal TV,
outside-support paid fractions, original p/q pricing and official settlement.
`tests/test_joint_candidate_replay.py` exercises HARD/WITHIN/ANCHOR success and
rehash-coherent corruption rejection on 50 synthetic periods. Source/file hashes
and unique ticket identities are checked independently. Numerical prefix ties
allow only a 1e-12 score tolerance, not a different substantive ranking.

Formal report: `reports/joint-candidate-pool-v3`, rendered QMD under
`reports/joint-candidate-pool-html-v3`, in the configured persistent data root.
v2 was stopped before labels for portable JSON seal enforcement; v1/v2 are
explicit rejected intermediates. No RDS fallback or compatibility layer.

## Results (50 issues; strategies evaluated separately)

| Strategy | Stake CNY | Net CNY | ROI | Hit issues | Profit issues | Max DD CNY |
|---|---:|---:|---:|---:|---:|---:|
| Old JOINT | 44,054 | -13,883.13 | -31.51% | 18 | 13 | 16,864.84 |
| Expanded JOINT | 48,738 | -11,454.67 | -23.50% | 32 | 18 | 14,360.66 |
| HARD0 | 51,200 | -16,129.66 | -31.50% | 25 | 12 | 17,397.44 |
| HARD1 | 51,200 | -8,723.35 | -17.04% | 26 | 13 | 9,673.74 |
| HARD2 | 51,200 | -15,949.25 | -31.15% | 27 | 15 | 15,949.25 |
| WITHIN0 | 51,200 | -1,503.96 | -2.94% | 25 | 18 | 6,418.77 |
| WITHIN1 | 51,200 | -17,947.94 | -35.05% | 27 | 13 | 20,113.06 |
| WITHIN2 | 51,200 | -22,476.20 | -43.90% | 31 | 11 | 23,004.80 |

ANCHOR equals WITHIN ticket-for-ticket for all three compression levels; no
outside-support ticket was selected. This does not test a realized benefit of
third-outcome expansion.

The original JOINT comparison changes only the pool and improves net CNY2428.46.
The hard/anchored comparison supports moderate depth reduction while retaining
all seven Top2 legs, not aggressive compression followed by further thinning.
WITHIN0 rescues seven HARD0-missed issues and loses seven HARD0-hit issues, so its
25 hit periods are unchanged. Group hits rise 30→44 and profitable periods12→18.
WITHIN1/2 increase hit periods but lose more money than their hard counterparts.

Critical reference: previous fresh diversified Top2 was -1490.22 CNY, not the
current HARD0's -16129.66. Current HARD0 changes the candidate pool AND uses
4096-world greedy group selection in place of the prior exact union selector.
Its degradation cannot be attributed solely to pool construction. The previous
four-group portfolio remains feasible in the expanded universe; greedily choosing
other groups is not a guarantee of realized improvement.

WITHIN0 is essentially equal in net to the previous diversified Top2, with
maximum DD reduced 10980.87→6418.77 (about42%). Without its best issue it loses
6127.12 CNY, versus the prior Top2's10455.39 loss. This is risk-shape improvement,
not evidence of positive profitability or a completed optimal candidate pool.

Readable findings entry: `quarto/226_joint_candidate_findings.qmd`; rendered at
`reports/joint-candidate-findings-v1/226_joint_candidate_findings.html` under the
persistent root. Full computation/550 period rows remain in225/v3. Independent
checks passed for6749 expanded-pool strategy-group purchases, plus old-reference
reconciliation, summary profits/net/drawdowns and exact WITHIN/ANCHOR equality.
Five targeted R suites and three independent Python audit cases passed. Full
unrelated worktree tests were not claimed as run. Codex review findings were
fixed and re-reviewed; no merge or Issue lifecycle change.
