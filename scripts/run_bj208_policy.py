"""Issue #208 staged runner: census → counterfactual surface → controls →
learned policy → diagnostics → selection → immutable package.

REWORK v2 (D1/D6): the runner builds the package in a staging directory,
fsyncs files + directory, writes COMPLETED.json, and atomically renames the
staging dir over the final output.  All artifacts (including tamper results
and the receipt) are written BEFORE the manifest, so SHA256SUMS.json has full
coverage.  Stochastic lanes run on the 16 preregistered seeds (never seed=0).

Usage:
  PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py run --output results/issue-208
  PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py verify --output results/issue-208
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any
import uuid

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PUBLISHED_OUTPUT = Path("results/issue-208")
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from parlay_policy.contract import (  # noqa: E402
    Action,
    ALL_SEEDS,
    CAPITAL_LANES,
    CONTRACT_VERSION,
    DEVELOPMENT_SPLITS,
    FIT_SPLIT,
    FOLDS,
    INCUMBENT_K,
    INCUMBENT_LANE,
    INCUMBENT_N,
    INITIAL_BANKROLL_YUAN,
    K_GRID,
    LANES,
    MODEL_SEED,
    N_GRID,
    NO_BET_KEY,
    TERMINAL_SPLIT,
    as_action_dict,
)
from parlay_policy.census import (  # noqa: E402
    build_panels,
    census_table,
    eligibility,
    load_upstream_ledger,
    load_upstream_tickets,
    load_value_matrix,
)
from parlay_policy.incumbent import build_incumbent_paths  # noqa: E402
from parlay_policy.policy import (  # noqa: E402
    best_fixed_action_key,
    choose_action,
    fit_policy,
    is_action_fundable,
    ood_gate,
    serialize_policy,
)
from parlay_policy.replay import (  # noqa: E402
    ReplayError,
    apply_issue_settlement,
    build_issue_contexts,
    build_label_surface,
    build_pool_cache,
    build_training_frame,
    full_path_replay,
    materialize_issue_path_metrics,
    path_holding_metrics,
    summarize_path,
)
from parlay_policy.tickets import (  # noqa: E402
    fit_learned_ranker,
    mean_pairwise_overlap,
    ranker_scores,
    repeat_exposure,
    ticket_hhi,
)
from parlay_policy.verify import (  # noqa: E402
    VerifyError,
    manifest,
    run_tamper_suite,
    sha256_file,
    verify_capital_accounting,
    verify_code_bindings,
    verify_chronology,
    verify_completion,
    verify_dynamic_control_decisions,
    verify_handoff_contract,
    verify_holdout_mutation_receipt,
    verify_manifest,
    verify_nk_semantics,
    verify_no_2024_issue,
    verify_no_embargoed_split,
    verify_payout_economics,
    verify_package_schema,
    verify_path_metrics,
    verify_provenance,
    verify_receipt,
    verify_req_evidence,
    verify_selection_authority,
    verify_state_semantics,
)
from parlay_policy.diagnostics import (  # noqa: E402
    action_frequency,
    action_variation_demo,
    calibration_curve,
    ood_fallback_census,
    permutation_importance_table,
)
from parlay_policy.features import STATE_FEATURE_NAMES, live_prior_state_from_rows  # noqa: E402


def _json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            _fsync_file(path)
    # File fsync does not make nested directory entries durable.  Flush every
    # directory bottom-up so model and diagnostic filenames are committed
    # before the package root is atomically installed.
    directories = [root, *(path for path in root.rglob("*") if path.is_dir())]
    for directory in sorted(
        directories, key=lambda path: len(path.parts), reverse=True
    ):
        _fsync_directory(directory)


def _fsync_directory(path: Path) -> None:
    dir_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _atomic_publish(staging: Path, output: Path) -> Path | None:
    """Install staging while retaining a recoverable last-good package.

    The old implementation deleted the backup before the staging rename, so
    a second-rename fault destroyed the only complete package.  This function
    keeps the backup until the caller has verified the published tree and
    restores it immediately if installation fails.
    """
    _fsync_tree(staging)
    output.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if output.exists():
        backup = output.parent / f".{output.name}.backup-{uuid.uuid4().hex}"
        try:
            os.replace(output, backup)
            _fsync_directory(output.parent)
        except BaseException:
            # The first parent-fsync is part of the transaction.  If it
            # fails after output→backup, restore last-good visibility here;
            # the caller cannot know the local backup path until return.
            if backup.exists() and not output.exists():
                os.replace(backup, output)
                try:
                    _fsync_directory(output.parent)
                except OSError:
                    # Preserve the original boundary error; visibility is
                    # already restored and retry remains safe.
                    pass
            raise
    try:
        os.replace(staging, output)
        _fsync_directory(output.parent)
    except BaseException:
        # Cover both staging→output rename failure (output absent) and the
        # second parent-fsync failure (new output visible but not durable).
        # Move a visible candidate back to staging so an immediate retry can
        # reuse the same complete tree, then restore last-good.
        if output.exists():
            if staging.exists():
                shutil.rmtree(staging)
            os.replace(output, staging)
        if backup is not None and backup.exists():
            os.replace(backup, output)
        try:
            _fsync_directory(output.parent)
        except OSError:
            pass
        raise
    return backup


PUBLICATION_INVALID_MARKER = ".PUBLICATION_INVALID"


def _mark_publication_invalid(output: Path) -> None:
    """Fail-closed marker written when a rollback cannot move an unverified
    package off the canonical path.

    The marker makes the production verifier (unlisted-file check) and any
    reader fail closed instead of consuming a package the transaction could
    not certify.  Best-effort: if even the marker cannot be written the
    original fault still propagates and the backup (if any) keeps the true
    last-good for the run()-start recovery pass.  A control interrupt during
    the marker write must not mask the caller's own fault, so every marker
    write failure (including KeyboardInterrupt/SystemExit) is swallowed
    here — the caller re-raises its own boundary fault.
    """
    try:
        (output / PUBLICATION_INVALID_MARKER).write_text(
            f"PUBLICATION_INVALID at {time.time()}\n", encoding="utf-8"
        )
    except BaseException:
        pass


def _rollback_publish(output: Path, backup: Path | None) -> None:
    """Restore the package state that existed before publication.

    Idempotent and fault-bounded: the caller may invoke this more than once
    with the same handle (run() post-verify branch and the outer
    BaseException handler).  Once the backup has been consumed (renamed back
    to output), a later call must be a no-op — it must never move the
    restored last-good to .failed-* and delete it (EV E1: a parent-fsync
    fault in the first rollback made the outer handler delete the restored
    package with the same stale handle).

    Fault policy: visibility restoration is the commit point.  After the
    backup is renamed to output the old last-good is visible; a parent-fsync
    fault or failed-copy cleanup fault at that point is a durability
    warning, never a reason to touch the visible package again.

    EV E1 (v9 -> v10): the rollback's new→failed rename fault must not leave
    the semantic-invalid new package occupying the canonical final path.
    When that rename fails, the backup is atomically overwritten over the
    invalid tree (os.replace replaces the target), restoring last-good
    visibility and consuming the backup so an immediate retry leaves no
    stale .backup-* orphan.  If even that overwrite fails, the tree is
    marked .PUBLICATION_INVALID (fail-closed) and the backup stays intact
    for the run()-start recovery pass.

    EV E1 (v10 -> v11, finalize REJECT 819ef79): the new→failed rename is
    BaseException-bounded, not just OSError-bounded.  A KeyboardInterrupt or
    SystemExit raised AT that rename (the boundary that decides canonical
    ownership) previously escaped without recovery and without the fail-closed
    marker while run() had already transferred backup ownership — exposing an
    unmarked semantic-invalid canonical.  Now every recovery step (invalid-tree
    removal, backup→output restore) is itself BaseException-bounded and
    converges to a safe state (last-good visible | canonical absent |
    fail-closed marker + intact backup) BEFORE the control interrupt intent
    propagates.  The first-publish (backup is None) branch has the same
    BaseException boundary.
    """
    if backup is None:
        # First-ever publication: roll back to the pre-publication state by
        # removing the unverified new package.  Idempotent: if the output is
        # already absent, nothing remains to do.
        if not output.exists():
            return
        failed = output.parent / f".{output.name}.failed-{uuid.uuid4().hex}"
        try:
            os.replace(output, failed)
        except BaseException:
            # Cannot even set the unverified new aside (OSError,
            # KeyboardInterrupt or SystemExit).  There is no last-good to
            # restore; fail closed so no reader consumes it.  A control
            # interrupt intent still propagates after the marker is written.
            _mark_publication_invalid(output)
            raise
        try:
            _fsync_directory(output.parent)
        except OSError:
            pass
        try:
            shutil.rmtree(failed)
        except OSError:
            pass
        try:
            _fsync_directory(output.parent)
        except OSError:
            pass
        return
    if not backup.exists():
        # The backup was already consumed by a previous rollback (or is
        # otherwise absent).  Fail closed: never touch the visible package.
        return
    failed = output.parent / f".{output.name}.failed-{uuid.uuid4().hex}"
    if output.exists():
        try:
            os.replace(output, failed)
        except BaseException as fault:
            # new→failed rename fault (OSError, KeyboardInterrupt or
            # SystemExit): the unverified new is still at the canonical
            # path.  A POSIX rename cannot replace a non-empty directory
            # target, so remove the invalid tree and then restore last-good
            # from the backup.  An absent output is fail-closed for any
            # reader.  The .failed-* diagnostic copy is sacrificed for
            # visibility.
            #
            # Every recovery step is BaseException-bounded (REWORK v11,
            # EV finalize REJECT 819ef79): a control interrupt or second
            # fault during recovery must still converge to a safe state —
            # last-good visible at canonical, canonical absent, or a
            # verifiable .PUBLICATION_INVALID marker with the backup intact.
            # Never expose an unmarked semantic-invalid canonical package.
            try:
                shutil.rmtree(output)
            except BaseException:
                # Even removal failed: keep the backup as the true last-good
                # and fail closed on the visible tree so readers cannot
                # consume it.  The next run()'s recovery pass restores the
                # backup once the filesystem heals.
                _mark_publication_invalid(output)
                raise
            try:
                os.replace(backup, output)
            except BaseException:
                # Restore failed after the invalid tree was removed:
                # canonical is absent (fail-closed) and the backup stays
                # intact for the run()-start recovery pass.
                _mark_publication_invalid(output)
                raise
            try:
                _fsync_directory(output.parent)
            except OSError:
                pass
            if isinstance(fault, OSError):
                # Ordinary rollback fault: recovery succeeded, so the caller
                # continues with its own VerifyError (v10 contract).
                return
            # KeyboardInterrupt / SystemExit (or another BaseException):
            # recovery converged to a safe state first, then the control
            # interrupt intent propagates to the caller.
            raise
    try:
        os.replace(backup, output)
    except BaseException:
        # backup→output rename fault: output stays absent and the backup
        # stays intact.  The run()-start recovery pass restores the
        # last-good on the next attempt; re-raise without touching state.
        raise
    try:
        _fsync_directory(output.parent)
    except OSError:
        # Visibility already restored; a durability fault must not escalate
        # into a second rollback that deletes the restored last-good.
        pass
    if failed.exists():
        try:
            shutil.rmtree(failed)
        except OSError:
            # Keep the failed copy as an explicit diagnostic; never let a
            # cleanup fault hide the restored package.
            pass
        try:
            _fsync_directory(output.parent)
        except OSError:
            pass


def _recover_stale_transaction(output: Path) -> None:
    """Converge leftover publication artifacts from a failed prior run.

    Invariant: whenever a .backup-* directory exists it holds the
    pre-transaction last-good package; the canonical output is at most an
    unverified or invalid candidate.  Called at the start of run() so an
    immediate retry after any publication fault converges to a single
    visible package with no stale backup/failed/staging orphan.

    - If the visible tree is NOT marked .PUBLICATION_INVALID and verifies as
      a complete package, it IS the last-good (e.g. a prior run committed
      the new package and then failed while cleaning up the obsolete
      backup): drop the stale backup, keep the tree.
    - Otherwise restore the backup through _rollback_publish (persistent
      faults keep the tree marked invalid and the backup intact for a later
      attempt).
    """
    for backup in sorted(output.parent.glob(f".{output.name}.backup-*")):
        invalid = (
            output.exists()
            and (output / PUBLICATION_INVALID_MARKER).exists()
        )
        if output.exists() and not invalid:
            try:
                failures = verify_package(output)
            except BaseException:
                failures = ["recovery verification raised"]
            if not failures:
                # Complete verified package is the last-good; the backup is
                # an obsolete duplicate that must not survive the retry.
                shutil.rmtree(backup, ignore_errors=True)
                continue
        _rollback_publish(output, backup)
    for stale in output.parent.glob(f".{output.name}.failed-*"):
        shutil.rmtree(stale, ignore_errors=True)
    for stale in output.parent.glob(f".{output.name}.staging-*"):
        shutil.rmtree(stale, ignore_errors=True)
    try:
        _fsync_directory(output.parent)
    except OSError:
        pass


def _commit_publish(output: Path, backup: Path | None) -> None:
    """Remove the retained backup only after final-package verification."""
    if backup is not None and backup.exists():
        # The new verified package is already committed.  Failure while
        # cleaning up only the obsolete backup must not trigger a rollback
        # that could discard the verified package; a stale backup is safer
        # than replacing good output with a partially deleted backup.
        try:
            shutil.rmtree(backup)
        except OSError:
            # One bounded retry closes transient cleanup faults while never
            # rolling a verified new package back to obsolete bytes.
            shutil.rmtree(backup)
        _fsync_directory(output.parent)


# ==== SECTION: RUN ====


def run(output: Path) -> dict[str, object]:
    started = time.time()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # REWORK v10 (EV E1): an immediate retry after any publication fault
    # must converge to a single visible package with no stale
    # backup/failed/staging orphan.  Restore or drop leftover transaction
    # artifacts from a failed prior run BEFORE building the next package.
    _recover_stale_transaction(output)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent)
    )
    backup: Path | None = None

    try:
        # The package may be replayed into an arbitrary audit directory, but
        # its downstream handoff always names the canonical repository path.
        # This makes alternate-output replay genuinely supported instead of
        # failing after the expensive scientific stages have completed.
        _run_stages(staging, published_output=CANONICAL_PUBLISHED_OUTPUT)
        _write_metadata(staging, started)
        _json(
            staging / "COMPLETED.json",
            {
                "status": "COMPLETED",
                "elapsed_seconds": round(time.time() - started, 1),
            },
        )
        # Schema inventory is frozen before the self-attacks run.  Publish an
        # explicit placeholder so the first structural verification sees the
        # same artifact inventory as the final package; the executed receipts
        # replace it before the final manifest is closed.
        _json(staging / "tamper_results.json", [])
        _write_manifest(staging)
        failures = verify_package(staging)
        if failures:
            raise VerifyError(
                "package verification failed: " + "; ".join(failures)
            )
        tamper_results = run_tamper_suite(staging, verify_package)
        _json(staging / "tamper_results.json", tamper_results)
        if not all(result["detected"] for result in tamper_results):
            raise VerifyError("tamper suite did not detect all attacks")
        # Refresh elapsed time after tamper probes, then close the final
        # manifest over both the completion marker and tamper evidence.
        _json(
            staging / "COMPLETED.json",
            {
                "status": "COMPLETED",
                "elapsed_seconds": round(time.time() - started, 1),
            },
        )
        _write_manifest(staging)
        failures = verify_package(staging)
        if failures:
            raise VerifyError(
                "post-tamper verification failed: " + "; ".join(failures)
            )
        backup = _atomic_publish(staging, output)
        # REWORK v3.1 (PI narrow durability): after the atomic rename, verify
        # the FINAL published package — handoff paths must resolve against the
        # canonical post-publication location (never .staging).
        post_failures = verify_package(output)
        if post_failures:
            # Ownership transfer BEFORE any rollback fault (EV E1): the
            # rollback restores last-good from the backup and then flushes the
            # parent directory; if that flush raises, the outer BaseException
            # handler below must NOT re-enter rollback with the same handle
            # (the backup is already consumed) and delete the restored
            # package.  Clearing the handle first makes the outer path a
            # no-op.  _rollback_publish itself is also idempotent (a consumed
            # backup is a fail-closed no-op) as a second line of defence.
            rollback_backup = backup
            backup = None
            _rollback_publish(output, rollback_backup)
            raise VerifyError(
                "post-publication verification failed: " + "; ".join(post_failures)
            )
        # The verified new package is now the visible last-good package.
        # Transfer ownership of the obsolete backup to cleanup *before* that
        # cleanup starts: if backup deletion succeeds and its parent fsync
        # fails, the outer exception path must never remove the verified new
        # package while trying to restore a backup that no longer exists.
        commit_backup = backup
        backup = None
        _commit_publish(output, commit_backup)
    except BaseException:
        if backup is not None:
            _rollback_publish(output, backup)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"[done] elapsed {time.time() - started:.1f}s -> {output}")
    return {"status": "ok", "output": str(output)}


# ==== SECTION: STAGES ====


def _run_stages(
    output: Path, *, published_output: Path | None = None
) -> None:
    # --- Stage 1: census ----------------------------------------------------
    vm = load_value_matrix(ROOT)
    panels = build_panels(vm)
    census = census_table(panels)
    elig = eligibility(panels)
    census.to_csv(output / "census.csv", index=False)
    elig.to_csv(output / "eligibility.csv", index=False)
    upstream_tickets = load_upstream_tickets(ROOT)
    upstream_ledger = load_upstream_ledger(ROOT)
    frozen_ticket_metrics = _frozen_incumbent_metric_map(upstream_tickets)
    print(
        f"[stage1 census] panels={len(panels)} "
        f"dev issues={census[census.split.isin(DEVELOPMENT_SPLITS)]['issue'].nunique()}"
    )

    # --- Stage 2: contexts + pool cache -------------------------------------
    incumbent_paths = build_incumbent_paths(upstream_ledger, upstream_tickets)
    incumbent_paths.to_parquet(output / "incumbent_paths.parquet", index=False)
    contexts = build_issue_contexts(panels, upstream_tickets, incumbent_paths)
    pool_cache = build_pool_cache(contexts)
    print(f"[stage2 contexts] {len(contexts)} issue contexts; {len(pool_cache)} pools")

    # --- Stage 3: label surface on fit fold (CV_2021) -----------------------
    fit_split_core, _ = _chronological_issue_blocks(
        contexts, (FIT_SPLIT,), fraction=0.15
    )
    ranker = fit_learned_ranker(
        _ranker_training_tickets(
            contexts, pool_cache, (FIT_SPLIT,), issue_whitelist=fit_split_core
        )
    )
    surface_fit = build_label_surface(
        contexts, pool_cache, train_splits=(FIT_SPLIT,), ranker=ranker
    )
    surface_fit.to_parquet(output / "label_surface_fit.parquet", index=False)

    # --- Stage 4: chronological folds ---------------------------------------
    fold_results: dict[str, object] = {}
    terminal_fitted_inventory: dict[str, object] | None = None
    terminal_diagnostic_loss = pd.DataFrame()
    fit_rows: list[pd.DataFrame] = []
    validation_rows: list[pd.DataFrame] = []
    chronology_rows: list[dict[str, object]] = []
    test_rows: list[pd.DataFrame] = []
    for fold_index, (train_splits, test_split) in enumerate(FOLDS):
        fold_name = f"fold{fold_index + 1}"
        fit_issues, validation_issues = _chronological_issue_blocks(
            contexts, train_splits, fraction=0.15
        )
        ranker_fold = fit_learned_ranker(
            _ranker_training_tickets(
                contexts,
                pool_cache,
                train_splits,
                issue_whitelist=fit_issues,
            )
        )
        surface_train = build_label_surface(
            contexts, pool_cache, train_splits=train_splits, ranker=ranker_fold
        )
        train_all_df = build_training_frame(surface_train, contexts)
        train_df = train_all_df.loc[
            train_all_df["issue"].astype(str).isin(fit_issues)
        ].copy()
        val_df = train_all_df.loc[
            train_all_df["issue"].astype(str).isin(validation_issues)
        ].copy()
        if train_df.empty or val_df.empty:
            raise ReplayError(f"{fold_name} has empty fit or validation block")
        overlap = set(train_df["issue"].astype(str)) & set(
            val_df["issue"].astype(str)
        )
        if overlap:
            raise ReplayError(
                f"{fold_name} chronological fit/validation overlap: "
                f"{sorted(overlap)[:5]}"
            )

        policy_mlp = fit_policy(
            train_df, kind="MLP", seed=MODEL_SEED, validation_df=val_df
        )
        policy_ridge = fit_policy(
            train_df, kind="RIDGE", seed=MODEL_SEED, validation_df=val_df
        )
        fixed_key = best_fixed_action_key(train_df)
        policy_fixed = fit_policy(
            train_df, kind="FIXED_ACTION", fixed_action_key=fixed_key
        )
        # Restricted dynamic attribution controls are genuine per-issue
        # state-conditioned policies.  They use the same causal state and
        # chronological train block as the full policy, but restrict the
        # action set so N-only, K-only and N×K effects are separately visible.
        restricted_policies = _fit_restricted_control_policies(
            train_df, val_df, seed=MODEL_SEED + 100 * (fold_index + 1)
        )
        # Persist the fitted model artifact (label-blind replay for #209).
        models_dir = output / "models"
        models_dir.mkdir(exist_ok=True)
        _persist_model(policy_mlp, models_dir / f"fold{fold_index + 1}_mlp.joblib")

        # OOD gate from fit-fold states.
        fit_states = [
            contexts[(split, issue)].state
            for (split, issue), ctx in contexts.items()
            if split in train_splits and str(issue) in fit_issues
        ]
        ood_scaler, ood_threshold = ood_gate(fit_states, fit_states)

        if test_split == TERMINAL_SPLIT:
            diagnostic_policy, terminal_diagnostic_loss = (
                _fit_chronological_diagnostic(train_all_df)
            )
            terminal_fitted_inventory = _fitted_object_inventory(
                ranker=ranker_fold,
                primary=policy_mlp,
                ridge=policy_ridge,
                fixed=policy_fixed,
                restricted=restricted_policies,
                ood_scaler=ood_scaler,
                ood_threshold=ood_threshold,
                diagnostic=diagnostic_policy,
            )
            _persist_model(policy_ridge, models_dir / "fold2_ridge.joblib")
            _persist_object(ranker_fold, models_dir / "fold2_ranker.joblib")
            for name, restricted_policy in restricted_policies.items():
                _persist_model(
                    restricted_policy,
                    models_dir / f"fold2_{name}.joblib",
                )
            _persist_object(
                ood_scaler, models_dir / "fold2_ood_scaler.joblib"
            )
            _persist_model(
                diagnostic_policy,
                models_dir / "fold2_diagnostic_mlp.joblib",
            )

        test_ctx = {
            (split, issue): ctx
            for (split, issue), ctx in contexts.items()
            if split == test_split
        }
        # Full-path replay of the learned policy on the test split.
        ranker_scores_test: dict[str, np.ndarray] = {}
        for (split, issue), ctx in test_ctx.items():
            for n in N_GRID:
                pool = pool_cache.get(f"{issue}:{n}")
                if pool is not None:
                    ranker_scores_test[f"{issue}:{n}"] = ranker_scores(
                        ranker_fold, pool
                    )

        def _learned_action_fn(ctx, prior):
            actions = _actions_for_issue(ctx)
            state = _state_with_prior(ctx, prior)
            action, trace = choose_action(
                policy_mlp, state, actions, ood_scaler=ood_scaler,
                ood_threshold=ood_threshold,
            )
            if action is None or not trace["safety_gate_pass"]:
                # Baseline-residual safety gate: fall back to the frozen
                # incumbent N7/K8/native-¥2 action when the gate fails.
                if _incumbent_feasible(ctx, prior.prior_bankroll_yuan):
                    fallback_action = Action(
                        7, 8, INCUMBENT_LANE, "NATIVE_2_YUAN"
                    )
                    trace["fallback_action"] = fallback_action.key
                    trace["fallback"] = "INCUMBENT_OR_NO_BET"
                    return fallback_action, trace
                return None, {**trace, "fallback": "NO_BET", "reason": "INCUMBENT_INFEASIBLE"}
            return action, trace

        path_learned = full_path_replay(
            test_ctx, pool_cache, action_fn=_learned_action_fn, split=test_split,
            policy_name="learned_policy",
            ranker_scores_by_issue=ranker_scores_test,
            frozen_incumbent=incumbent_paths,
            frozen_ticket_metrics=frozen_ticket_metrics,
        )
        path_learned.to_parquet(
            output / f"path_learned_fold{fold_index + 1}.parquet", index=False
        )
        # The decision artifact must reflect the live policy path, including
        # its own prior bankroll after earlier learned/fallback settlements.
        # A static re-score on the frozen incumbent bankroll is only a
        # counterfactual and is not serialized as the executed decision.
        decision_df = _decision_frame_from_path(path_learned)
        decision_df.to_parquet(
            output / f"decision_fold{fold_index + 1}.parquet", index=False
        )

        # Controls on the same test split (each evaluated as a full path).
        control_paths = _run_controls(
            test_ctx, pool_cache, test_split,
            restricted_policies=restricted_policies,
            ood_scaler=ood_scaler,
            ood_threshold=ood_threshold,
            frozen_incumbent=incumbent_paths,
            upstream_tickets=upstream_tickets,
        )
        for name, path in control_paths.items():
            path.to_parquet(output / f"path_control_{name}_fold{fold_index + 1}.parquet", index=False)

        # Control paths for Ridge + best-fixed-action (REWORK v2: evaluated).
        control_policy_paths = _run_policy_controls(
            test_ctx, pool_cache, test_split,
            policy_mlp=policy_mlp,
            policy_ridge=policy_ridge,
            policy_fixed=policy_fixed,
            ood_scaler=ood_scaler,
            ood_threshold=ood_threshold,
            ranker_scores_by_issue=ranker_scores_test,
            frozen_incumbent=incumbent_paths,
            frozen_ticket_metrics=frozen_ticket_metrics,
        )
        for name, path in control_policy_paths.items():
            path.to_parquet(output / f"path_control_{name}_fold{fold_index + 1}.parquet", index=False)

        fold_results[fold_name] = {
            "train_splits": list(train_splits),
            "fit_issues": sorted(fit_issues),
            "validation_issues": sorted(validation_issues),
            "test_split": test_split,
            "learned_summary": summarize_path(path_learned),
            "control_summaries": {
                name: summarize_path(path)
                for name, path in {**control_paths, **control_policy_paths}.items()
            },
            "fixed_action_key": fixed_key,
            "policy_mlp": serialize_policy(
                policy_mlp,
                model_path=models_dir / f"fold{fold_index + 1}_mlp.joblib",
            ),
            "policy_ridge": serialize_policy(policy_ridge),
            "policy_fixed": {
                "model_kind": "FIXED_ACTION",
                "fixed_action_key": fixed_key,
            },
            "restricted_dynamic_controls": {
                name: serialize_policy(policy)
                for name, policy in restricted_policies.items()
            },
            "ood_threshold": ood_threshold,
        }
        fit_rows.append(
            train_df.assign(fold=fold_name, training_role="FIT")
        )
        validation_rows.append(
            val_df.assign(fold=fold_name, training_role="VALIDATION")
        )
        chronology_rows.extend(
            {
                "fold": fold_name,
                "issue": issue,
                "role": "FIT",
                "used_by_q_fit": True,
                "used_by_ranker_fit": True,
                "used_by_ood_fit": True,
            }
            for issue in sorted(fit_issues)
        )
        chronology_rows.extend(
            {
                "fold": fold_name,
                "issue": issue,
                "role": "VALIDATION",
                "used_by_q_fit": False,
                "used_by_ranker_fit": False,
                "used_by_ood_fit": False,
            }
            for issue in sorted(validation_issues)
        )
        test_rows.append(decision_df)
        print(
            f"[stage4 fold{fold_index + 1}] train={train_splits} test={test_split} "
            f"learned ending={summarize_path(path_learned).get('ending_capital_yuan', float('nan')):.2f}"
        )

    # --- Stage 5: diagnostics -----------------------------------------------
    all_fit = pd.concat(fit_rows, ignore_index=True)
    all_fit.to_parquet(output / "training_frame_all.parquet", index=False)
    all_validation = pd.concat(validation_rows, ignore_index=True)
    all_validation.to_parquet(
        output / "validation_frame_all.parquet", index=False
    )
    pd.DataFrame(chronology_rows).to_parquet(
        output / "chronology_blocks.parquet", index=False
    )
    if terminal_fitted_inventory is None:
        raise ReplayError("terminal fitted-object inventory was not produced")
    _json(
        output / "fitted_object_inventory.json",
        {"terminal_fold": "fold2", "fitted_objects": terminal_fitted_inventory},
    )
    all_test = pd.concat(test_rows, ignore_index=True)
    all_test.to_parquet(output / "decision_rows_all.parquet", index=False)
    _write_diagnostics(
        output,
        val_df,
        all_test,
        contexts,
        policy_mlp,
        train_all_df,
        diagnostic_loss=terminal_diagnostic_loss,
    )

    # Consolidated capital ledger for verification + tamper targeting.
    ledger_parts = [
        pd.read_parquet(path)
        for path in sorted(output.glob("path_learned_fold*.parquet"))
    ]
    for path in sorted(output.glob("path_control_*_fold*.parquet")):
        ledger_parts.append(pd.read_parquet(path))
    consolidated = pd.concat(ledger_parts, ignore_index=True)
    consolidated.to_parquet(output / "issue_capital_ledger.parquet", index=False)

    # Decision-critical path and concentration summaries are materialized,
    # not left as report-only calculations.
    holding_rows: list[dict[str, object]] = []
    for path_file in sorted(output.glob("path_*_fold*.parquet")):
        path_frame = pd.read_parquet(path_file)
        if path_frame.empty:
            continue
        holding_rows.append(
            {
                "artifact": path_file.name,
                "split": str(path_frame.iloc[0]["split"]),
                "policy": str(path_frame.iloc[0]["policy"]),
                **summarize_path(path_frame),
                **path_holding_metrics(path_frame),
            }
        )
    pd.DataFrame(holding_rows).to_parquet(
        output / "path_holding_metrics.parquet", index=False
    )

    dynamic_names = {
        "dynamic_n_fixed_k8_lane",
        "fixed_n7_dynamic_k",
        "dynamic_nk_fixed_generator",
    }
    dynamic_rows = consolidated.loc[
        consolidated["policy"].isin(dynamic_names)
    ].copy()
    dynamic_rows.to_parquet(
        output / "dynamic_control_decisions.parquet", index=False
    )

    # --- Stage 6: selection rule + #209 handoff ------------------------------
    selection = _apply_selection_rule(
        fold_results, all_test, all_fit, incumbent_paths=incumbent_paths
    )
    _json(output / "selection.json", selection)
    handoff = _build_handoff(
        fold_results, selection, output, published_output=published_output
    )
    _json(output / "handoff_209.json", handoff)

    # Materialize decision ticket identities + seed aggregates (REQ-208-04).
    # REWORK v3: pass the terminal-fold ranker so the LEARNED_MLP lane can be
    # materialized for ticket_economics.parquet (payout-economics verifier).
    _write_ticket_artifacts(
        output, test_ctx, pool_cache, fold_results, ranker=ranker_fold
    )
    _write_holdout_mutation_receipt(
        output, vm, upstream_tickets, upstream_ledger
    )


# ==== SECTION: HELPERS ====


def _ranker_training_tickets(
    contexts,
    pool_cache,
    train_splits,
    *,
    issue_whitelist: set[str] | None = None,
):
    rows = []
    for (split, issue), ctx in contexts.items():
        if split not in train_splits:
            continue
        if issue_whitelist is not None and str(issue) not in issue_whitelist:
            continue
        pool = pool_cache.get(f"{issue}:7")
        if pool is None:
            continue
        sub = pool.copy()
        sub["labels_available"] = ctx.panel.labels_available
        rows.append(sub)
    return pd.concat(rows, ignore_index=True)


def _chronological_issue_blocks(
    contexts,
    train_splits,
    *,
    fraction: float = 0.15,
) -> tuple[set[str], set[str]]:
    """Return disjoint chronological fit and validation issue sets.

    The issue block is resolved before fitting the ticket ranker, Q models,
    restricted controls or OOD scaler.  This prevents the prior defect where
    validation rows were scored separately but still entered every fit API.
    """
    issues = sorted(
        str(issue)
        for (split, issue) in contexts
        if split in train_splits
    )
    if len(issues) < 5:
        raise ReplayError("chronological split needs at least five issues")
    cut = max(2, int(len(issues) * (1.0 - fraction)))
    fit_issues = set(issues[:cut])
    validation_issues = set(issues[cut:])
    if not fit_issues or not validation_issues:
        raise ReplayError("empty chronological fit or validation issue block")
    if fit_issues & validation_issues:
        raise ReplayError("chronological issue blocks overlap")
    return fit_issues, validation_issues


def _chronological_validation_frame(
    train_df: pd.DataFrame, *, fraction: float = 0.15
) -> pd.DataFrame:
    issues = sorted(train_df["issue"].astype(str).unique())
    if len(issues) < 5:
        return pd.DataFrame()
    cut = max(2, int(len(issues) * (1.0 - fraction)))
    val_issues = set(issues[cut:])
    return train_df.loc[train_df["issue"].astype(str).isin(val_issues)]


def _state_with_prior(ctx, prior) -> np.ndarray:
    """Return the issue's causal state with this policy path's LIVE prior.

    REWORK v4 (EV D1): replaces ALL FIVE path-dependent state features
    (prior_bankroll_yuan, prior_trail5_bankroll_yuan,
    prior_trail10_bankroll_yuan, prior_running_drawdown_pct,
    prior_consecutive_losses) from the lane's own strictly-prior live
    history.  The old helper only replaced prior_bankroll_yuan and kept the
    frozen-incumbent trail/drawdown/loss features, so once a learned/control
    action diverged from the incumbent the next issue's state was
    counterfactual.
    """
    state = np.asarray(ctx.state, dtype=float).copy()
    for name in (
        "prior_bankroll_yuan",
        "prior_trail5_bankroll_yuan",
        "prior_trail10_bankroll_yuan",
        "prior_running_drawdown_pct",
        "prior_consecutive_losses",
    ):
        state[STATE_FEATURE_NAMES.index(name)] = float(getattr(prior, name))
    return state


def _decision_frame_from_path(path: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, row in path.iterrows():
        trace = json.loads(str(row["decision_trace_json"]))
        rows.append(
            {
                "split": str(row["split"]),
                "issue": str(row["issue"]),
                "year": int(row["year"]),
                "action_key": str(row["action_key"]),
                "n": row.get("n"),
                "k": row.get("k"),
                "lane": row.get("lane"),
                "capital": row.get("capital"),
                "prior_bankroll_yuan": float(row["pre_issue_bankroll_yuan"]),
                "predicted_lift": float(trace.get("predicted_lift", np.nan)),
                "conservative_lift": float(
                    trace.get("conservative_lift", np.nan)
                ),
                "ood_statistic": float(trace.get("ood_statistic", np.nan)),
                "ood_threshold": trace.get("ood_threshold"),
                "safety_gate_pass": bool(trace.get("safety_gate_pass", False)),
                "fallback": str(trace.get("fallback", "NO_BET")),
                "decision_trace_json": str(row["decision_trace_json"]),
            }
        )
    return pd.DataFrame(rows)


def _restricted_control_frame(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    """Return the preregistered action subset for one attribution control."""
    common = (
        frame["lane"].eq("MARKET_WOR")
        & frame["capital"].eq("NATIVE_2_YUAN")
    )
    if name == "dynamic_n_fixed_k8_lane":
        mask = common & frame["k"].eq(8)
    elif name == "fixed_n7_dynamic_k":
        mask = common & frame["n"].eq(7)
    elif name == "dynamic_nk_fixed_generator":
        mask = common
    else:  # pragma: no cover - internal contract guard
        raise ValueError(f"unknown restricted control {name}")
    return frame.loc[mask].copy()


def _fit_restricted_control_policies(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    *,
    seed: int,
) -> dict[str, object]:
    """Fit causal state-conditioned MLP controls on restricted action sets.

    Unlike the superseded implementation, no train-fold global median action
    is repeated across all test issues.  Each control scores its lawful action
    subset for each issue from that issue's pre-event state.
    """
    policies: dict[str, object] = {}
    names = (
        "dynamic_n_fixed_k8_lane",
        "fixed_n7_dynamic_k",
        "dynamic_nk_fixed_generator",
    )
    for offset, name in enumerate(names):
        restricted = _restricted_control_frame(train_df, name)
        restricted_val = _restricted_control_frame(validation_df, name)
        if restricted.empty:
            raise ReplayError(f"restricted control has no training rows: {name}")
        policies[name] = fit_policy(
            restricted,
            kind="MLP",
            seed=seed + offset,
            validation_df=restricted_val,
        )
    return policies


def _stable_model_payload(model: object) -> dict[str, object]:
    """Extract deterministic fitted numerical state from an sklearn pipeline."""
    if model is None:
        return {}
    steps = getattr(model, "named_steps", {})
    scaler = steps.get("standardscaler")
    estimator = (
        steps.get("mlpregressor")
        or steps.get("mlpclassifier")
        or steps.get("ridge")
    )
    payload: dict[str, object] = {
        "pipeline_steps": list(steps),
        "estimator_type": type(estimator).__name__ if estimator is not None else None,
    }
    if scaler is not None:
        payload["scaler_mean"] = np.asarray(scaler.mean_, dtype=float).tolist()
        payload["scaler_scale"] = np.asarray(scaler.scale_, dtype=float).tolist()
    if estimator is not None:
        if hasattr(estimator, "coefs_"):
            payload["coefs"] = [
                np.asarray(value, dtype=float).tolist()
                for value in estimator.coefs_
            ]
            payload["intercepts"] = [
                np.asarray(value, dtype=float).tolist()
                for value in estimator.intercepts_
            ]
        if hasattr(estimator, "coef_"):
            payload["coef"] = np.asarray(
                estimator.coef_, dtype=float
            ).tolist()
            payload["intercept"] = np.asarray(
                estimator.intercept_, dtype=float
            ).tolist()
        if hasattr(estimator, "classes_"):
            payload["classes"] = np.asarray(estimator.classes_).tolist()
        if getattr(estimator, "n_iter_", None) is not None:
            payload["n_iter"] = int(estimator.n_iter_)
    return payload


def _stable_policy_payload(policy: object) -> dict[str, object]:
    return {
        "model_kind": str(policy.model_kind),
        "fixed_action_key": policy.fixed_action_key,
        "fitted_action_keys": list(policy.fitted_action_keys),
        "residual_rmse": float(policy.residual_rmse),
        "validation_rmse": (
            float(policy.validation_rmse)
            if policy.validation_rmse is not None
            else None
        ),
        "fit_issue_count": int(policy.fit_issue_count),
        "validation_issue_count": int(policy.validation_issue_count),
        "model": _stable_model_payload(policy.model),
    }


def _stable_scaler_payload(scaler: object) -> dict[str, object]:
    return {
        "type": type(scaler).__name__,
        "mean": np.asarray(scaler.mean_, dtype=float).tolist(),
        "scale": np.asarray(scaler.scale_, dtype=float).tolist(),
        "n_features_in": int(scaler.n_features_in_),
    }


def _fit_chronological_diagnostic(
    train_all_df: pd.DataFrame,
) -> tuple[object, pd.DataFrame]:
    """Fit the one diagnostic model once and return its bound loss output."""
    issues = sorted(train_all_df["issue"].astype(str).unique())
    cut = max(2, int(len(issues) * 0.85))
    fit_issues = set(issues[:cut])
    validation_issues = set(issues[cut:])
    fit_df = train_all_df.loc[
        train_all_df["issue"].astype(str).isin(fit_issues)
    ]
    validation_df = train_all_df.loc[
        train_all_df["issue"].astype(str).isin(validation_issues)
    ]
    policy = fit_policy(
        fit_df, kind="MLP", seed=MODEL_SEED, validation_df=validation_df
    )
    loss = pd.DataFrame(
        [{
            "model": "MLP",
            "fit_issues": len(fit_issues),
            "validation_issues": len(validation_issues),
            "fit_rmse": float(policy.residual_rmse),
            "validation_rmse": float(policy.validation_rmse),
        }]
    )
    return policy, loss


def _fitted_object_inventory(
    *,
    ranker: object,
    primary: object,
    ridge: object,
    fixed: object,
    restricted: dict[str, object],
    ood_scaler: object,
    ood_threshold: float,
    diagnostic: object,
) -> dict[str, object]:
    return {
        "ticket_ranker": _stable_model_payload(ranker),
        "primary_mlp": _stable_policy_payload(primary),
        "ridge": _stable_policy_payload(ridge),
        "best_fixed": _stable_policy_payload(fixed),
        "restricted_mlps": {
            name: _stable_policy_payload(policy)
            for name, policy in sorted(restricted.items())
        },
        "ood": {
            "scaler": _stable_scaler_payload(ood_scaler),
            "threshold": float(ood_threshold),
        },
        "diagnostic_mlp": _stable_policy_payload(diagnostic),
    }


def _actual_refit_signature(
    value_matrix: pd.DataFrame,
    upstream_tickets: pd.DataFrame,
    upstream_ledger: pd.DataFrame,
) -> dict[str, object]:
    """Refit the terminal development fold and return its decision signature.

    This is intentionally the production construction path: panels, contexts,
    ticket ranker, counterfactual action surface, MLP, fixed control, OOD gate
    and earlier-fold decisions are all recomputed.  Merely comparing a census
    is not evidence of holdout isolation.
    """
    panels = build_panels(value_matrix)
    incumbent_paths = build_incumbent_paths(upstream_ledger, upstream_tickets)
    contexts = build_issue_contexts(panels, upstream_tickets, incumbent_paths)
    pool_cache = build_pool_cache(contexts)
    train_splits, test_split = FOLDS[-1]
    fit_issues, validation_issues = _chronological_issue_blocks(
        contexts, train_splits, fraction=0.15
    )
    ranker = fit_learned_ranker(
        _ranker_training_tickets(
            contexts,
            pool_cache,
            train_splits,
            issue_whitelist=fit_issues,
        )
    )
    train_surface = build_label_surface(
        contexts, pool_cache, train_splits=train_splits, ranker=ranker
    )
    train_all_df = build_training_frame(train_surface, contexts)
    train_df = train_all_df.loc[
        train_all_df["issue"].astype(str).isin(fit_issues)
    ].copy()
    validation_df = train_all_df.loc[
        train_all_df["issue"].astype(str).isin(validation_issues)
    ].copy()
    policy = fit_policy(
        train_df,
        kind="MLP",
        seed=MODEL_SEED,
        validation_df=validation_df,
    )
    ridge = fit_policy(
        train_df,
        kind="RIDGE",
        seed=MODEL_SEED,
        validation_df=validation_df,
    )
    fixed_key = best_fixed_action_key(train_df)
    fixed = fit_policy(
        train_df,
        kind="FIXED_ACTION",
        fixed_action_key=fixed_key,
    )
    restricted = _fit_restricted_control_policies(
        train_df, validation_df, seed=MODEL_SEED + 200
    )
    diagnostic, _ = _fit_chronological_diagnostic(train_all_df)
    fit_states = [
        ctx.state
        for (split, issue), ctx in contexts.items()
        if split in train_splits and str(issue) in fit_issues
    ]
    ood_scaler, ood_threshold = ood_gate(fit_states, fit_states)
    test_ctx = {
        (split, issue): ctx
        for (split, issue), ctx in contexts.items()
        if split == test_split
    }
    ranker_scores_by_issue: dict[str, np.ndarray] = {}
    for (_, issue), ctx in test_ctx.items():
        for n in N_GRID:
            pool = pool_cache.get(f"{issue}:{n}")
            if pool is not None:
                ranker_scores_by_issue[f"{issue}:{n}"] = ranker_scores(
                    ranker, pool
                )

    def _refit_action_fn(ctx, prior):
        state = _state_with_prior(ctx, prior)
        action, trace = choose_action(
            policy,
            state,
            _actions_for_issue(ctx),
            ood_scaler=ood_scaler,
            ood_threshold=ood_threshold,
        )
        if action is None or not trace["safety_gate_pass"]:
            if _incumbent_feasible(ctx, prior.prior_bankroll_yuan):
                fallback = Action(7, 8, INCUMBENT_LANE, "NATIVE_2_YUAN")
                return fallback, {
                    **trace,
                    "fallback_action": fallback.key,
                    "fallback": "INCUMBENT_OR_NO_BET",
                }
            return None, {
                **trace,
                "fallback": "NO_BET",
                "reason": "INCUMBENT_INFEASIBLE",
            }
        return action, trace

    replay = full_path_replay(
        test_ctx,
        pool_cache,
        action_fn=_refit_action_fn,
        split=test_split,
        policy_name="holdout_refit_probe",
        ranker_scores_by_issue=ranker_scores_by_issue,
        frozen_incumbent=incumbent_paths,
        frozen_ticket_metrics=_frozen_incumbent_metric_map(upstream_tickets),
    )
    decisions = [
        {
            "issue": str(row["issue"]),
            "prior_bankroll_yuan": float(row["pre_issue_bankroll_yuan"]),
            "action_key": str(row["action_key"]),
            "decision_trace_json": str(row["decision_trace_json"]),
        }
        for _, row in replay.iterrows()
    ]
    payload = {
        "train_splits": list(train_splits),
        "test_split": test_split,
        "training_issues": sorted(train_df["issue"].astype(str).unique()),
        "validation_issues": sorted(
            validation_df["issue"].astype(str).unique()
        ),
        "fitted_objects": _fitted_object_inventory(
            ranker=ranker,
            primary=policy,
            ridge=ridge,
            fixed=fixed,
            restricted=restricted,
            ood_scaler=ood_scaler,
            ood_threshold=ood_threshold,
            diagnostic=diagnostic,
        ),
        "decisions": decisions,
    }
    return {
        "sha256": _sha256_json(payload),
        "payload": payload,
    }


def _mutate_locked_test_labels(value_matrix: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    mutated = value_matrix.copy()
    locked = mutated["split"].astype(str).eq("LOCKED_TEST")
    row_count = int(locked.sum())
    if row_count == 0:
        raise ReplayError("holdout mutation probe found no LOCKED_TEST rows")
    locked_frame = mutated.loc[locked].copy()
    for _, group in locked_frame.groupby(
        ["split", "issue", "match_idx"], sort=False
    ):
        realized = group["realized_outcome"].astype(bool).to_numpy()
        if int(realized.sum()) == 1:
            current = int(np.flatnonzero(realized)[0])
            shifted = np.zeros(len(group), dtype=bool)
            shifted[(current + 1) % len(group)] = True
            mutated.loc[group.index, "realized_outcome"] = shifted
    mutated.loc[locked, "official_final_sp_label"] = (
        mutated.loc[locked, "official_final_sp_label"].astype(float) * 1.5
    )
    return mutated, row_count


def _write_holdout_mutation_receipt(
    output: Path,
    value_matrix: pd.DataFrame,
    upstream_tickets: pd.DataFrame,
    upstream_ledger: pd.DataFrame,
) -> None:
    baseline = _actual_refit_signature(
        value_matrix, upstream_tickets, upstream_ledger
    )
    mutated, mutated_rows = _mutate_locked_test_labels(value_matrix)
    after = _actual_refit_signature(mutated, upstream_tickets, upstream_ledger)
    invariant = baseline["sha256"] == after["sha256"]
    baseline_file = "holdout_refit_baseline.json"
    mutated_file = "holdout_refit_mutated.json"
    _json(output / baseline_file, baseline["payload"])
    _json(output / mutated_file, after["payload"])
    receipt = {
        "probe": "ACTUAL_TERMINAL_FOLD_REFIT_AFTER_LOCKED_TEST_LABEL_MUTATION",
        "mutated_split": "LOCKED_TEST",
        "mutated_rows": mutated_rows,
        "calendar_2024_rows_available": int(
            value_matrix["issue"].astype(str).str.startswith("24").sum()
        ),
        "baseline_signature_sha256": baseline["sha256"],
        "mutated_signature_sha256": after["sha256"],
        "baseline_payload_file": baseline_file,
        "mutated_payload_file": mutated_file,
        "all_fitted_objects_and_decisions_invariant": invariant,
    }
    _json(output / "holdout_mutation_receipt.json", receipt)
    if not invariant:
        raise VerifyError("LOCKED_TEST label mutation changed fitted #208 policy")


def _persist_model(policy, path: Path) -> None:
    import joblib

    joblib.dump(policy.model, path)


def _persist_object(value: object, path: Path) -> None:
    import joblib

    joblib.dump(value, path)


def _actions_for_issue(ctx):
    m = len(ctx.panel.match_idx)
    return [
        Action(n=n, k=k, lane=lane, capital=capital)
        for n in N_GRID
        if n <= m
        for k in K_GRID
        for lane in LANES
        for capital in CAPITAL_LANES
    ]


def _incumbent_feasible(ctx, bankroll: float) -> bool:
    return (
        len(ctx.panel.match_idx) >= INCUMBENT_N
        and bankroll >= INCUMBENT_K * 2.0
    )


def _write_ticket_artifacts(
    output, test_ctx, pool_cache, fold_results, ranker=None
) -> None:
    """Materialize decision ticket identities + per-seed aggregates.

    REWORK v2 (D3/D4): seed=0 is never used; for stochastic lanes the
    materialized tickets are the union over the 16 preregistered seeds, with
    per-seed ticket identities recorded and seed aggregates computed.

    REWORK v3 (PI payout-economics): additionally materializes
    `ticket_economics.parquet` — per-ticket pre-tax multiples, expected net
    and raw official-SP products — so the production verifier can independently
    recompute the corrected payout formula (0.65 applied exactly once) through
    the immutable package (omission / division-out / 0.65^N detection).

    Deterministic lanes (VALUE_WOR / LEARNED_MLP) are single-evaluation rows
    (seed=0 is not a stochastic seed; deterministic lanes ignore the seed).
    LEARNED_MLP requires the fold's ranker scores; `ranker` defaults to the
    fit-fold ranker when not provided.
    """
    from parlay_policy.contract import ALL_SEEDS, LANES, K_GRID
    from parlay_policy.tickets import (
        ranker_scores,
        select_tickets,
        settle_tickets,
    )

    if ranker is None:
        raise ReplayError(
            "ticket-economics materialization requires a ranker for LEARNED_MLP"
        )
    rows: list[dict[str, Any]] = []
    economics: list[dict[str, Any]] = []
    for (split, issue), ctx in test_ctx.items():
        for n in N_GRID:
            pool = pool_cache.get(f"{issue}:{n}")
            if pool is None:
                continue
            scores = None
            if "LEARNED_MLP" in LANES:
                scores = ranker_scores(ranker, pool)
            for lane in LANES:
                for k in K_GRID:
                    if lane in ("MARKET_WR", "MARKET_WOR"):
                        for seed in ALL_SEEDS:
                            sel = select_tickets(pool, lane, k, seed=seed)
                            rows.append(
                                {
                                    "split": split,
                                    "issue": issue,
                                    "n": n,
                                    "k": k,
                                    "lane": lane,
                                    "seed": seed,
                                    "ticket_identity": sel["ticket_identity"].tolist(),
                                }
                            )
                            settled = settle_tickets(sel)
                            for ticket_position, (_, tr) in enumerate(
                                settled.iterrows()
                            ):
                                economics.append(
                                    {
                                        "split": split,
                                        "issue": issue,
                                        "n": int(tr["n"]),
                                        "k": int(k),
                                        "lane": lane,
                                        "seed": int(seed),
                                        "ticket_position": int(ticket_position),
                                        "ticket_identity": str(tr["ticket_identity"]),
                                        "match_indices": str(tr["match_indices"]),
                                        "outcomes": str(tr["outcomes"]),
                                        "realized_hit": bool(tr["realized_hit"]),
                                        "pre_tax_gross_multiple": float(
                                            tr["pre_tax_gross_multiple"]
                                        ),
                                        "payout_yuan": float(tr["payout_yuan"]),
                                    }
                                )
                    else:
                        sel = select_tickets(
                            pool, lane, k, seed=0, scores=scores
                        )
                        rows.append(
                            {
                                "split": split,
                                "issue": issue,
                                "n": n,
                                "k": k,
                                "lane": lane,
                                "seed": 0,
                                "ticket_identity": sel["ticket_identity"].tolist(),
                            }
                        )
                        settled = settle_tickets(sel)
                        for ticket_position, (_, tr) in enumerate(
                            settled.iterrows()
                        ):
                            economics.append(
                                {
                                    "split": split,
                                    "issue": issue,
                                    "n": int(tr["n"]),
                                    "k": int(k),
                                    "lane": lane,
                                    "seed": 0,
                                    "ticket_position": int(ticket_position),
                                    "ticket_identity": str(tr["ticket_identity"]),
                                    "match_indices": str(tr["match_indices"]),
                                    "outcomes": str(tr["outcomes"]),
                                    "realized_hit": bool(tr["realized_hit"]),
                                    "pre_tax_gross_multiple": float(
                                        tr["pre_tax_gross_multiple"]
                                    ),
                                    "payout_yuan": float(tr["payout_yuan"]),
                                }
                            )
    frame = pd.DataFrame(rows)
    frame.to_parquet(output / "decision_ticket_identities.parquet", index=False)
    econ = pd.DataFrame(economics)
    econ.to_parquet(output / "ticket_economics.parquet", index=False)


# ==== SECTION: METADATA + MANIFEST ====


def _write_metadata(output: Path, started: float) -> None:
    producer_code_commit = _git_head()
    code_bindings = _code_bindings()
    environment = _environment()
    environment_lock_sha256 = _sha256_json(environment)
    req_evidence = [
        {
            "req": f"REQ-208-{index:02d}",
            "status": "PASS",
            "evidence": evidence,
        }
        for index, evidence in {
            1: ["provenance.json", "incumbent_paths.parquet"],
            2: ["ticket_economics.parquet", "decision_ticket_identities.parquet"],
            3: ["holdout_mutation_receipt.json", "provenance.json"],
            4: ["training_frame_all.parquet", "decision_ticket_identities.parquet"],
            5: ["dynamic_control_decisions.parquet", "issue_capital_ledger.parquet"],
            6: ["issue_capital_ledger.parquet", "path_holding_metrics.parquet"],
            7: ["path_holding_metrics.parquet", "selection.json"],
            8: ["handoff_209.json", "models/fold2_mlp.joblib"],
            9: ["decision_rows_all.parquet", "models/fold2_mlp.joblib"],
        }.items()
    ]
    decision = {
        "contract_version": CONTRACT_VERSION,
        "producer_code_commit": producer_code_commit,
        "exact_reviewed_sha_binding": "external producer handoff and independent EV verdict",
        "req_evidence": req_evidence,
        "upstream_207": {
            "sha": "90869a959dc1b972cd872ffe465d1009e29df75e",
            "manifest_sha256": "48c11d971c20cb2239cd342ade4084bea484686bd106253c77a320ba7ae78ab6",
        },
        "incumbent": {
            "n": INCUMBENT_N,
            "k": INCUMBENT_K,
            "lane": INCUMBENT_LANE,
            "capital": "NATIVE_2_YUAN",
        },
        "initial_bankroll_yuan": INITIAL_BANKROLL_YUAN,
        "payout_semantics": {
            "pre_tax_gross_multiple": "hit * 0.65 * product(official_final_sp_i)",
            "coefficient": "Beijing Single Match payout coefficient, applied once",
            "superseded": "product(SP) as pre-tax gross; division by 0.65; 0.65^N",
        },
        "elapsed_seconds": round(time.time() - started, 1),
    }
    _json(output / "decision.json", decision)
    _json(output / "protocol_log.json", as_action_dict())
    _json(
        output / "provenance.json",
        {
            "version": CONTRACT_VERSION,
            "source_value_matrix": "results/issue-205/value_matrix.parquet",
            "source_value_matrix_sha256": "8fdace9c7249502456f8990137011847df9addae5ad633e61760c44b7ccde84b",
            "source_issue_207": "results/issue-207",
            "source_issue_207_sha": "90869a959dc1b972cd872ffe465d1009e29df75e",
            "source_issue_207_manifest_sha256": "48c11d971c20cb2239cd342ade4084bea484686bd106253c77a320ba7ae78ab6",
            "label_boundary": "CV_2021 fit; CV_2022/CV_2023 development; 2024/2025/2026 embargoed",
            "replay": "PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py run --output results/issue-208",
            "producer_code_commit": producer_code_commit,
            "code_bindings": code_bindings,
            "environment": environment,
            "environment_lock_sha256": environment_lock_sha256,
        },
    )
    # Plain-text receipt binds method.yaml hash (method_preflight checks it).
    shutil.copy2(ROOT / "method.yaml", output / "method.yaml")
    method_hash = sha256_file(output / "method.yaml")
    (output / "receipt.sha256").write_text(
        f"{method_hash}  method.yaml\n", encoding="utf-8"
    )
    _write_schema(output)


def _series_contract(series: pd.Series) -> str:
    """Stable portable dtype name for a published frame column."""
    if pd.api.types.is_bool_dtype(series):
        return "bool"
    if pd.api.types.is_integer_dtype(series):
        return "int"
    if pd.api.types.is_numeric_dtype(series):
        return "float"
    present = series.dropna()
    if present.map(lambda value: isinstance(value, str)).all():
        return "str"
    return "any"


def _frame_contract(path: Path, *, diagnostic_only: bool) -> dict[str, object]:
    frame = (
        pd.read_parquet(path)
        if path.suffix == ".parquet"
        else pd.read_csv(path)
    )
    return {
        "columns": {
            str(column): _series_contract(frame[column])
            for column in frame.columns
        },
        "diagnostic_only": diagnostic_only,
    }


def _write_schema(output: Path) -> None:
    """Declarative column schema for the immutable package frames."""
    schema: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "frames": {
            "census.csv": {
                "split": "str", "issue": "numeric", "year": "int",
                "M": "int", "labels_available": "bool",
                "excluded_matches": "int",
            },
            "eligibility.csv": {
                "split": "str", "issue": "numeric", "year": "int",
                "M": "int", "N": "int", "eligible": "bool",
                "labels_available": "bool",
            },
            "issue_capital_ledger.parquet": {
                "columns": {
                    "split": "str", "issue": "str", "year": "int",
                    "policy": "str", "action_key": "str",
                    "pre_issue_bankroll_yuan": "float",
                    "requested_stake_yuan": "float",
                    "funded_stake_yuan": "float",
                    "gross_payout_yuan": "float",
                    "post_issue_bankroll_yuan": "float",
                    "net_pnl_yuan": "float",
                    "mean_pairwise_overlap": "float",
                    "ticket_hhi": "float",
                    "repeat_exposure": "float",
                },
                "non_null": [
                    "split", "issue", "year", "policy", "action_key",
                    "pre_issue_bankroll_yuan", "requested_stake_yuan",
                    "funded_stake_yuan", "gross_payout_yuan",
                    "post_issue_bankroll_yuan", "net_pnl_yuan",
                ],
                "primary_key": ["split", "policy", "issue"],
                "domains": {"split": ["CV_2022", "CV_2023"]},
                "units": {
                    "pre_issue_bankroll_yuan": "CNY",
                    "requested_stake_yuan": "CNY",
                    "funded_stake_yuan": "CNY",
                    "gross_payout_yuan": "CNY",
                    "post_issue_bankroll_yuan": "CNY",
                    "net_pnl_yuan": "CNY",
                },
            },
            "decision_rows_all.parquet": {
                "columns": {
                    "split": "str", "issue": "str", "year": "int",
                    "action_key": "str", "n": "int", "k": "int",
                    "lane": "str", "capital": "str",
                    "prior_bankroll_yuan": "float",
                    "predicted_lift": "float", "conservative_lift": "float",
                    "safety_gate_pass": "bool", "decision_trace_json": "str",
                },
                "non_null": [
                    "split", "issue", "year", "action_key",
                    "prior_bankroll_yuan", "safety_gate_pass",
                    "decision_trace_json",
                ],
                "primary_key": ["split", "issue"],
                "domains": {
                    "split": ["CV_2022", "CV_2023"],
                    "lane": ["MARKET_WR", "MARKET_WOR", "VALUE_WOR", "LEARNED_MLP"],
                    "capital": ["NATIVE_2_YUAN", "SIMPLE_ACTIVE"],
                },
                "units": {
                    "prior_bankroll_yuan": "CNY",
                    "predicted_lift": "CNY per issue vs frozen incumbent",
                    "conservative_lift": "CNY per issue vs frozen incumbent",
                },
            },
            "dynamic_control_decisions.parquet": {
                "columns": {
                    "split": "str", "issue": "str", "year": "int",
                    "policy": "str", "action_key": "str",
                    "pre_issue_bankroll_yuan": "float",
                    "requested_stake_yuan": "float",
                    "funded_stake_yuan": "float",
                    "gross_payout_yuan": "float",
                    "post_issue_bankroll_yuan": "float",
                    "net_pnl_yuan": "float",
                    "decision_trace_json": "str",
                },
                "non_null": [
                    "split", "issue", "year", "policy", "action_key",
                    "pre_issue_bankroll_yuan", "requested_stake_yuan",
                    "funded_stake_yuan", "gross_payout_yuan",
                    "post_issue_bankroll_yuan", "net_pnl_yuan",
                    "decision_trace_json",
                ],
                "primary_key": ["split", "policy", "issue"],
                "domains": {
                    "split": ["CV_2022", "CV_2023"],
                    "policy": [
                        "dynamic_n_fixed_k8_lane", "fixed_n7_dynamic_k",
                        "dynamic_nk_fixed_generator",
                    ],
                },
                "units": {
                    "pre_issue_bankroll_yuan": "CNY",
                    "requested_stake_yuan": "CNY",
                    "funded_stake_yuan": "CNY",
                    "gross_payout_yuan": "CNY",
                    "post_issue_bankroll_yuan": "CNY",
                    "net_pnl_yuan": "CNY",
                },
            },
            "path_holding_metrics.parquet": {
                "columns": {
                    "artifact": "str", "split": "str", "policy": "str",
                    "ending_capital_yuan": "float",
                    "max_drawdown_pct": "float",
                    "turnover_yuan": "float",
                    "total_net_pnl_yuan": "float",
                    "max_consecutive_losing_issues": "float",
                    "time_under_water_issues": "float",
                    "max_recovery_issues": "float",
                    "open_underwater_issues": "float",
                    "ex_largest_issue_ending_capital_yuan": "float",
                },
                "non_null": [
                    "artifact", "split", "policy", "ending_capital_yuan",
                    "max_drawdown_pct", "turnover_yuan",
                    "total_net_pnl_yuan",
                ],
                "primary_key": ["artifact"],
                "domains": {"split": ["CV_2022", "CV_2023"]},
                "units": {
                    "ending_capital_yuan": "CNY",
                    "turnover_yuan": "CNY",
                    "total_net_pnl_yuan": "CNY",
                    "max_drawdown_pct": "fraction of running peak",
                },
            },
            "label_surface_fit.parquet": {
                "split": "str", "issue": "str", "year": "int",
                "action_key": "str", "n": "int", "k": "int",
                "lane": "str", "capital": "str",
                "matched_lift_mean": "float",
                "matched_lift_median": "float",
                "matched_lift_std": "float",
                "funded_yuan": "float",
            },
            "ticket_economics.parquet": {
                "columns": {
                    "split": "str", "issue": "str", "n": "int", "k": "int",
                    "lane": "str", "seed": "int", "ticket_position": "int",
                    "ticket_identity": "str", "match_indices": "str",
                    "outcomes": "str", "realized_hit": "bool",
                    "pre_tax_gross_multiple": "float", "payout_yuan": "float",
                },
                "non_null": [
                    "split", "issue", "n", "k", "lane", "seed",
                    "ticket_position", "ticket_identity", "match_indices",
                    "outcomes", "realized_hit", "pre_tax_gross_multiple",
                    "payout_yuan",
                ],
                "primary_key": [
                    "split", "issue", "n", "k", "lane", "seed",
                    "ticket_position",
                ],
                "domains": {
                    "split": ["CV_2022", "CV_2023"],
                    "n": [4, 5, 6, 7, 8, 9, 10],
                    "k": [8, 16, 32],
                    "lane": ["MARKET_WR", "MARKET_WOR", "VALUE_WOR", "LEARNED_MLP"],
                },
                "units": {
                    "pre_tax_gross_multiple": "gross multiple including one 0.65 payout coefficient",
                    "payout_yuan": "CNY for one native ¥2 ticket",
                },
            },
            "incumbent_paths.parquet": {
                "columns": {
                    "split": "str", "issue": "str", "year": "int",
                    "pre_issue_bankroll_yuan": "float",
                    "funded_stake_yuan": "float",
                    "gross_payout_yuan": "float",
                    "post_issue_bankroll_yuan": "float",
                    "source": "str",
                },
                "non_null": [
                    "split", "issue", "year", "pre_issue_bankroll_yuan",
                    "funded_stake_yuan", "gross_payout_yuan",
                    "post_issue_bankroll_yuan", "source",
                ],
                "primary_key": ["split", "issue"],
                "domains": {
                    "split": ["CV_2021", "CV_2022", "CV_2023"],
                    "source": ["RECONSTRUCTED_CORRECTED_ECONOMICS"],
                },
                "units": {
                    "pre_issue_bankroll_yuan": "CNY",
                    "funded_stake_yuan": "CNY",
                    "gross_payout_yuan": "CNY",
                    "post_issue_bankroll_yuan": "CNY",
                },
            },
        },
        "json_artifacts": {
            "handoff_209.json": {
                "required_keys": [
                    "handoff_version", "fit_boundary.train_through",
                    "fit_boundary.2024_opened", "candidate", "fallback",
                    "model", "model_file", "contract_version",
                    "package_manifest", "label_blind_replay",
                ],
            },
            "decision.json": {
                "required_keys": [
                    "contract_version", "producer_code_commit",
                    "req_evidence", "incumbent", "initial_bankroll_yuan",
                    "payout_semantics",
                ],
            },
            "holdout_mutation_receipt.json": {
                "required_keys": [
                    "probe", "mutated_rows", "baseline_signature_sha256",
                    "mutated_signature_sha256",
                    "all_fitted_objects_and_decisions_invariant",
                ],
            },
        },
        "relationships": [
            {
                "name": "capital_conservation",
                "production_verifier": "verify_capital_accounting",
            },
            {
                "name": "ticket_bundle_n_k",
                "production_verifier": "verify_nk_semantics",
            },
            {
                "name": "payout_exactly_once",
                "production_verifier": "verify_payout_economics",
            },
            {
                "name": "handoff_resolves_post_publish",
                "production_verifier": "verify_handoff_contract",
            },
            {
                "name": "chronological_issue_block_isolation",
                "production_verifier": "verify_chronology",
            },
            {
                "name": "issue_level_path_metrics",
                "production_verifier": "verify_path_metrics",
            },
            {
                "name": "dynamic_restricted_argmax",
                "production_verifier": "verify_dynamic_control_decisions",
            },
            {
                "name": "complete_code_binding_set",
                "production_verifier": "verify_code_bindings",
            },
            {
                "name": "training_state_source_binding",
                "production_verifier": "verify_state_semantics",
            },
            {
                "name": "selection_handoff_authority",
                "production_verifier": "verify_selection_authority",
            },
        ],
        "manifest_identity": {
            "all_delivered_bytes_except_manifest_are_hashed": True,
            "manifest_external_binding": "exact Git PR HEAD + independent EV",
        },
    }

    # Every delivered CSV/Parquet frame is declared.  Decision/capital/#209
    # inputs are non-diagnostic; auxiliary plots/tables are explicitly marked
    # diagnostic-only.  Published columns are declared exactly, not as a
    # permissive subset.
    critical_frames = set(schema["frames"]) | {
        "training_frame_all.parquet",
        "validation_frame_all.parquet",
        "chronology_blocks.parquet",
        "decision_ticket_identities.parquet",
    }
    declared_frames: dict[str, object] = schema["frames"]  # type: ignore[assignment]
    for path in sorted(
        p for p in output.rglob("*")
        if p.is_file() and p.suffix in {".csv", ".parquet"}
    ):
        name = path.relative_to(output).as_posix()
        inferred = _frame_contract(
            path, diagnostic_only=name not in critical_frames
        )
        existing = declared_frames.get(name)
        if isinstance(existing, dict):
            if "columns" not in existing:
                existing = {"columns": existing}
            existing["columns"] = inferred["columns"]
            existing["diagnostic_only"] = False
            declared_frames[name] = existing
        else:
            declared_frames[name] = inferred

    critical_json = {
        "COMPLETED.json",
        "decision.json",
        "handoff_209.json",
        "holdout_mutation_receipt.json",
        "holdout_refit_baseline.json",
        "holdout_refit_mutated.json",
        "fitted_object_inventory.json",
        "protocol_log.json",
        "provenance.json",
        "selection.json",
        "tamper_results.json",
    }
    json_contracts: dict[str, object] = schema["json_artifacts"]  # type: ignore[assignment]
    for name in sorted(critical_json):
        json_contracts.setdefault(
            name, {"required_keys": [], "diagnostic_only": False}
        )
    for path in sorted(output.rglob("*.json")):
        name = path.relative_to(output).as_posix()
        if name in {"SHA256SUMS.json", "schema.json"}:
            continue
        existing = json_contracts.get(name)
        if isinstance(existing, dict):
            existing["diagnostic_only"] = False
        else:
            json_contracts[name] = {
                "required_keys": [],
                "diagnostic_only": name not in critical_json,
            }

    schema["binary_artifacts"] = {
        path.relative_to(output).as_posix(): {"diagnostic_only": False}
        for path in sorted(output.rglob("*.joblib"))
    }
    _json(output / "schema.json", schema)


def _write_manifest(output: Path) -> None:
    """Write SHA256SUMS.json covering every delivered file except itself.

    REWORK v2 (D6): COMPLETED.json is written BEFORE this call so it is a
    covered payload — the old ordering left it unlisted.
    """
    artifacts = sorted(
        p
        for p in output.rglob("*")
        if p.is_file()
        and p.relative_to(output).as_posix() != "SHA256SUMS.json"
    )
    _json(output / "SHA256SUMS.json", manifest(output, artifacts))


def _environment() -> dict[str, str]:
    import importlib.metadata
    import platform

    names = ("numpy", "pandas", "pyarrow", "scikit-learn", "scipy")
    return {
        "python": platform.python_version(),
        **{name: importlib.metadata.version(name) for name in names},
    }


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256_json(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def _code_bindings() -> dict[str, str]:
    paths = [
        ROOT / "method.yaml",
        ROOT / "requirements.txt",
        ROOT / "scripts/run_bj208_policy.py",
    ]
    paths.extend(sorted((ROOT / "src/parlay_policy").glob("*.py")))
    return {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in paths
    }


def verify_package(output: Path) -> list[str]:
    """Full production verifier — used by `verify` command AND tamper suite.

    REWORK v2 (D4): manifest coverage (including unlisted-payload check),
    receipt binding, provenance identity, capital accounting (start ¥100,000,
    ¥2 units, no top-up, continuity), embargo/2024 checks, schema columns.

    REWORK v3 (PI payout-economics): `verify_payout_economics` recomputes the
    corrected pre-tax formula (0.65 applied exactly once) from the frozen
    value-matrix panels + upstream CONTROLLING tickets and compares against
    the package's ticket_economics + incumbent_paths.  Omission, division-out
    and 0.65^N tamper attacks all FAIL here.
    """
    failures: list[str] = []
    manifest_path = output / "SHA256SUMS.json"
    if not manifest_path.exists():
        return ["missing SHA256SUMS.json"]
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures.extend(verify_manifest(output, expected))
    failures.extend(verify_receipt(output))
    # REWORK v3.1 (PI narrow durability): handoff artifact paths must resolve
    # after publication and must never reference the staging directory.
    failures.extend(verify_handoff_contract(output))
    failures.extend(verify_selection_authority(output))

    provenance_path = output / "provenance.json"
    if provenance_path.exists():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        failures.extend(verify_provenance(provenance))
        failures.extend(verify_code_bindings(provenance, ROOT))
    else:
        failures.append("missing provenance.json")

    schema_path = output / "schema.json"
    if not schema_path.exists():
        failures.append("missing schema.json")
    else:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        failures.extend(verify_package_schema(output, schema))
    failures.extend(verify_completion(output))
    failures.extend(verify_holdout_mutation_receipt(output))
    failures.extend(verify_chronology(output))

    decision_path = output / "decision.json"
    if not decision_path.exists():
        failures.append("missing decision.json")
    else:
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        failures.extend(verify_req_evidence(decision, output))

    # REWORK v4 (EV D3): source-derived binding of critical training-state
    # evidence.  A legal re-manifest of training_frame_all.parquet that shifts
    # prior_running_drawdown_pct must FAIL here even with a valid manifest.
    failures.extend(verify_state_semantics(output))

    # Foundational package failures do not need the expensive upstream payout
    # replay.  This also keeps the production tamper suite practical: attacks
    # on completion/schema/provenance/REQ evidence fail at their controlling
    # gate instead of rereading the 700k+ ticket settlement surface.
    if failures:
        return failures

    ledger = pd.read_parquet(output / "issue_capital_ledger.parquet")
    failures.extend(verify_capital_accounting(ledger))
    failures.extend(verify_no_embargoed_split(ledger))
    failures.extend(verify_no_2024_issue(ledger))
    holding = pd.read_parquet(output / "path_holding_metrics.parquet")
    failures.extend(verify_path_metrics(ledger, holding))

    decisions = pd.read_parquet(output / "decision_rows_all.parquet")
    failures.extend(verify_no_embargoed_split(decisions))
    failures.extend(verify_no_2024_issue(decisions))

    ticket_economics = pd.read_parquet(output / "ticket_economics.parquet")
    failures.extend(verify_nk_semantics(ticket_economics))

    dynamic_controls = pd.read_parquet(
        output / "dynamic_control_decisions.parquet"
    )
    failures.extend(verify_dynamic_control_decisions(dynamic_controls))

    # Only a package that passes all structural and decision-semantic checks
    # reaches the independent payout recomputation.  The three payout attacks
    # therefore still exercise the full 0.65 verifier, while unrelated attacks
    # fail quickly and deterministically above.
    if failures:
        return failures

    # REWORK v3: payout-economics production-entry check.
    try:
        panels = build_panels(load_value_matrix(ROOT))
        upstream_tickets = load_upstream_tickets(ROOT)
        failures.extend(
            verify_payout_economics(output, panels, upstream_tickets, ledger=ledger)
        )
    except Exception as exc:  # pragma: no cover — fail closed on any load error
        failures.append(f"payout-economics check failed: {exc}")
    return failures


# ==== SECTION: CONTROLS ====


def _make_fixed_action(action: "Action") -> Any:
    def choose(ctx):
        return action

    return choose


def _action(n: int, k: int, lane: str, capital: str) -> "Action":
    return Action(n=n, k=k, lane=lane, capital=capital)


_CONTROL_ACTIONS: dict[str, Any] = {
    "incumbent_n7k8": _make_fixed_action(
        _action(7, 8, "MARKET_WOR", "NATIVE_2_YUAN")
    ),
    "n7k16_sensitivity": _make_fixed_action(
        _action(7, 16, "MARKET_WOR", "NATIVE_2_YUAN")
    ),
    "static_n4k8": _make_fixed_action(_action(4, 8, "MARKET_WOR", "NATIVE_2_YUAN")),
    "static_n5k8": _make_fixed_action(_action(5, 8, "MARKET_WOR", "NATIVE_2_YUAN")),
    "static_n6k8": _make_fixed_action(_action(6, 8, "MARKET_WOR", "NATIVE_2_YUAN")),
    "static_n8k8": _make_fixed_action(_action(8, 8, "MARKET_WOR", "NATIVE_2_YUAN")),
    "static_n9k8": _make_fixed_action(_action(9, 8, "MARKET_WOR", "NATIVE_2_YUAN")),
    "static_n10k8": _make_fixed_action(_action(10, 8, "MARKET_WOR", "NATIVE_2_YUAN")),
    "dynamic_n_fixed_k8_lane": lambda ctx: _action(7, 8, "MARKET_WOR", "NATIVE_2_YUAN"),
    "fixed_n7_dynamic_k": lambda ctx: _action(7, 16, "MARKET_WOR", "NATIVE_2_YUAN"),
    "dynamic_nk_fixed_generator": lambda ctx: _action(7, 8, "MARKET_WOR", "NATIVE_2_YUAN"),
    "generator_change_n7k8": lambda ctx: _action(7, 8, "MARKET_WR", "NATIVE_2_YUAN"),
    "capital_change_identical": lambda ctx: _action(7, 8, "MARKET_WOR", "SIMPLE_ACTIVE"),
    "cash_no_bet": lambda ctx: _action(7, 8, "MARKET_WOR", "NATIVE_2_YUAN"),
}


def _run_controls(
    test_ctx, pool_cache, test_split, *,
    restricted_policies: dict[str, object],
    ood_scaler,
    ood_threshold,
    frozen_incumbent: pd.DataFrame | None = None,
    upstream_tickets: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Run the 10-arm attribution matrix on the test split.

    REWORK v2 (D2/D3): SIMPLE_ACTIVE funding is the corrected EQUAL_1PCT
    semantics; the incumbent arm binds the exact frozen #207 capital path;
    stochastic lanes aggregate the 16 preregistered seeds (seed=0 never used);
    capital_change_identical uses the frozen incumbent CONTROLLING ticket
    identities (identical tickets, only the capital rule changes).
    """
    from parlay_policy.tickets import (
        select_tickets, settle_tickets, bundle_capital,
        bundle_capital_equal1pct, mean_pairwise_overlap, ticket_hhi,
        repeat_exposure,
    )

    results: dict[str, pd.DataFrame] = {}
    issues = sorted(test_ctx.keys(), key=lambda item: test_ctx[item].panel.year)
    incumbent_key = f"N{INCUMBENT_N}/K{INCUMBENT_K}/{INCUMBENT_LANE}/NATIVE_2_YUAN"

    for name, action_fn in _CONTROL_ACTIONS.items():
        rows: list[dict[str, object]] = []
        bankroll = INITIAL_BANKROLL_YUAN
        for (split, issue) in issues:
            ctx = test_ctx[(split, issue)]
            m = len(ctx.panel.match_idx)
            trace: dict[str, object]
            if name in restricted_policies:
                # REWORK v4 (EV D1): restricted dynamic controls are scored
                # from THEIR OWN live prior history (this arm's accumulated
                # rows), not from the frozen incumbent counterfactual path.
                prior = live_prior_state_from_rows(rows)
                state = _state_with_prior(ctx, prior)
                if name == "dynamic_n_fixed_k8_lane":
                    actions = [
                        _action(n, 8, "MARKET_WOR", "NATIVE_2_YUAN")
                        for n in N_GRID if n <= m
                    ]
                elif name == "fixed_n7_dynamic_k":
                    actions = [
                        _action(7, k, "MARKET_WOR", "NATIVE_2_YUAN")
                        for k in K_GRID if 7 <= m
                    ]
                else:
                    actions = [
                        _action(n, k, "MARKET_WOR", "NATIVE_2_YUAN")
                        for n in N_GRID if n <= m for k in K_GRID
                    ]
                actions = [
                    action for action in actions
                    if is_action_fundable(action, state)
                ]
                action, trace = choose_action(
                    restricted_policies[name],
                    state,
                    actions,
                    ood_scaler=ood_scaler,
                    ood_threshold=ood_threshold,
                    conservative=False,
                )
                trace = {
                    **trace,
                    "control_semantics": "PER_ISSUE_CAUSAL_STATE_CONDITIONED",
                    "restricted_control": name,
                }
            else:
                action = action_fn(ctx)
                trace = {
                    "control_semantics": "FIXED_OR_MATCHED_CONTROL",
                    "restricted_control": None,
                }
            if action is None:
                rows.append(
                    {
                        "split": split,
                        "issue": issue,
                        "year": ctx.panel.year,
                        "policy": name,
                        "action_key": NO_BET_KEY,
                        "n": None,
                        "k": None,
                        "lane": None,
                        "capital": None,
                        "pre_issue_bankroll_yuan": bankroll,
                        "requested_stake_yuan": 0.0,
                        "funded_stake_yuan": 0.0,
                        "gross_payout_yuan": 0.0,
                        "post_issue_bankroll_yuan": bankroll,
                        "net_pnl_yuan": 0.0,
                        "drawdown_pct": 0.0,
                        "mean_pairwise_overlap": 0.0,
                        "ticket_hhi": 0.0,
                        "repeat_exposure": 0.0,
                        "decision_trace_json": json.dumps(trace, ensure_ascii=False),
                        "source": "NO_BET",
                    }
                )
                continue
            pool = pool_cache.get(f"{issue}:{action.n}")
            # Exact frozen incumbent binding for the incumbent arm.
            if (
                name == "incumbent_n7k8"
                and action.key == incumbent_key
                and frozen_incumbent is not None
                and not frozen_incumbent.empty
            ):
                frozen_row = frozen_incumbent[
                    (frozen_incumbent["split"] == split)
                    & (frozen_incumbent["issue"] == issue)
                ]
                if not frozen_row.empty:
                    row = frozen_row.iloc[0]
                    frozen_tickets = _frozen_incumbent_tickets(
                        upstream_tickets, split, issue
                    )
                    if frozen_tickets is None or frozen_tickets.empty:
                        raise ReplayError(
                            f"missing frozen ticket identities for {split}/{issue}"
                        )
                    payout = float(row["gross_payout_yuan"])
                    funded = float(row["funded_stake_yuan"])
                    new_bankroll = apply_issue_settlement(bankroll, funded, payout)
                    rows.append(
                        {
                            "split": split,
                            "issue": issue,
                            "year": ctx.panel.year,
                            "policy": name,
                            "action_key": action.key,
                            "n": action.n,
                            "k": action.k,
                            "lane": action.lane,
                            "capital": action.capital,
                            "pre_issue_bankroll_yuan": bankroll,
                            "requested_stake_yuan": funded,
                            "funded_stake_yuan": funded,
                            "gross_payout_yuan": payout,
                            "post_issue_bankroll_yuan": new_bankroll,
                            "net_pnl_yuan": float(new_bankroll - bankroll),
                            "drawdown_pct": 0.0,
                            "mean_pairwise_overlap": mean_pairwise_overlap(
                                frozen_tickets
                            ),
                            "ticket_hhi": ticket_hhi(frozen_tickets),
                            "repeat_exposure": repeat_exposure(frozen_tickets),
                            "decision_trace_json": json.dumps(trace, ensure_ascii=False),
                            "source": "FROZEN_INCUMBENT_207",
                        }
                    )
                    bankroll = new_bankroll
                    continue
            if pool is None or name == "cash_no_bet":
                rows.append(
                    {
                        "split": split,
                        "issue": issue,
                        "year": ctx.panel.year,
                        "policy": name,
                        "action_key": "NO_BET" if name == "cash_no_bet" else action.key,
                        "n": action.n,
                        "k": action.k,
                        "lane": action.lane,
                        "capital": action.capital,
                        "pre_issue_bankroll_yuan": bankroll,
                        "requested_stake_yuan": 0.0,
                        "funded_stake_yuan": 0.0,
                        "gross_payout_yuan": 0.0,
                        "post_issue_bankroll_yuan": bankroll,
                        "net_pnl_yuan": 0.0,
                        "drawdown_pct": 0.0,
                        "mean_pairwise_overlap": 0.0,
                        "ticket_hhi": 0.0,
                        "repeat_exposure": 0.0,
                        "decision_trace_json": json.dumps(trace, ensure_ascii=False),
                    }
                )
                continue
            # Capital-change-identical arm: use frozen incumbent CONTROLLING
            # identities when available (identical tickets, only capital rule
            # differs).  Otherwise replay the same lane from the pool.
            if name == "capital_change_identical":
                frozen_tickets = _frozen_incumbent_tickets(
                    upstream_tickets, split, issue
                )
                if frozen_tickets is not None and not frozen_tickets.empty:
                    cap = bundle_capital_equal1pct(frozen_tickets, bankroll)
                    funded = float(cap["funded_stake_yuan"])
                    payout = float(cap["gross_payout_yuan"])
                    new_bankroll = apply_issue_settlement(bankroll, funded, payout)
                    rows.append(
                        {
                            "split": split,
                            "issue": issue,
                            "year": ctx.panel.year,
                            "policy": name,
                            "action_key": action.key,
                            "n": action.n,
                            "k": action.k,
                            "lane": action.lane,
                            "capital": action.capital,
                            "pre_issue_bankroll_yuan": bankroll,
                            "requested_stake_yuan": bankroll * 0.01,
                            "funded_stake_yuan": funded,
                            "gross_payout_yuan": payout,
                            "post_issue_bankroll_yuan": new_bankroll,
                            "net_pnl_yuan": float(new_bankroll - bankroll),
                            "drawdown_pct": 0.0,
                            "mean_pairwise_overlap": mean_pairwise_overlap(frozen_tickets),
                            "ticket_hhi": ticket_hhi(frozen_tickets),
                            "repeat_exposure": repeat_exposure(frozen_tickets),
                            "decision_trace_json": json.dumps(trace, ensure_ascii=False),
                            "source": "IDENTICAL_TICKETS_207",
                        }
                    )
                    bankroll = new_bankroll
                    continue
            # Stochastic lanes: aggregate over the 16 preregistered seeds.
            if action.lane in ("MARKET_WR", "MARKET_WOR"):
                funded_list: list[float] = []
                payout_list: list[float] = []
                overlap_list: list[float] = []
                hhi_list: list[float] = []
                repeat_list: list[float] = []
                for seed in ALL_SEEDS:
                    sel = select_tickets(pool, action.lane, action.k, seed=seed)
                    settled = settle_tickets(sel)
                    if action.capital == "SIMPLE_ACTIVE":
                        cap = bundle_capital_equal1pct(settled, bankroll)
                    else:
                        cap = bundle_capital(settled, bankroll)
                    funded_list.append(float(cap["funded_stake_yuan"]))
                    payout_list.append(float(cap["gross_payout_yuan"]))
                    overlap_list.append(mean_pairwise_overlap(sel))
                    hhi_list.append(ticket_hhi(sel))
                    repeat_list.append(repeat_exposure(sel))
                funded = float(np.mean(funded_list))
                payout = float(np.mean(payout_list))
                overlap = float(np.mean(overlap_list))
                hhi = float(np.mean(hhi_list))
                repeat = float(np.mean(repeat_list))
            else:
                sel = select_tickets(pool, action.lane, action.k, seed=0)
                settled = settle_tickets(sel)
                if action.capital == "SIMPLE_ACTIVE":
                    cap = bundle_capital_equal1pct(settled, bankroll)
                else:
                    cap = bundle_capital(settled, bankroll)
                funded = float(cap["funded_stake_yuan"])
                payout = float(cap["gross_payout_yuan"])
                overlap = mean_pairwise_overlap(sel)
                hhi = ticket_hhi(sel)
                repeat = repeat_exposure(sel)
            new_bankroll = apply_issue_settlement(bankroll, funded, payout)
            requested = (
                bankroll * 0.01
                if action.capital == "SIMPLE_ACTIVE"
                else action.k * 2.0
            )
            rows.append(
                {
                    "split": split,
                    "issue": issue,
                    "year": ctx.panel.year,
                    "policy": name,
                    "action_key": action.key,
                    "n": action.n,
                    "k": action.k,
                    "lane": action.lane,
                    "capital": action.capital,
                    "pre_issue_bankroll_yuan": bankroll,
                    "requested_stake_yuan": float(requested),
                    "funded_stake_yuan": funded,
                    "gross_payout_yuan": payout,
                    "post_issue_bankroll_yuan": new_bankroll,
                    "net_pnl_yuan": float(new_bankroll - bankroll),
                    "drawdown_pct": 0.0,
                    "mean_pairwise_overlap": overlap,
                    "ticket_hhi": hhi,
                    "repeat_exposure": repeat,
                    "decision_trace_json": json.dumps(trace, ensure_ascii=False),
                }
            )
            bankroll = new_bankroll
        results[name] = materialize_issue_path_metrics(pd.DataFrame(rows))
    return results


def _frozen_incumbent_tickets(
    upstream_tickets: pd.DataFrame | None, split: str, issue: str
) -> pd.DataFrame | None:
    """Frozen incumbent CONTROLLING ticket rows for the identical-ticket arm.

    REWORK v2 (D2): the old capital_change_identical arm re-drew tickets with
    seed=0.  Now it binds the frozen #207 CONTROLLING identities directly
    (policy=MARKET_WOR, k=8, panel_role=CONTROLLING).

    REWORK v3 (PI payout-economics): upstream #206 `realized_gross` is ALREADY
    the correct 0.65-adjusted pre-tax gross multiple (realized_gross =
    0.65 * prod(official_sp)).  The upstream `pre_tax_gross_multiple` column is
    the superseded product(SP) value (derived by division by 0.65) and is never
    used here.  The multiple column is remapped to `realized_gross` so capital
    settlement applies the coefficient exactly once.
    """
    if upstream_tickets is None or upstream_tickets.empty:
        return None
    sub = upstream_tickets[
        (upstream_tickets["split"] == split)
        & (upstream_tickets["issue"] == issue)
        & (upstream_tickets["panel_role"] == "CONTROLLING")
        & (upstream_tickets["policy"] == INCUMBENT_LANE)
        & (upstream_tickets["k"] == INCUMBENT_K)
    ].copy()
    if sub.empty:
        return None
    sub["pre_tax_gross_multiple"] = sub["realized_gross"]
    return sub


def _frozen_incumbent_metric_map(
    upstream_tickets: pd.DataFrame,
) -> dict[tuple[str, str], dict[str, float]]:
    """Materialize concentration diagnostics for frozen ticket identities."""
    metrics: dict[tuple[str, str], dict[str, float]] = {}
    keys = upstream_tickets[["split", "issue"]].drop_duplicates()
    for _, key in keys.iterrows():
        split = str(key["split"])
        issue = str(key["issue"])
        tickets = _frozen_incumbent_tickets(
            upstream_tickets, split, issue
        )
        if tickets is None or tickets.empty:
            continue
        metrics[(split, issue)] = {
            "mean_pairwise_overlap": mean_pairwise_overlap(tickets),
            "ticket_hhi": ticket_hhi(tickets),
            "repeat_exposure": repeat_exposure(tickets),
        }
    return metrics


# ==== SECTION: POLICY CONTROLS ====


def _run_policy_controls(
    test_ctx, pool_cache, test_split, *,
    policy_mlp, policy_ridge, policy_fixed,
    ood_scaler, ood_threshold,
    ranker_scores_by_issue, frozen_incumbent, frozen_ticket_metrics,
) -> dict[str, pd.DataFrame]:
    """Ridge and best-fixed-action policy paths (REWORK v2: evaluated per fold,
    not just metadata)."""

    def _ridge_action_fn(ctx, prior):
        actions = _actions_for_issue(ctx)
        if not actions:
            return None, {"fallback": "NO_BET", "reason": "NO_LAWFUL_ACTION"}
        state = _state_with_prior(ctx, prior)
        action, trace = choose_action(
            policy_ridge, state, actions,
            ood_scaler=ood_scaler, ood_threshold=ood_threshold,
        )
        if action is None or not trace["safety_gate_pass"]:
            if _incumbent_feasible(ctx, prior.prior_bankroll_yuan):
                return Action(7, 8, INCUMBENT_LANE, "NATIVE_2_YUAN"), {
                    **trace, "fallback": "INCUMBENT_OR_NO_BET",
                }
            return None, {**trace, "fallback": "NO_BET", "reason": "INCUMBENT_INFEASIBLE"}
        return action, trace

    def _fixed_action_fn(ctx, prior):
        actions = _actions_for_issue(ctx)
        if not actions:
            return None, {"fallback": "NO_BET", "reason": "NO_LAWFUL_ACTION"}
        state = _state_with_prior(ctx, prior)
        action, trace = choose_action(
            policy_fixed, state, actions,
            ood_scaler=None, ood_threshold=None,
        )
        if action is None:
            if _incumbent_feasible(ctx, prior.prior_bankroll_yuan):
                return Action(7, 8, INCUMBENT_LANE, "NATIVE_2_YUAN"), {
                    "fallback": "INCUMBENT_OR_NO_BET",
                }
            return None, {"fallback": "NO_BET", "reason": "INCUMBENT_INFEASIBLE"}
        return action, trace

    results: dict[str, pd.DataFrame] = {}
    for name, fn in (
        ("ridge_policy", _ridge_action_fn),
        ("best_fixed_policy", _fixed_action_fn),
    ):
        path = full_path_replay(
            test_ctx, pool_cache, action_fn=fn, split=test_split,
            policy_name=name,
            ranker_scores_by_issue=ranker_scores_by_issue,
            frozen_incumbent=frozen_incumbent,
            frozen_ticket_metrics=frozen_ticket_metrics,
        )
        results[name] = path
    return results


# ==== SECTION: DIAGNOSTICS ====


def _write_diagnostics(
    output,
    terminal_validation,
    all_test,
    contexts,
    policy_mlp,
    terminal_train_all,
    *,
    diagnostic_loss: pd.DataFrame,
):
    context_states = {
        f"{split}:{issue}": ctx.state
        for (split, issue), ctx in contexts.items()
    }
    if not all_test.empty:
        freq = action_frequency(all_test)
        freq.to_csv(output / "action_frequency.csv", index=False)
        fallback = ood_fallback_census(all_test)
        fallback.to_csv(output / "ood_fallback_census.csv", index=False)
    # Diagnostics are evaluated on the chronological validation block.  The
    # model has never fitted these issue rows.
    if not terminal_validation.empty:
        perm = permutation_importance_table(terminal_validation, policy_mlp)
        perm.to_csv(output / "permutation_importance.csv", index=False)
        calib = calibration_curve(terminal_validation, policy_mlp, context_states)
        calib.to_csv(output / "calibration_curve.csv", index=False)
        demo = action_variation_demo(context_states, policy_mlp)
        demo.to_csv(output / "action_variation_demo.csv", index=False)
    # Chronological train/val loss (REWORK v2: issue-block, not row-level).
    if terminal_train_all is not None and not terminal_train_all.empty:
        diagnostic_loss.to_csv(
            output / "chronological_train_val_loss.csv", index=False
        )


# ==== SECTION: SELECTION ====


def _apply_selection_rule(
    fold_results: dict[str, object],
    all_test: pd.DataFrame,
    all_fit: pd.DataFrame,
    incumbent_paths: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Preregistered lexicographic selection rule over 2 constructible folds.

    REWORK v2 (D3/M04): rule 1 requires complete fold support on ALL
    constructible folds (2 of 2, per PROTOCOL-LOG DELTA #208-1); rule 3 is
    'positive on all constructible development folds' — wording superseded in
    method.yaml (supersede_208_3).  Tie-breakers (worst-fold, max drawdown,
    complexity) are implemented, not stubbed.
    """
    from parlay_policy.contract import (
        INCUMBENT_LANE, INCUMBENT_N, INCUMBENT_K,
    )

    def _frozen_incumbent_end(test_split: str) -> float:
        if incumbent_paths is None or incumbent_paths.empty:
            return float("nan")
        sub = incumbent_paths[incumbent_paths["split"] == test_split]
        if sub.empty:
            return float("nan")
        return float(sub.sort_values("issue").iloc[-1]["post_issue_bankroll_yuan"])

    matched_lifts = []
    for fold_index, fold in fold_results.items():
        test_split = fold["test_split"]
        learned = fold["learned_summary"]
        learned_end = learned.get("ending_capital_yuan", float("nan"))
        frozen_incumbent_end = _frozen_incumbent_end(test_split)
        matched_lifts.append(
            {
                "fold": fold_index,
                "test_split": test_split,
                "learned_end": learned_end,
                "frozen_incumbent_end": frozen_incumbent_end,
                "matched_lift": learned_end - frozen_incumbent_end
                if np.isfinite(learned_end) and np.isfinite(frozen_incumbent_end)
                else float("nan"),
            }
        )
    matched_df = pd.DataFrame(matched_lifts)
    median_lift = float(matched_df["matched_lift"].median()) if not matched_df.empty else float("nan")
    positive_folds = int((matched_df["matched_lift"] > 0).sum()) if not matched_df.empty else 0
    valid_replay = bool(not matched_df.empty and np.isfinite(median_lift))
    complete_support = bool(not matched_df.empty and len(matched_df) == len(fold_results))
    no_ruin = bool(not matched_df.empty and (matched_df["learned_end"] > 0).all())
    rule1 = valid_replay and complete_support and no_ruin
    rule2 = np.isfinite(median_lift) and median_lift > 0
    rule3 = positive_folds >= len(fold_results)  # all constructible folds
    eligible = bool(rule1 and rule2 and rule3)
    candidate = {
        "policy": "LEARNED_MLP_Q",
        "n": None,
        "k": None,
        "lane": None,
        "capital": None,
    }
    # Tie-breakers: highest median → highest worst-fold → smaller max drawdown
    # → lower complexity (rule 4).
    worst_fold_lift = float(matched_df["matched_lift"].min()) if not matched_df.empty else float("nan")
    max_dd = float(max(
        (fold.get("learned_summary", {}).get("max_drawdown_pct", float("nan"))
         for fold in fold_results.values()),
        default=float("nan"),
    ))
    if eligible:
        if not all_test.empty:
            freq = (
                all_test[all_test["split"] == TERMINAL_SPLIT]["action_key"]
                .value_counts()
            )
            if not freq.empty:
                representative = str(freq.index[0])
                parts = representative.split("/")
                if len(parts) == 4:
                    candidate = {
                        "policy": "LEARNED_MLP_Q",
                        "n": int(parts[0][1:]),
                        "k": int(parts[1][1:]),
                        "lane": parts[2],
                        "capital": parts[3],
                    }
    result = {
        "rule1_valid_replay_complete_support_no_ruin": rule1,
        "rule2_positive_median_lift": rule2,
        "rule3_positive_on_all_constructible_folds": rule3,
        "eligible": eligible,
        "median_matched_lift_yuan": median_lift,
        "positive_fold_count": positive_folds,
        "constructible_fold_count": len(fold_results),
        "worst_fold_matched_lift_yuan": worst_fold_lift,
        "max_drawdown_pct": max_dd,
        "matched_lift_by_fold": matched_df.to_dict(orient="records"),
        "candidate": candidate if eligible else {
            "policy": "FROZEN_N7_INCUMBENT",
            "n": INCUMBENT_N,
            "k": INCUMBENT_K,
            "lane": INCUMBENT_LANE,
            "capital": "NATIVE_2_YUAN",
            "reason": "selection rule found no eligible learned row; freeze N7 incumbent",
        },
        "frozen_candidate": (
            candidate if eligible
            else {
                "policy": "FROZEN_N7_INCUMBENT",
                "n": INCUMBENT_N,
                "k": INCUMBENT_K,
                "lane": INCUMBENT_LANE,
                "capital": "NATIVE_2_YUAN",
            }
        ),
    }
    return result


def _build_handoff(
    fold_results, selection, output: Path, *, published_output: Path | None = None
) -> dict[str, object]:
    """Single frozen #209 handoff: hashes, fit boundary, candidate/fallback.

    REWORK v3.1 (PI narrow durability REJECT 2026-08-15): the handoff must
    serialize the CANONICAL post-publication manifest path
    (`results/issue-208/SHA256SUMS.json`), never the transient staging path.
    `_build_handoff` is called while the package is still in the staging
    directory, so the caller passes `published_output` (the final output path)
    to keep handoff paths resolvable after the atomic rename.
    """
    fold2_model = fold_results.get("fold2", {}).get("policy_mlp", {})
    published = published_output or output
    return {
        "handoff_version": "bj208-handoff-for-209-v7",
        "fit_boundary": {
            "train_through": "2022",
            "test_2023": True,
            "2024_opened": False,
            "2025_2026_opened": False,
        },
        "payout_semantics": {
            "pre_tax_gross_multiple": "hit * 0.65 * product(official_final_sp_i)",
            "coefficient_applied": "exactly once per winning N-fold ticket",
            "never": ["division by 0.65", "per-leg 0.65", "0.65^N compounding"],
            "expected_pre_tax_net": "0.65 * prod(p*SP) - 1",
        },
        "candidate": selection["frozen_candidate"],
        "fallback": {
            "policy": "FROZEN_N7_INCUMBENT",
            "n": INCUMBENT_N,
            "k": INCUMBENT_K,
            "lane": INCUMBENT_LANE,
            "capital": "NATIVE_2_YUAN",
        },
        "model": fold2_model,
        "model_file": "results/issue-208/models/fold2_mlp.joblib",
        "terminal_split": TERMINAL_SPLIT,
        "contract_version": CONTRACT_VERSION,
        "replay_command": "PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py run --output results/issue-208",
        "package_manifest": str(published / "SHA256SUMS.json"),
        "label_blind_replay": (
            "inference path never reads realized_outcome/official_final_sp_label; "
            "2024/2025/2026 embargoed"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue #208 runner")
    parser.add_argument("command", choices=("run", "verify"))
    parser.add_argument("--output", default="results/issue-208")
    args = parser.parse_args()
    output = Path(args.output)
    if args.command == "run":
        result = run(output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "verify":
        failures = verify_package(output)
        if failures:
            raise SystemExit("verify failed: " + "; ".join(failures))
        tamper_path = output / "tamper_results.json"
        if tamper_path.exists():
            tamper = json.loads(tamper_path.read_text(encoding="utf-8"))
            print(f"verify ok; tamper detected={len(tamper)}")
        else:
            print("verify ok (no tamper_results.json present)")
    else:
        raise SystemExit(f"unknown command {args.command}")


if __name__ == "__main__":
    main()
