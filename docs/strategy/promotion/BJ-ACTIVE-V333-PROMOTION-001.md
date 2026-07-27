# BJ-ACTIVE-V333-PROMOTION-001 — promotion card

Status: `revision_for_pi_review_before_code`

## Scope and dependency receipt

This is a technical-contract migration only. `active_v3.3.3` remains the one
formal default; its model, probability, q/EV calculation, selection,
protection/stop, Exact-N, budget, concentration, staking, and ticket rules do
not change.

The branch is rebased on `origin/main` commit
`68891253549c721de80809717006212dc5e027c6` (PR #55 merge). That commit is an
ancestor of this card revision. The implementation branch must remain based on
that commit or a later `main` commit.

The only proposed native contract names are:

| Contract field | Existing formal value | Native value after cutover |
| --- | --- | --- |
| `decision_variants[active_v3.3.3].kind` | `shadow` | `active` |
| `decision_variants[active_v3.3.3].source` | `structured_shadow_csv` | `structured_active_csv` |
| `decision_variants[active_v3.3.3].artifact_key` | `structured_shadow_dir` | `structured_active_dir` |
| release artifact root | `results/structured_decision_chain_shadow` | `results/structured_decision_chain_active` |
| issue CSV | `structured_shadow_{issue}.csv` | `structured_active_{issue}.csv` |
| executable selection column | `shadow_selection_codes` | `selection_codes` |
| issue receipt | `structured_decision_input_receipt_v1` | `structured_decision_input_receipt_v1` |
| formal-binding schema | `adhoc_formal_selection_binding_v1` (legacy only) | `adhoc_formal_selection_binding_v2` |

`shadow_v3.3.3` becomes a read-only audit alias of `active_v3.3.3`; it is not a
variant which can generate, sign, or publish an operational package.
`active_v3` remains retired, non-selectable, and never a resolver fallback.
Both v4.2 shadow/manual variants retain their existing `structured_shadow_csv`
contract unchanged.

## Frozen zero-difference baseline

The before-code comparison baseline is the completed formal snapshot below.
It is a fixed historical artifact, not an authority to backfill, re-publish, or
re-sign anything.

| Item | Frozen value |
| --- | --- |
| Issue / generation window | `26078` / `2026-07-26T16:37:35.691221+00:00` (receipt clock) |
| Formal CSV | `results/structured_decision_chain_shadow/26078_20260726_active_v3.3.3/structured_shadow_26078.csv` |
| Formal CSV SHA-256 / bytes | `4adf064b950901e70906c0db000d41f28c7cfd6b183e8e7d334436ebc82d6a4f` / `615643` |
| Receipt path / file SHA-256 | `results/structured_decision_chain_shadow/26078_20260726_active_v3.3.3/structured_shadow_26078.input_receipt.json` / `2bf4c49fc0410f03d2922142321f6c7b93e7ab2e6429edfe83fa573ab58c411c` |
| Receipt schema / semantic SHA-256 | `structured_decision_input_receipt_v1` / `6e879ee749903770e159b1f1d0624ee9b596aa2e2345113f5ed9cb1c572b6468` |
| Expected / actual row count | `173` / `173` (complete `match_idx` 1–173) |
| Canonical map digest | `e72f7b4a0a6b8038fcacf7b74716a0c891335456c75e7ffe54337950f37eac4e` |
| Semantic ticket-input fixture digest | `d9add04900e8fe9c7d636b9e60f8e3dde506eb765cc5fd3a768886cf81febed4` |
| Committed projection fixture | `tests/fixtures/promotion/active_v333_26078_shadow_selection_projection.csv` / SHA-256 `8c726a5fea280e3b4770360479b90a99d27a135592e9d2884c8f8e7f8ce90d22` |
| Committed provenance receipt | `tests/fixtures/promotion/active_v333_26078_shadow_selection_projection.receipt.json` / file SHA-256 `896943524e0227c8f13b3f55f8e1a24fe735ba8cffaa7c3c97d915a8b74d7092` / semantic SHA-256 `3325d1f6eea44047f7268bd2305e0c2bafd92292f214bf4c9fb89d7c37bf38e7` |

The canonical map is UTF-8 SHA-256 of compact sorted-key JSON, with rows
ordered by `match_idx`, each row exactly
`{"match_idx": <int>, "selection_codes": [<ordered codes>]}`. The semantic
ticket-input fixture wraps that exact map as
`{"schema_version":"active_v333_selection_parity_fixture_v1","issue":"26078","rows":<canonical map>}`.
It freezes the ticket semantics which this migration may consume, without
claiming a historical package was operationally publishable. The native
conversion test must generate the native CSV from these bytes and prove:

1. the native `selection_codes` map has the listed canonical digest;
2. exactly 173 indices occur once and only once;
3. the row-by-row old `shadow_selection_codes` and new `selection_codes` are
   equal; and
4. the native ticket-input fixture digest equals the listed value before any
   ticket packaging is attempted.

This baseline intentionally uses the formal `shadow_selection_codes` field
bound to public variant `active_v3.3.3`. It does not use the CSV's
`active_selection_codes`: that column belongs to retired `active_v3` and has
26 differences on this snapshot (its map digest is
`7257dc324e31cd8963fb2818cbf54b461d7147d56af18b2b2026e8777b8d6ac3`).
Treating that retired column as a parity source would violate the no-fallback
contract rather than prove this promotion.

The committed projection fixture is the complete ordered 173-row extraction,
not a runtime-only path. Its provenance receipt binds the issue, generation
clock, original CSV and receipt paths, their file/semantic hashes, projection
file hash, row count, canonical map digest, and semantic ticket-input digest.
An independent exact-HEAD checkout reproduces all claims with:

```bash
uv run pytest tests/test_active_v333_promotion_fixture.py
```

`structured_decision_input_receipt_v1` is retained only as a source-contract-
neutral byte/issue/clock receipt: its validator checks receipt schema, issue,
CSV name, CSV bytes/size and a timezone-aware generation clock, but does not
encode a root, arm, or selection-column meaning. The new v2 formal binding,
not this generic receipt, owns those native semantic checks.

Any mismatch is `PARITY_MISMATCH` and blocks cutover; no alternate strategy or
legacy artifact may be substituted.

## Formal-binding version boundary

`adhoc_formal_selection_binding_v1` is explicitly a legacy shadow binding. It
continues to verify immutable audit material only and can never produce a new
`READY_FOR_REVIEW` package after this promotion.

`adhoc_formal_selection_binding_v2` is the sole native operational binding. It
requires all of the following together: `decision_variant_id=active_v3.3.3`,
an active arm (not `shadow_arm`), a path beneath
`results/structured_decision_chain_active`, a valid
`structured_decision_input_receipt_v1` for that native CSV, exactly one row per
`match_idx`, and the `selection_codes` column whose canonical digest binds the
decision input. A v2 binding pointing to a shadow root or
`shadow_selection_codes`, and a v1 binding presented as native, are both
rejected before package generation. There is no automatic v1-to-v2 conversion
at verification time.

The implementation test set must cover all downgrade and cross-version cases:
v1 cannot obtain `READY_FOR_REVIEW`; v2 cannot use a shadow root, shadow
column, or shadow arm; v1 and v2 digest/receipt substitutions fail; and a v2
native decision input cannot be verified with a legacy attestation. These are
in addition to the fixed projection test above.

## Publication-attestation transition

Operational package publication remains governed by the PR #55 attestation
contract; this promotion does not weaken it.

| Requirement | Exact transition rule |
| --- | --- |
| Attestation schema | The signed wrapper remains `adhoc_publication_attestation_v1`; a native package requires `adhoc_formal_selection_binding_v2`, while v1 is legacy audit-only. |
| Signed statement | The canonical Ed25519 statement includes `formal_binding_schema_version=adhoc_formal_selection_binding_v2`, `unsigned_package_content_sha256`, issue/request/validity fields, package schema and `decision_variant_id`, native formal CSV SHA-256, native receipt SHA-256, canonical `formal_selection_codes_sha256`, decision-input, Exact-N and concentration SHA-256 values, plus `artifact_digest_set_sha256`. |
| Native formal mapping | An attested `READY_FOR_REVIEW` package must bind `formal_binding_schema_version=adhoc_formal_selection_binding_v2`, `decision_variant_id=active_v3.3.3`, active arm semantics, `formal_selection_column=selection_codes`, the native CSV/receipt paths and hashes, and the canonical selection digest. A legacy binding, column, arm or root fails closed. |
| Pinned public key | Verification uses version-controlled `config/adhoc_publication_keys.json`, schema `adhoc_publication_key_registry_v1`; only an `active` key whose `usage` matches its registry environment is valid. |
| Private-key authority | Only the Decision API identity receives `BEIDAN_ADHOC_PUBLICATION_PRIVATE_KEY_FILE` and `BEIDAN_ADHOC_PUBLICATION_KEY_ID`, with a read-only PKCS#8 Ed25519 PEM mount. It alone may write the operational package root. |
| Manual/runtime callers | A caller without that authority may create only an `UNATTESTED_AUDIT_ONLY` record in its audit root. It cannot be current, downloadable as operational, or later promoted by attaching a signature. |
| Legacy data | `results/structured_decision_chain_shadow/**`, its receipts, and legacy attestations are audit-only byte-immutable inputs. They are never re-signed, copied into a new operational package as a native artifact, or newly publishable. |
| Failure behavior | Missing/unreadable key, unknown/retired/revoked key, schema mismatch, invalid signature, statement mismatch, native receipt/hash mismatch, or formal-map mismatch returns an unavailable error before operational generation; there is no `active_v3`, shadow, or manual fallback. |

## Consumer cutover matrix

`compatibility` below is deliberately read-only: no old path is a new write or
publication target.

| Consumer | Old read / write | Native read / write | Compatibility | Cutover state | Required test or receipt |
| --- | --- | --- | --- | --- | --- |
| Registry / release resolver | `strategy_release.json`: `kind=shadow`, `source=structured_shadow_csv`, `artifact_key=structured_shadow_dir` / no artifact write | `kind=active`, `source=structured_active_csv`, `artifact_key=structured_active_dir` / no artifact write | Parse `legacy_aliases=["shadow_v3.3.3"]` only for audit lookup | atomic registry release change; no generic fallback | registry schema test; `active_v3` non-fallback assertion |
| Artifact writer | shadow root and `structured_shadow_{issue}.csv` / writes shadow CSV + `structured_decision_input_receipt_v1` | `results/structured_decision_chain_active/{issue}_{generation}_active_v3.3.3/structured_active_{issue}.csv` / writes native CSV + same receipt schema | writer never writes old root after cutover | new native artifact is fully verified before pointer change | fixed 26078 CSV/hash/receipt/map parity receipt |
| Shared resolver | shadow candidate scan and `shadow_selection_codes` / none | one resolver reads `structured_active_dir`, validates receipt, uniqueness and `selection_codes` / none | legacy reader is separate audit-only function, not resolver fallback | all operational consumers call this resolver | missing, duplicate, wrong issue, bad receipt and legacy-fallback tests |
| Decision API | registry-selected shadow CSV / no direct CSV write | shared native resolver / no direct CSV write | may display legacy provenance only via audit endpoint | API package endpoint changes with resolver | API current-default + fail-closed response tests |
| Adhoc builder / verifier | v1 formal root `results/structured_decision_chain_shadow`, `shadow_arm`, `shadow_selection_codes` / audit package only | v2 native root, active arm and `selection_codes` / Decision API-only attested package write | v1 remains verifier-readable only as audit material | v2 native binding required for `READY_FOR_REVIEW` | v1 downgrade, v2-on-shadow root/column/arm, source-root escape, receipt/hash and parity tests |
| N-ticket | shadow-derived decision input / no formal artifact write | shared native resolved decision input / no formal artifact write | no legacy operational N-ticket build | resolver cutover | exact-N input map digest parity test |
| PDF / CSV | shadow-labelled source provenance / package files written only after existing checks | native `decision_variant_id`, formal hashes and `selection_codes` provenance / package files written only after native attestation | existing legacy files immutable/read-only | native package generation only | ticket-input fixture + PDF/CSV manifest digest receipt |
| Segment betting | shadow-derived rows / no formal artifact write | shared native resolved rows / no formal artifact write | audit display may name legacy source but cannot choose it | resolver cutover | segment selection parity and unavailable-on-resolver-failure test |
| Postmatch | shadow artifact correlation / no rewrite | native artifact correlation / no rewrite | legacy historical reports remain read-only | native correlation for new records only | native/legacy provenance-separation test |
| Dashboard / UI | displays active formal variant through shadow vocabulary / no write | displays `active_v3.3.3` as native active / no write | legacy alias labelled audit-only and nonselectable | after API resolver cutover | UI/API payload test: no selectable `shadow_v3.3.3`; v4.2 unchanged |
| Publication attestation | signs formal shadow hashes for existing permitted packages / Decision API-only write | signs native formal CSV, receipt and selection-map hashes / Decision API-only write | no re-signing legacy artifact/package | native binding gates `READY_FOR_REVIEW` | valid signature and every listed failure-mode test |
| Legacy audit reader | reads shadow CSV/receipt / never writes | does not read native as legacy / never writes | explicit `UNATTESTED_AUDIT_ONLY`/audit presentation only | permanently retained | alias cannot generate/publish package test |

## Executable cutover and rollback card

1. Stage and independently verify a native artifact under
   `structured_active_dir`, with receipt schema
   `structured_decision_input_receipt_v1`, a valid v2 native formal-binding
   record, and the frozen parity receipt above. The staged artifact is not
   operational until the registry changes.
2. Deploy the shared resolver and its fail-closed tests first. It must have no
   legacy-resolution branch for operational calls.
3. Create a `native_promotion_cutover_receipt_v1` before changing the
   registry. Its required immutable fields are `issue`, `native_csv_path`,
   `native_csv_sha256`, `native_receipt_sha256`,
   `formal_selection_codes_sha256`, `native_artifact_identity`,
   `previous_native_artifact_identity`, `attestation_key_id`, and
   `attestation_sha256`. `native_artifact_identity` is exactly
   `active_v3.3.3:{issue}:{native_csv_sha256}`; empty
   `previous_native_artifact_identity` means rollback is unavailable and must
   fail closed.
4. Change the registry’s `active_v3.3.3` `kind`, `source`, and `artifact_key`
   as one reviewed release-config transition, naming that cutover receipt.
   This is the sole cutover switch.
5. Enable attested operational publication only when the native binding and
   Ed25519 verification both pass. A staged native artifact with no active key
   remains `UNATTESTED_AUDIT_ONLY`.

The rollback target is the immediately preceding **verified native** artifact
under the same `structured_active_dir` and receipt schema, identified by its
immutable CSV SHA-256, receipt SHA-256, canonical map digest, and active-key
attestation, encoded in
`native_promotion_cutover_receipt_v1.previous_native_artifact_identity`. The
deploy receipt must name this exact target before cutover. If there is no such
verified native predecessor, rollback is an abort to fail-closed
unavailability—not a switch to a shadow artifact. A rollback changes only the
reviewed native artifact pointer and re-verifies the complete native receipt
and signature.

Triggers are a post-cutover receipt/hash/map mismatch, signature/key failure,
missing/duplicate/wrong-issue rows, parity failure, or operational consumer
not using the shared resolver. Rollback must never enable `active_v3`, make an
arbitrary `shadow_v3.3.3` artifact publishable, mutate history, or re-sign any
legacy bytes.

## Evidence required before merge

1. frozen 26078 row-by-row zero-difference receipt and semantic ticket-input
   fixture parity;
2. native artifact hash/receipt, complete issue membership and unique-index
   receipt;
3. valid native Ed25519 publication attestation that binds v2, plus
   missing-key, invalid-key, invalid-signature, statement-mismatch, downgrade
   and cross-version-substitution fail-closed tests;
4. legacy alias read-only/non-publishable test, `active_v3` non-fallback test,
   and unchanged v4.2 shadow/manual test;
5. exact-HEAD independent Engineering Validation and PI review.
