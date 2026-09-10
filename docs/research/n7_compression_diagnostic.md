# N7 compression count sweep

Same 40 exposed issues, frozen expert snapshots and weights, original per-issue
budget totaling CNY55,040. Fix MAX_SINGLE, vary k=0..7 only. Cost per logical group
is 2*2**(7-k). The first k fixtures ranked by Top1 probability retain Top1 only;
others remain doubles. Disjoint probability-concentrated groups first, then
sequential MILP overlap groups (<=2 uses per fixture, <=2 shared fixtures per
pair). No added units or score bets; remaining cash held. All k share the same
double-coverage grouping objective, not a separately tuned group selector.

One authoritative implementation: n7_single_plan now requires explicit
single_count, supports0..7; settle_n7_single uses variable group cost and existing
component settlement. next_overlap_group unchanged. Every function is covered in
tests/test_fundamentals_n7_single.py, extended for all counts and invalid inputs.
Old one-count planner/runner/checker bytes are preserved under n7-single-v2/
source-snapshot for archived evidence; no duplicate runtime implementations.

Replay: scripts/run_n7_single.py --parent data/derived/fundamentals_417/decision-chain-conflict-v1
--output NEW_DIR --single-counts 0 1 2 3 4 5 6 7 --single-rule MAX_SINGLE.
All360 plans frozen before settlement. Shared Cutoffs and transitive provenance
are bound; no fits, recency learning, chronology copies or caches. Existing
scipy/numpy/pandas APIs reused, no dependency additions. Model availability remains
historical proxy evidence, not prospective ticket admission.

Independent checker enumerates support, contraction choices, initial ranking,
reuse caps, payouts and cash. k0 reproduces CURRENT and k1 reproduces prior
MAX_SINGLE cash/groups/hits to1e-7. R/QMD65 reports all320 variant issue rows,
eight-count totals and partitions; same reusable R summary. Old QMD64 remains
archived. CI fixture helper is generalized by explicit fixture path, both64 and65
render steps retained. Targeted R and Python checks plus clean real/archive
renders required; full R implementation unchanged from immediately prior passing
suite. Codex review required, remote CI not executed locally.

k1 budget return38.47%, maxDD5,946.77; k2 return39.40%, maxDD3,248.79, but TEST8
falls from44.55% to9.92%. k3 reaches615groups; k4..7 cannot buy more groups and
all have zero winning TEST8 groups. k7 ROI182.35% reflects a tiny stake denominator:
budget return4.08%, only two wins in all40, both validation. No automatic promotion
or posthoc count selection; retain the whole sweep as diagnostic evidence.
