"""Build the exact BEST_FULL plus residual-action issue panel."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from issue296.panel import load_issue_features

BASELINE_PATH = Path("evidence/bj299_residual_sources_v1/best_full_2019_2023.csv")
SOURCE_MANIFEST_PATH = Path("evidence/bj299_residual_sources_v1/source_manifest.json")

ACTIONS: dict[str, tuple[str, ...]] = {
    "BASELINE_ONLY": (),
    "BASELINE_SCALE_DOWN": ("CASH_OVERRIDE",),
    "BASELINE_PLUS_CORE": ("SMOOTH_M512",),
    "BASELINE_PLUS_TAIL": ("RARE_LOGIT_TOP64",),
    "BASELINE_PLUS_DIVERGENCE": ("DIVERGENCE_Z100_K1",),
    "BASELINE_PLUS_MIXED": ("SMOOTH_M512", "RARE_LOGIT_TOP64"),
}

RESIDUAL_EXPERTS = (
    "SMOOTH_M512",
    "DIVERGENCE_Z100_K1",
    "RARE_LOGIT_TOP64",
)


def load_baseline(root: str | Path) -> pd.DataFrame:
    """Load the frozen exact BEST_FULL projection and enforce its atomic contract."""

    frame = pd.read_csv(Path(root) / BASELINE_PATH)
    frame["issue"] = pd.to_numeric(frame["issue"], errors="raise").astype(int)
    frame["issue_year"] = pd.to_numeric(frame["issue_year"], errors="raise").astype(int)
    if not frame["issue_year"].between(2019, 2023).all():
        raise AssertionError("BEST_FULL projection is outside 2019-2023")
    if frame["issue"].duplicated().any() or len(frame) != 270:
        raise AssertionError("BEST_FULL projection must have one row per issue")
    active = frame["stake_yuan"].gt(0)
    if not frame.loc[active, "stake_yuan"].eq(4374.0).all():
        raise AssertionError("active BEST_FULL stake drift")
    if not frame.loc[active, "executed_ticket_count"].eq(2187).all():
        raise AssertionError("active BEST_FULL ticket-count drift")
    if (
        not frame.loc[~active, ["stake_yuan", "gross_pre_tax_yuan", "pre_tax_net_yuan"]]
        .eq(0)
        .all(axis=None)
    ):
        raise AssertionError("BEST_FULL NO_BET carries economics")
    return frame.sort_values(["issue_year", "issue"]).reset_index(drop=True)


def build_action_panel(root: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return one causal issue table and one issue-by-residual-action ledger."""

    features = load_issue_features(root)
    baseline = load_baseline(root)
    expert_panel = _load_residual_experts(root)
    support = features[["issue", "issue_year"]].merge(
        baseline,
        on=["issue", "issue_year"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    baseline = support.loc[support["_merge"].eq("both")].drop(columns="_merge")
    if len(baseline) != 227:
        raise AssertionError("unexpected BEST_FULL/feature common support")
    baseline = baseline.rename(
        columns={
            "stake_yuan": "baseline_stake_cny",
            "gross_pre_tax_yuan": "baseline_gross_cny",
            "pre_tax_net_yuan": "baseline_pnl_cny",
            "hit_ticket_count": "baseline_hits",
        }
    )
    issue_table = features.merge(
        baseline[
            [
                "issue",
                "baseline_stake_cny",
                "baseline_gross_cny",
                "baseline_pnl_cny",
                "baseline_hits",
                "settlement_status",
                "n7_identity_sha256",
                "ticket_identity_sha256",
            ]
        ],
        on="issue",
        how="inner",
        validate="one_to_one",
    )
    issue_table["baseline_active"] = issue_table["baseline_stake_cny"].gt(0).astype(int)

    experts = expert_panel.set_index(["issue", "expert_id"])
    rows: list[dict[str, object]] = []
    for issue in issue_table.itertuples(index=False):
        base = {
            "stake_cny": float(issue.baseline_stake_cny),
            "pnl_cny": float(issue.baseline_pnl_cny),
            "gross_cny": float(issue.baseline_gross_cny),
            "hits": float(issue.baseline_hits),
        }
        for action, additions in ACTIONS.items():
            economics = base.copy()
            available = True
            if additions == ("CASH_OVERRIDE",):
                economics = {key: 0.0 for key in economics}
            else:
                for expert in additions:
                    key = (int(issue.issue), expert)
                    if key not in experts.index or not bool(
                        experts.loc[key, "available"]
                    ):
                        available = False
                        break
                    economics["stake_cny"] += float(experts.loc[key, "stake_unit_cny"])
                    economics["pnl_cny"] += float(experts.loc[key, "pnl_unit_cny"])
                    economics["gross_cny"] += float(experts.loc[key, "gross_unit_cny"])
                    economics["hits"] += float(experts.loc[key, "hit_count"])
            rows.append(
                {
                    "issue": int(issue.issue),
                    "issue_year": int(issue.issue_year),
                    "action": action,
                    "available": available,
                    **economics,
                    "residual_stake_cny": economics["stake_cny"] - base["stake_cny"],
                    "residual_pnl_cny": economics["pnl_cny"] - base["pnl_cny"],
                    "residual_gross_cny": economics["gross_cny"] - base["gross_cny"],
                }
            )
    actions = pd.DataFrame(rows)
    unavailable = ~actions["available"]
    actions.loc[
        unavailable,
        [
            "stake_cny",
            "pnl_cny",
            "gross_cny",
            "hits",
            "residual_stake_cny",
            "residual_pnl_cny",
            "residual_gross_cny",
        ],
    ] = np.nan
    if actions.groupby("issue")["action"].nunique().ne(len(ACTIONS)).any():
        raise AssertionError("action panel is incomplete")
    return issue_table, actions


def build_support_receipt(root: str | Path) -> pd.DataFrame:
    """Expose every feature-calendar issue and whether exact BEST_FULL exists."""

    features = load_issue_features(root)[["issue", "issue_year"]]
    baseline = load_baseline(root)[["issue", "issue_year"]]
    receipt = features.merge(
        baseline,
        on=["issue", "issue_year"],
        how="left",
        indicator=True,
        validate="one_to_one",
    )
    receipt["support_status"] = np.where(
        receipt["_merge"].eq("both"),
        "MATCHED_BASELINE_AND_FEATURES",
        "EXCLUDED_NO_EXACT_BEST_FULL",
    )
    return receipt.drop(columns="_merge")


def _load_residual_experts(root: str | Path) -> pd.DataFrame:
    """Load only realizable experts used by #299; exclude #296 synthetic Q-WOR."""

    root = Path(root)
    sources = _verified_residual_sources(root)
    source_176 = pd.read_csv(sources["SMOOTH_M512"])
    source_176 = source_176[source_176["expert_id"].eq("SMOOTH_M512")]
    source_190 = pd.read_csv(sources["DIVERGENCE_Z100_K1"])
    source_190 = source_190[source_190["expert_id"].eq("DIVERGENCE_Z100_K1")]
    source_291 = pd.read_csv(sources["RARE_LOGIT_TOP64"])
    source_291 = source_291[
        source_291["domain"].eq("BASE")
        & source_291["model"].eq("DATA_LOGIT_RIDGE")
        & source_291["score"].eq("DIRECT_PNL")
        & source_291["ticket_budget_per_issue"].eq(64)
    ].rename(
        columns={
            "oof_year": "issue_year",
            "stake_cny": "stake_unit_cny",
            "pnl_cny": "pnl_unit_cny",
            "gross_cny": "gross_unit_cny",
            "hits": "hit_count",
        }
    )
    source_291["expert_id"] = "RARE_LOGIT_TOP64"
    columns = [
        "issue",
        "issue_year",
        "expert_id",
        "stake_unit_cny",
        "pnl_unit_cny",
        "gross_unit_cny",
        "hit_count",
    ]
    frame = pd.concat(
        [source_176[columns], source_190[columns], source_291[columns]],
        ignore_index=True,
    )
    frame["issue"] = pd.to_numeric(frame["issue"], errors="raise").astype(int)
    frame["issue_year"] = pd.to_numeric(frame["issue_year"], errors="raise").astype(int)
    if frame["issue_year"].gt(2023).any():
        raise AssertionError("residual expert source opened a sealed year")
    if frame.duplicated(["issue", "expert_id"]).any():
        raise AssertionError("residual expert ledger is not unique")
    frame["available"] = True
    if set(frame["expert_id"].unique()) != set(RESIDUAL_EXPERTS):
        raise AssertionError("residual expert identity drift")
    return frame


def _verified_residual_sources(root: Path) -> dict[str, Path]:
    """Resolve residual sources only after checking the #299 registry hashes."""

    manifest = json.loads((root / SOURCE_MANIFEST_PATH).read_text(encoding="utf-8"))
    resolved: dict[str, Path] = {}
    for source in manifest["residual_sources"]:
        path = root / source["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source["sha256"]:
            raise AssertionError(f"residual source hash drift: {source['expert_id']}")
        resolved[str(source["expert_id"])] = path
    if set(resolved) != set(RESIDUAL_EXPERTS):
        raise AssertionError("residual source registry is incomplete")
    return resolved
