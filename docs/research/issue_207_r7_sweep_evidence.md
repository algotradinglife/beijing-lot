# Issue #207 R7 — Same-Category Sweep Evidence (EV R6 REJECT closure)

Audited SHA (R6 REJECT): `6b82aa757527e8efb9398e1822d45d073dbdf4f6`
Rework: R7 fresh mode, `REWORK_TYPE=method`.

EV R6 blocking defects and their root-cause categories:

| EV defect | Root-cause category | Public call point |
|---|---|---|
| `labels_available.astype(bool)` accepts NaN/"False"; `realized_gross` unvalidated; negative payout enters replay | 验证盲区 / settlement domain | `_validate_candidates` + `replay_path` |
| Seven-cell source trace validates shape only, not per-cell identity/outcome consistency | schema/trace relationship | `_validate_candidates` trace loop |
| `JSONDecodeError` from `source_cells_json` not mapped to `Stage4Error` | 异常归一化 | `_validate_candidates` + `_trace_frame` |

## 1. 验证盲区 — nullable boolean domain (full sweep)

All `astype(bool)` / boolean-coercion call points in the Stage-4 module:

| Call point (R6 line → R7 line) | Input origin | Verdict |
|---|---|---|
| `_validate_candidates` labels check (`:284-286` → `:319-327`) | **public #206 input** | FIXED: `_coerce_nullable_boolean` rejects strings/out-of-domain; NaN rejected; historical must be `True`, LOCKED must not be `True` |
| `replay_path` labels check (`:499` → `:563`) | public requests frame | FIXED: same nullable-boolean coercion, every funded issue must be `True` |
| `verify` `research_only` / `promoted` / `labels_used_for_identity` (`:1800-1803`) | producer-written bool columns (reconstruct) | SAFE: values are bool constants written by `reconstruct_active_requests`; semantic replay compares the full frame and rejects tamper |
| `_path_metrics` `window_loss.astype(bool).mean()` (`:854`) | internal computed column (`window_return < 0`) | SAFE: not a public input; derived inside the module |
| `_decision` / `_matched_comparisons` `terminal_evidentiary.astype(bool)` (`:1228,:1468,:1864-1865`) | internal computed column | SAFE: derived, not parsed from input |
| `verify` `equal_capital_schedule.astype(bool)` (`:1809`) | producer CSV column compared semantically | SAFE: semantic replay compares full frame |

Conclusion: every public-input nullable boolean is now domain-validated; remaining
`astype(bool)` uses are internal derived columns whose values the producer owns
and which the semantic verifier replays.

## 2. settlement domain — payout / gross multiple (full sweep)

All `realized_gross` / gross-multiple / payout call points:

| Call point | Role | Verdict |
|---|---|---|
| `_validate_candidates` required cols (`:269`) | public input schema | unchanged (column presence) |
| **`_validate_settlement_domain` (new `:243-259`)** | public input domain | FIXED: settled rows finite + non-negative `realized_gross`; unavailable-label rows must be NaN; numeric coercion errors normalized to `Stage4Error` |
| `reconstruct_active_requests` (`:345-346`) | propagates `realized_gross` → multiples | SAFE after upstream validation (runs after `_validate_candidates` in `run()`/`verify()`) |
| `replay_path` payout calc (`:519-524` → `:584-589`) | settlement execution | FIXED: negative payout (pre-tax or tax-adjusted) rejected with `Stage4Error("negative payout")` |
| `replay_path` ledger rows `gross_payout_yuan` / `tax_adjusted_reference_payout_yuan` / `net_pnl_yuan` (`:572-574`) | derived outputs | SAFE: derived from validated payout |
| `_matched_reference` / `_matched_comparisons` `candidate/comparator_gross_payout_yuan` (`:1083-1096`) | matched comparison | SAFE: derived from already-validated ledger |
| `_schema_catalog` `realized_gross` unit (`:1393`) | schema declaration | unchanged (already `gross_return_multiple`) |

Conclusion: no negative or non-finite gross/payout can enter the evidence chain:
input domain is validated before reconstruction, replay rejects negative payout
fail-fast, and the semantic verifier replays both.

## 3. schema/trace relationship — seven-cell source trace (full sweep)

| Call point | Role | Verdict |
|---|---|---|
| `_validate_candidates` trace loop (`:290-315` → `:332-380`) | public input structural + semantic | FIXED: per-cell checks now enforce `cell.match_idx == match_indices[i]`, `cell.outcome == outcomes[i]`, and `ticket_identity[i] == f"{match}:{outcome}"`; identity ordering enforced by index alignment; duplicated match rejected both by `len(set(matches)) != N` and per-cell match_idx equality |
| `_trace_frame` decision_trace_json (`:684`) | internal derived JSON | FIXED (同类别): `JSONDecodeError` → `Stage4Error` |
| `verify` JSON reads (provenance/decision/SHA256SUMS) | internal artifacts | SAFE: manifest hash verified first; a malformed internal JSON fails the manifest check before parse |

## 4. 异常归一化 — JSON parser (full sweep)

| Call point | Verdict |
|---|---|
| `_validate_candidates` `json.loads(source_cells_json)` | FIXED: `JSONDecodeError` → `Stage4Error("malformed source_cells_json")` |
| `_trace_frame` `json.loads(decision_trace_json)` | FIXED: `JSONDecodeError` → `Stage4Error("malformed decision_trace_json")` |
| `_notebook_contract_digest` notebook JSON (`:108`) | dev-environment artifact; raising is correct fail-closed behaviour, not a settlement-input path |

## 5. Executable tests added (R7)

All in `tests/test_bj207_bankroll.py`, all fail closed with explicit `Stage4Error`:

- `test_candidate_validation_rejects_non_nullable_boolean_availability` — NaN / "False" / "True" / "false" / 2 / 0.5 / "yes"
- `test_candidate_validation_rejects_invalid_realized_gross` — NaN / +Inf / -Inf / -1.0 / -0.001
- `test_candidate_validation_rejects_settlement_gross_on_unavailable_labels`
- `test_candidate_validation_rejects_ev_probe_all_cv2023_unavailable_negative_gross` — EV R6 probe regression
- `test_candidate_validation_rejects_per_cell_source_trace_inconsistency` — match_idx mismatch / outcome tamper / duplicated match / identity mismatch (4 param cases)
- `test_candidate_validation_rejects_malformed_source_cells_json`
- `test_replay_rejects_negative_payout_from_negative_gross`
- `test_semantic_verifier_rejects_remanifested_nullable_boolean_and_negative_gross` — verifier mutation: NaN label + negative gross, per-cell trace tamper, malformed JSON, each re-manifested → semantic REJECT

## 6. Verifier mutation proof

The verifier calls `_validate_candidates` on the frozen #206 source and replays
`reconstruct_active_requests` + `replay_path` from it; tampered settlement or
trace fields in the committed `active_research_ticket_requests.parquet` therefore
diverge from the replayed frame and are rejected by `_assert_semantic_frame`,
and tampered source candidates are rejected by the new domain validators before
any replay starts. Invalid settlement can no longer produce a negative payout or
`ENGINE_VALID` evidence.
