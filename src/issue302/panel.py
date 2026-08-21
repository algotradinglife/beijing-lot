"""Matched atomic BEST_FULL and realizable expert panel for Issue #302."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from issue296.panel import build_expert_panel
from issue299.panel import build_action_panel

EXPERT_IDS = (
    "SMOOTH_M512",
    "Q_TAIL_M192",
    "DIVERGENCE_Z100_K1",
    "RARE_LOGIT_TOP64",
)


def build_panel(root: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return exact #299 support and four whole-bundle realizable experts."""

    _verify_projection_manifest(Path(root))
    issues, _ = build_action_panel(root)
    panel, _ = build_expert_panel(root)
    experts = panel[
        panel["expert_id"].isin(EXPERT_IDS) & panel["issue"].isin(issues["issue"])
    ].copy()
    experts = experts.sort_values(["issue_year", "issue", "expert_id"])
    expected = len(issues) * len(EXPERT_IDS)
    if len(experts) != expected:
        raise AssertionError(f"expert support drift: {len(experts)} != {expected}")
    if experts.duplicated(["issue", "expert_id"]).any():
        raise AssertionError("expert panel is not unique")
    if set(experts["expert_id"]) != set(EXPERT_IDS):
        raise AssertionError("realizable expert identity drift")
    if issues["issue_year"].gt(2023).any() or experts["issue_year"].gt(2023).any():
        raise AssertionError("Issue #302 opened a sealed 2024+ row")
    return issues.reset_index(drop=True), experts.reset_index(drop=True)


def _verify_projection_manifest(root: Path) -> None:
    manifest_path = root / "evidence/bj296_expert_sources_v1/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    directory = manifest_path.parent
    for name, expected in manifest["projection_sha256"].items():
        actual = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        if actual != expected:
            raise AssertionError(f"Issue #296 projection hash drift: {name}")


def action_ledger(issues: pd.DataFrame, experts: pd.DataFrame) -> pd.DataFrame:
    """Create one row per issue/action without fractional-return substitutions."""

    base = issues[
        [
            "issue",
            "issue_year",
            "baseline_active",
            "baseline_stake_cny",
            "baseline_pnl_cny",
            "baseline_gross_cny",
            "baseline_hits",
        ]
    ].rename(
        columns={
            "baseline_active": "available",
            "baseline_stake_cny": "stake_unit_cny",
            "baseline_pnl_cny": "pnl_unit_cny",
            "baseline_gross_cny": "gross_unit_cny",
            "baseline_hits": "hit_count",
        }
    )
    base["action_id"] = "B0_BEST_FULL"
    base["available"] = True
    expert = experts.rename(columns={"expert_id": "action_id"})[
        [
            "issue",
            "issue_year",
            "action_id",
            "available",
            "stake_unit_cny",
            "pnl_unit_cny",
            "gross_unit_cny",
            "hit_count",
        ]
    ]
    result = pd.concat([base, expert], ignore_index=True)
    result["payout"] = result["gross_unit_cny"].gt(0).astype(int)
    result["loss"] = result["pnl_unit_cny"].lt(0).astype(int)
    result["downside_cny"] = (-result["pnl_unit_cny"]).clip(lower=0)
    return result.sort_values(["issue_year", "issue", "action_id"]).reset_index(
        drop=True
    )
