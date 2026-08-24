# Issue 388 — Harden shared cutoff learning after #382 EV

**State:** delivered → PI Review (post-merge EV optional)
**Executor:** analyst · session `20260825_003155_0b8b9f`
**Contract:** #388 — governance/infrastructure correction of #382.

## Scope

All fixes remain inside `src/temporal_learning`, the mapping client, and the
shared governance tooling (`scripts/check_cutoff_governance.py`, CI workflow,
allowlist inventory). No mapping/selector/future client was duplicated;
`#383` remains blocked on this issue; `#210/#218` evidence untouched; the #382
pilot's numeric claim is narrowed to its frozen `kickoff+4h` historical
availability policy (no scientific reinterpretation).

## Required corrections — how each is satisfied

### 1. Target identity exclusion (core)

`Cutoff` now carries a structured `target_identity` (set by
`Cutoff.decision_epoch`). `prepare_learning_context` excludes *every* row of the
target issue after the availability filter, even rows whose timestamp precedes
the decision epoch, and receipts `target_exclusion.{enabled,target_identity,
excluded_rows}`. Ambiguous identity (blank/missing issue codes) fails closed;
a decision-epoch cutoff that cannot prove its target's rows were excluded fails
closed (never admits neighbours).

### 2. Repository-wide enforcement (governance)

`scripts/check_cutoff_governance.py` now scans **both** `src/` and `scripts/`.
Legacy whole-file exemptions were migrated to an occurrence/baseline-bound
inventory (`config/cutoff_governance_legacy_allowlist.json`): each entry binds
the exact function/global occurrence and the file's baseline sha256; new
occurrences in allowlisted files, baseline drift, new hidden globals, and new
detached `mapping_accepted` consumers all fail CI. A mere import of
`prepare_learning_context`/`WalkForwardRunner` no longer authorizes an
unrelated direct `.fit()` anywhere in the file — direct fit is only allowed in
a function that itself calls a shared context API, or an explicit inventory
occurrence. CI workflow sparse checkout now includes the scanned scripts.

### 3. Transitive implementation closure (core + package)

New `src/temporal_learning/closure.py` computes the transitive repo-internal
import closure of decision-facing modules (including contract/constants and
package `__init__`) via AST import resolution. The mapping client binds
`cutoff_mapping.closure` in its implementation hashes, and the package manifest
now records `module:*` closure hashes plus a complete `implementation_closure`
receipt. `verify_manifest` re-derives the same closure; mutation of any
imported blob changes the closure hash → cache key differs and `verify` fails.

### 4. Availability semantics (core + client)

`AvailabilityFilter` declares a policy identity that must start with
`OBSERVED_` or `PROXY_`; `PROXY_*` policies require a preregistered
conservative safe boundary. Receipts bind `availability_policy.identity`,
`proxy_safe_boundary_ts` and `margin_to_cutoff_days` (min/max/median). The
mapping pilot now names its true `PROXY_KICKOFF_PLUS_4H` policy. A
`prospective_capable=True` claim fails closed unless availability is observed
or a strict safe boundary sits strictly before the cutoff.

### 5. Recency blend semantics (core)

`RECENT_STATE_BLEND` (per-row boost) is deleted with no compatibility wrapper.
Replaced by `WeightingPolicy.recent_state_mixture(window, blend)` →
`RECENT_STATE_MIXTURE`, a mathematically explicit convex mixture
`w = (1-α)·u + α·v` over the long-history prior (all rows) and the recent-state
rows, with `α ∈ (0, 0.5]` so the long prior retains at least as much aggregate
mass. The weight receipt binds `declared_recent_blend`, `long/recent_part_mass`
(sum = 1), `normalized_recent_row_aggregate`, `recent/long_rows`, `ess`,
`issue_mass` per issue, and `shrinkage_toward_long_prior`.

## Acceptance — evidence mapping

| Acceptance | Evidence |
|---|---|
| decision-epoch target row cannot enter fit/tune/calibration/final refit | tests `test_target_exclusion_counts_and_partitions`; notebook §1a |
| post-cutoff & same-target mutation invariance | tests `test_post_cutoff_same_target_mutation_invariant`, `test_tamper_future_label_rejected`, `test_replay_matches_original_after_relevant_mutation` |
| scripts/src static bypass probes rejected | notebook §3 probes; tests `test_checker_rejects_*` |
| allowlisted-file new occurrence rejected | probe 2 in checker probe set; `test_checker_rejects_new_occurrence_in_allowlisted_file` |
| unrelated direct fit in shared-importing module rejected | probe 3; `test_checker_rejects_unrelated_fit_in_shared_importing_module` |
| transitive contract-module mutation rejected | `test_contract_module_mutation_changes_closure`; notebook §2 |
| observed/proxy availability explicit and fail-closed for prospective | `test_proxy_requires_safe_boundary`, `test_prospective_fails_closed_with_default_boundary`, `test_prospective_ok_with_strict_boundary`, `test_receipt_binds_policy_and_margin` |
| recency mixture mass/bound/ESS reconciled | `test_recent_mixture_mass_bounded_ess`, `test_old_recent_state_blend_rejected` |
| equivalent cutoffs / cache isolation / replay intact | `test_equivalent_cutoff_same_science_distinct_cache`, `test_cache_key_rejects_poisoned_implementation` |
| mapping + non-mapping clients still share one API | `test_mapping_and_threshold_clients_share_api`; notebook §6 |
| executed notebook/report, source-bound verifier, adversarial tests | this report + `Issue-388-Cutoff-Hardening.ipynb` + `tests/research/test_cutoff_governance_hardening.py` (26 passing) |

REQ-E06 tamper self-tests included: settlement/acceptance field tamper,
weight-ledger row tamper, rewritten manifest, forged source trace / future
label — all asserted to fail closed (`test_tamper_*`).

## Files changed

- `src/temporal_learning/core.py` — target identity, availability policy, mixture
- `src/temporal_learning/closure.py` — new transitive closure hashing
- `src/temporal_learning/__init__.py` — exports
- `src/cutoff_mapping/api.py` — closure binding + explicit proxy policy
- `src/cutoff_mapping/package.py` — manifest uses closure + `verify_manifest`
- `scripts/check_cutoff_governance.py` — src+scripts scan, occurrence inventory
- `config/cutoff_governance_legacy_allowlist.json` — occurrence/baseline-bound
- `.github/workflows/cutoff-governance.yml` — sparse checkout covers scripts
- `docs/research/temporal-function-inventory.csv` — new rows
- `notebooks/research/cutoff-learning/Issue-388-Cutoff-Hardening.ipynb` — executed evidence
- `tests/research/test_cutoff_governance_hardening.py` — 26 adversarial/golden tests

## Verification commands

```bash
python scripts/check_cutoff_governance.py          # expects PASS
python -m pytest tests/research/test_cutoff_governance_hardening.py -q  # 26 passed
```

## Known risks / notes

- The `#382` equal-weight historical mapping pilot remains numerically valid
  at its merged SHA; its claim is narrowed to the frozen `kickoff+4h`
  historical availability policy (per contract evidence boundary).
- `AGENTS.md` remains PI-owned; owner-mandated governance prose was not
  edited by this delivery (the checker + CI enforce the rule mechanically).
- `prospective_capable=True` is intentionally conservative: a proxy policy
  whose safe boundary merely equals the cutoff cannot claim prospective
  readiness.