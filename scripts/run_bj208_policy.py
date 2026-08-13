"""Issue #208 staged runner: census → counterfactual surface → controls →
learned policy → diagnostics → selection → immutable package.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py run --output results/issue-208
  PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py verify --output results/issue-208
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import time
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from parlay_policy.contract import (  # noqa: E402
    Action,
    CONTRACT_VERSION,
    DEVELOPMENT_SPLITS,
    FIT_SPLIT,
    FOLDS,
    INCUMBENT_K,
    INCUMBENT_LANE,
    INCUMBENT_N,
    INITIAL_BANKROLL_YUAN,
    MODEL_SEED,
    SELECTION_SPLIT,
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
    ood_gate,
    serialize_policy,
)
from parlay_policy.replay import (  # noqa: E402
    ReplayError,
    build_issue_contexts,
    build_label_surface,
    build_pool_cache,
    build_training_frame,
    full_path_replay,
    summarize_path,
)
from parlay_policy.tickets import (  # noqa: E402
    fit_learned_ranker,
    ranker_scores,
)
from parlay_policy.contract import N_GRID  # noqa: E402
from parlay_policy.verify import (  # noqa: E402
    VerifyError,
    manifest,
    run_tamper_suite,
    sha256_file,
    verify_capital_accounting,
    verify_manifest,
    verify_nk_semantics,
    verify_no_2024_issue,
    verify_no_embargoed_split,
    verify_schema,
)
from parlay_policy.diagnostics import (  # noqa: E402
    action_frequency,
    action_variation_demo,
    calibration_curve,
    ood_fallback_census,
    permutation_importance_table,
)


def _json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        import os

        os.fsync(handle.fileno())


def _fsync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            _fsync_file(path)


def run(output: Path) -> dict[str, object]:
    started = time.time()
    output = Path(output)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    # --- Stage 1: census ----------------------------------------------------
    vm = load_value_matrix(ROOT)
    panels = build_panels(vm)
    census = census_table(panels)
    elig = eligibility(panels)
    census.to_csv(output / "census.csv", index=False)
    elig.to_csv(output / "eligibility.csv", index=False)
    upstream_tickets = load_upstream_tickets(ROOT)
    upstream_ledger = load_upstream_ledger(ROOT)
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
    ranker = fit_learned_ranker(
        _ranker_training_tickets(contexts, pool_cache, (FIT_SPLIT,))
    )
    surface_fit = build_label_surface(
        contexts, pool_cache, train_splits=(FIT_SPLIT,), ranker=ranker
    )
    train_fit = build_training_frame(surface_fit, contexts)
    surface_fit.to_parquet(output / "label_surface_fit.parquet", index=False)

    # --- Stage 4: chronological folds ---------------------------------------
    fold_results: dict[str, object] = {}
    fit_rows: list[pd.DataFrame] = []
    test_rows: list[pd.DataFrame] = []
    for fold_index, (train_splits, test_split) in enumerate(FOLDS):
        ranker_fold = fit_learned_ranker(
            _ranker_training_tickets(contexts, pool_cache, train_splits)
        )
        surface_train = build_label_surface(
            contexts, pool_cache, train_splits=train_splits, ranker=ranker_fold
        )
        surface_test = build_label_surface(
            contexts, pool_cache, train_splits=(test_split,), ranker=ranker_fold
        )
        train_df = build_training_frame(surface_train, contexts)
        test_df = build_training_frame(surface_test, contexts)

        policy_mlp = fit_policy(train_df, kind="MLP", seed=MODEL_SEED)
        policy_ridge = fit_policy(train_df, kind="RIDGE", seed=MODEL_SEED)
        fixed_key = best_fixed_action_key(train_df)
        policy_fixed = fit_policy(
            train_df, kind="FIXED_ACTION", fixed_action_key=fixed_key
        )

        # OOD gate from fit-fold states.
        fit_states = [
            contexts[(split, issue)].state
            for (split, issue), ctx in contexts.items()
            if split in train_splits
        ]
        ood_scaler, ood_threshold = ood_gate(fit_states, fit_states)

        test_ctx = {
            (split, issue): ctx
            for (split, issue), ctx in contexts.items()
            if split == test_split
        }
        test_issues = sorted(
            test_ctx.keys(), key=lambda item: test_ctx[item].panel.year
        )
        decision_rows: list[dict[str, object]] = []
        for (split, issue) in test_issues:
            ctx = test_ctx[(split, issue)]
            actions = _actions_for_issue(ctx)
            action, trace = choose_action(
                policy_mlp,
                ctx.state,
                actions,
                ood_scaler=ood_scaler,
                ood_threshold=ood_threshold,
            )
            decision_rows.append(
                {
                    "split": split,
                    "issue": issue,
                    "year": ctx.panel.year,
                    "action_key": action.key,
                    "n": action.n,
                    "k": action.k,
                    "lane": action.lane,
                    "capital": action.capital,
                    "predicted_lift": trace["predicted_lift"],
                    "conservative_lift": trace["conservative_lift"],
                    "ood_statistic": trace["ood_statistic"],
                    "ood_threshold": trace["ood_threshold"],
                    "safety_gate_pass": trace["safety_gate_pass"],
                    "fallback": trace["fallback"],
                    "decision_trace_json": json.dumps(trace, ensure_ascii=False),
                }
            )
        decision_df = pd.DataFrame(decision_rows)
        decision_df.to_parquet(
            output / f"decision_fold{fold_index + 1}.parquet", index=False
        )

        # Full-path replay of the learned policy on the test split.
        ranker_scores_test: dict[str, np.ndarray] = {}
        for (split, issue), ctx in test_ctx.items():
            for n in N_GRID:
                pool = pool_cache.get(f"{issue}:{n}")
                if pool is not None:
                    ranker_scores_test[f"{issue}:{n}"] = ranker_scores(
                        ranker_fold, pool
                    )

        def _learned_action_fn(ctx, bankroll):
            actions = _actions_for_issue(ctx)
            action, trace = choose_action(
                policy_mlp, ctx.state, actions, ood_scaler=ood_scaler,
                ood_threshold=ood_threshold,
            )
            if not trace["safety_gate_pass"]:
                # Baseline-residual safety gate: fall back to the frozen
                # incumbent N7/K8/native-¥2 action, never execute the argmax
                # action on a non-positive conservative predicted lift.
                fallback_action = Action(
                    7, 8, INCUMBENT_LANE, "NATIVE_2_YUAN"
                )
                trace["fallback_action"] = fallback_action.key
                trace["fallback"] = "INCUMBENT_OR_NO_BET"
                return fallback_action, trace
            return action, trace

        path_learned = full_path_replay(
            test_ctx, pool_cache, action_fn=_learned_action_fn, split=test_split,
            policy_name="learned_policy",
            ranker_scores_by_issue=ranker_scores_test,
            frozen_incumbent=incumbent_paths,
        )
        path_learned.to_parquet(
            output / f"path_learned_fold{fold_index + 1}.parquet", index=False
        )

        # Controls on the same test split.
        control_paths = _run_controls(
            test_ctx, pool_cache, test_split, train_frames=train_df,
            frozen_incumbent=incumbent_paths,
        )
        for name, path in control_paths.items():
            path.to_parquet(output / f"path_control_{name}_fold{fold_index + 1}.parquet", index=False)

        fold_results[f"fold{fold_index + 1}"] = {
            "train_splits": list(train_splits),
            "test_split": test_split,
            "learned_summary": summarize_path(path_learned),
            "control_summaries": {
                name: summarize_path(path)
                for name, path in control_paths.items()
            },
            "fixed_action_key": fixed_key,
            "policy_mlp": serialize_policy(policy_mlp),
            "policy_ridge": serialize_policy(policy_ridge),
            "policy_fixed": {
                "model_kind": "FIXED_ACTION",
                "fixed_action_key": fixed_key,
            },
            "ood_threshold": ood_threshold,
        }
        fit_rows.append(train_df)
        test_rows.append(decision_df)
        print(
            f"[stage4 fold{fold_index + 1}] train={train_splits} test={test_split} "
            f"learned ending={summarize_path(path_learned).get('ending_capital_yuan', float('nan')):.2f}"
        )

    # --- Stage 5: diagnostics -----------------------------------------------
    all_fit = pd.concat(fit_rows, ignore_index=True)
    all_fit.to_parquet(output / "training_frame_all.parquet", index=False)
    all_test = pd.concat(test_rows, ignore_index=True)
    all_test.to_parquet(output / "decision_rows_all.parquet", index=False)
    _write_diagnostics(output, all_fit, all_test, contexts, policy_mlp)

    # Consolidated capital ledger for verification + tamper targeting.
    ledger_parts = [
        pd.read_parquet(path)
        for path in sorted(output.glob("path_learned_fold*.parquet"))
    ]
    for path in sorted(output.glob("path_control_*_fold*.parquet")):
        ledger_parts.append(pd.read_parquet(path))
    consolidated = pd.concat(ledger_parts, ignore_index=True)
    consolidated.to_parquet(output / "issue_capital_ledger.parquet", index=False)

    # --- Stage 6: selection rule + #209 handoff ------------------------------
    selection = _apply_selection_rule(
        fold_results, all_test, all_fit, incumbent_paths=incumbent_paths
    )
    _json(output / "selection.json", selection)
    handoff = _build_handoff(fold_results, selection, output)
    _json(output / "handoff_209.json", handoff)

    # --- Stage 7: package metadata + verification ----------------------------
    decision = {
        "contract_version": CONTRACT_VERSION,
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
        "selection": selection,
        "initial_bankroll_yuan": INITIAL_BANKROLL_YUAN,
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
            "environment": _environment(),
        },
    )

    # manifest after all artifacts (include method.yaml + schema.json)
    shutil.copy2(ROOT / "method.yaml", output / "method.yaml")
    artifacts = sorted(
        p
        for p in output.glob("*")
        if p.is_file() and p.name != "SHA256SUMS.json"
    )
    _json(output / "SHA256SUMS.json", manifest(output, artifacts))
    # Plain-text receipt for method_preflight protocol-hash binding.
    method_hash = sha256_file(output / "method.yaml")
    (output / "receipt.sha256").write_text(
        f"{method_hash}  method.yaml\n", encoding="utf-8"
    )

    # verify package + tamper
    failures = verify_package(output)
    if failures:
        raise VerifyError("package verification failed: " + "; ".join(failures))
    tamper_results = run_tamper_suite(output)
    _json(output / "tamper_results.json", tamper_results)
    if not all(result["detected"] for result in tamper_results):
        raise VerifyError("tamper suite did not detect all attacks")
    print(f"[stage7 verify] package ok; tamper detected={len(tamper_results)}")
    print(f"[done] elapsed {time.time() - started:.1f}s -> {output}")
    return {"status": "ok", "output": str(output)}


def _ranker_training_tickets(contexts, pool_cache, train_splits):
    rows = []
    for (split, issue), ctx in contexts.items():
        if split not in train_splits:
            continue
        pool = pool_cache.get(f"{issue}:7")
        if pool is None:
            continue
        sub = pool.copy()
        sub["labels_available"] = ctx.panel.labels_available
        rows.append(sub)
    return pd.concat(rows, ignore_index=True)


def _actions_for_issue(ctx):
    from parlay_policy.contract import Action, N_GRID, K_GRID, LANES, CAPITAL_LANES

    m = len(ctx.panel.match_idx)
    return [
        Action(n=n, k=k, lane=lane, capital=capital)
        for n in N_GRID
        if n <= m
        for k in K_GRID
        for lane in LANES
        for capital in CAPITAL_LANES
    ]


def _run_controls(
    test_ctx, pool_cache, test_split, train_frames=None,
    frozen_incumbent: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Run the 10-arm attribution matrix on the test split.

    Dynamic controls (dynamic N with fixed K8, fixed N7 with dynamic K, dynamic
    N×K) choose per issue from the train-fold median lift ranking, restricted
    to eligibility — never from test outcomes. The incumbent arm binds the
    exact frozen #207 capital path.
    """
    from parlay_policy.contract import Action, N_GRID, K_GRID, LANES, CAPITAL_LANES
    from parlay_policy.tickets import select_tickets, settle_tickets, bundle_capital, bundle_capital_equal1pct

    results: dict[str, pd.DataFrame] = {}
    issues = sorted(test_ctx.keys(), key=lambda item: test_ctx[item].panel.year)
    incumbent_key = f"N{INCUMBENT_N}/K{INCUMBENT_K}/{INCUMBENT_LANE}/NATIVE_2_YUAN"

    # Train-fold median lift tables for dynamic controls (label-blind choice).
    dynamic_n_rank: dict[int, float] = {}
    dynamic_k_rank: dict[int, float] = {}
    dynamic_nk_rank: dict[tuple[int, int], float] = {}
    if train_frames is not None and not train_frames.empty:
        for (n, k, lane, capital), group in train_frames.groupby(
            ["n", "k", "lane", "capital"]
        ):
            if lane == "MARKET_WOR" and capital == "NATIVE_2_YUAN":
                dynamic_nk_rank[(int(n), int(k))] = float(group["y_lift"].median())
                if int(k) == 8:
                    dynamic_n_rank[int(n)] = float(group["y_lift"].median())
                if int(n) == 7:
                    dynamic_k_rank[int(k)] = float(group["y_lift"].median())

    for name, action_fn in _CONTROL_ACTIONS.items():
        rows: list[dict[str, object]] = []
        bankroll = INITIAL_BANKROLL_YUAN
        for (split, issue) in issues:
            ctx = test_ctx[(split, issue)]
            m = len(ctx.panel.match_idx)
            if name == "dynamic_n_fixed_k8_lane" and dynamic_n_rank:
                eligible = {n: v for n, v in dynamic_n_rank.items() if n <= m}
                best_n = max(eligible, key=eligible.get) if eligible else 7
                action = _action(best_n, 8, "MARKET_WOR", "NATIVE_2_YUAN")
            elif name == "fixed_n7_dynamic_k" and dynamic_k_rank:
                best_k = max(dynamic_k_rank, key=dynamic_k_rank.get)
                action = _action(7, best_k, "MARKET_WOR", "NATIVE_2_YUAN")
            elif name == "dynamic_nk_fixed_generator" and dynamic_nk_rank:
                eligible = {
                    (n, k): v for (n, k), v in dynamic_nk_rank.items()
                    if n <= m
                }
                best_cell = max(eligible, key=eligible.get) if eligible else (7, 8)
                action = _action(best_cell[0], best_cell[1], "MARKET_WOR", "NATIVE_2_YUAN")
            else:
                action = action_fn(ctx)
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
                    payout = float(row["gross_payout_yuan"])
                    funded = float(row["funded_stake_yuan"])
                    new_bankroll = float(row["post_issue_bankroll_yuan"])
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
                            "funded_stake_yuan": funded,
                            "gross_payout_yuan": payout,
                            "post_issue_bankroll_yuan": new_bankroll,
                            "net_pnl_yuan": float(new_bankroll - bankroll),
                            "drawdown_pct": 0.0,
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
                        "funded_stake_yuan": 0.0,
                        "gross_payout_yuan": 0.0,
                        "post_issue_bankroll_yuan": bankroll,
                        "net_pnl_yuan": 0.0,
                        "drawdown_pct": 0.0,
                    }
                )
                continue
            sel = select_tickets(pool, action.lane, action.k, seed=0)
            settled = settle_tickets(sel)
            if action.capital == "SIMPLE_ACTIVE":
                cap = bundle_capital_equal1pct(settled, bankroll)
            else:
                cap = bundle_capital(settled, bankroll)
            new_bankroll = float(cap["post_issue_bankroll_yuan"])
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
                    "funded_stake_yuan": float(cap["funded_stake_yuan"]),
                    "gross_payout_yuan": float(cap["gross_payout_yuan"]),
                    "post_issue_bankroll_yuan": new_bankroll,
                    "net_pnl_yuan": float(new_bankroll - bankroll),
                    "drawdown_pct": 0.0,
                }
            )
            bankroll = new_bankroll
        results[name] = pd.DataFrame(rows)
    return results


def _make_fixed_action(action) -> Any:
    def choose(ctx):
        return action

    return choose


def _action(n: int, k: int, lane: str, capital: str) -> "Action":
    from parlay_policy.contract import Action

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


def _write_diagnostics(output, all_fit, all_test, contexts, policy_mlp):
    from parlay_policy.diagnostics import (
        action_frequency,
        action_variation_demo,
        calibration_curve,
        ood_fallback_census,
        permutation_importance_table,
    )

    context_states = {
        f"{split}:{issue}": ctx.state
        for (split, issue), ctx in contexts.items()
    }
    if not all_test.empty:
        freq = action_frequency(all_test)
        freq.to_csv(output / "action_frequency.csv", index=False)
        fallback = ood_fallback_census(all_test)
        fallback.to_csv(output / "ood_fallback_census.csv", index=False)
    if not all_fit.empty:
        perm = permutation_importance_table(all_fit, policy_mlp)
        perm.to_csv(output / "permutation_importance.csv", index=False)
        calib = calibration_curve(all_fit, policy_mlp, context_states)
        calib.to_csv(output / "calibration_curve.csv", index=False)
        demo = action_variation_demo(context_states, policy_mlp)
        demo.to_csv(output / "action_variation_demo.csv", index=False)


def _apply_selection_rule(
    fold_results: dict[str, object],
    all_test: pd.DataFrame,
    all_fit: pd.DataFrame,
    incumbent_paths: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Preregistered lexicographic selection rule (protocol section 10).

    Matched lift is versus the frozen #207 incumbent path (exact CONTROLLING
    ticket identities, native ¥2) on the same test split, never versus a
    replayed proxy control.
    """
    from parlay_policy.contract import Action, INCUMBENT_LANE, INCUMBENT_N, INCUMBENT_K

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
    no_ruin = bool(not matched_df.empty and (matched_df["learned_end"] > 0).all())
    rule1 = valid_replay and no_ruin
    rule2 = np.isfinite(median_lift) and median_lift > 0
    rule3 = positive_folds >= 2
    eligible = bool(rule1 and rule2 and rule3)
    candidate = {
        "policy": "LEARNED_MLP_Q",
        "n": None,
        "k": None,
        "lane": None,
        "capital": None,
    }
    if eligible:
        best_fold = matched_df.sort_values("matched_lift", ascending=False).iloc[0]
        # The candidate is the per-issue learned policy; its representative
        # action is the most frequent action on the terminal fold.
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
        "rule1_valid_replay_no_ruin": rule1,
        "rule2_positive_median_lift": rule2,
        "rule3_positive_in_two_folds": rule3,
        "eligible": eligible,
        "median_matched_lift_yuan": median_lift,
        "positive_fold_count": positive_folds,
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


def _build_handoff(fold_results, selection, output) -> dict[str, object]:
    """Single frozen #209 handoff: hashes, fit boundary, candidate/fallback."""
    return {
        "handoff_version": "bj208-handoff-for-209-v1",
        "fit_boundary": {
            "train_through": "2022",
            "test_2023": True,
            "2024_opened": False,
            "2025_2026_opened": False,
        },
        "candidate": selection["frozen_candidate"],
        "fallback": {
            "policy": "FROZEN_N7_INCUMBENT",
            "n": INCUMBENT_N,
            "k": INCUMBENT_K,
            "lane": INCUMBENT_LANE,
            "capital": "NATIVE_2_YUAN",
        },
        "model": (
            fold_results.get("fold2", {}).get("policy_mlp", {})
            if "fold2" in fold_results
            else {}
        ),
        "terminal_split": TERMINAL_SPLIT,
        "contract_version": CONTRACT_VERSION,
        "replay_command": "PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py run --output results/issue-208",
        "package_manifest": (
            str(output / "SHA256SUMS.json")
        ),
    }


def _environment() -> dict[str, str]:
    import importlib.metadata
    import platform

    names = ("numpy", "pandas", "pyarrow", "scikit-learn", "scipy")
    return {
        "python": platform.python_version(),
        **{name: importlib.metadata.version(name) for name in names},
    }


def verify_package(output: Path) -> list[str]:
    failures: list[str] = []
    manifest_path = output / "SHA256SUMS.json"
    if not manifest_path.exists():
        return ["missing SHA256SUMS.json"]
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures.extend(verify_manifest(output, expected))

    ledger = pd.read_parquet(output / "issue_capital_ledger.parquet")
    failures.extend(verify_capital_accounting(ledger))
    failures.extend(verify_no_embargoed_split(ledger))
    failures.extend(verify_no_2024_issue(ledger))

    decisions = pd.read_parquet(output / "decision_rows_all.parquet")
    failures.extend(verify_no_embargoed_split(decisions))
    failures.extend(verify_no_2024_issue(decisions))
    return failures


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
        tamper = json.loads((output / "tamper_results.json").read_text(encoding="utf-8"))
        print(f"verify ok; tamper detected={len(tamper)}")
    else:
        raise SystemExit(f"unknown command {args.command}")


if __name__ == "__main__":
    main()
