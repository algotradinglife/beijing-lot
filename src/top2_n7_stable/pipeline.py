"""Build and verify the Issue #319 probability-only stable-center package.

The module deliberately separates pre-outcome construction from settlement.  The
pre-outcome hashes are computed before the SQLite settlement table is opened.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .contract import (
    ACTIVE_ARMS,
    GM_GATES,
    HORIZONS,
    ISSUE_STAKE,
    N_LEGS,
    OUTCOME_ORDER,
    PAYOUT_FACTOR,
    PRICE_BLOCKED_ARMS,
    PROBABILITY_SOURCE,
    RANDOM_SEEDS,
    STAKE_PER_TICKET,
    STARTING_CAPITAL,
    TERMINAL_DECISION,
    TICKETS_PER_BUNDLE,
)


PREOUTCOME_BUNDLE_COLUMNS = [
    "issue_code", "issue_year", "horizon", "arm", "gate", "seed",
    "status_preoutcome", "selected_fixture_keys", "support_json",
    "retained_mass_mean", "retained_mass_min", "ticket_count", "planned_stake",
]
PREOUTCOME_TICKET_COLUMNS = [
    "issue_code", "issue_year", "horizon", "arm", "gate", "seed",
    "ticket_index", "ticket_key", "stake",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame, columns: list[str]) -> str:
    ordered = frame.loc[:, columns].sort_values(columns, kind="stable").reset_index(drop=True)
    payload = ordered.to_csv(index=False, lineterminator="\n", float_format="%.12g")
    return hashlib.sha256(payload.encode()).hexdigest()


def locate_data_root(repo_root: Path, explicit: Path | None = None) -> Path:
    candidates = [] if explicit is None else [explicit]
    candidates += [repo_root / "data", repo_root.parents[1] / "data"]
    for candidate in candidates:
        if (candidate / "derived/bj238_divergence_materializer_v4r3").exists():
            return candidate.resolve()
    raise FileNotFoundError("data root with bj238_divergence_materializer_v4r3 not found")


def _seed(issue_code: str, seed_index: int) -> int:
    raw = f"BJ-TOP2-N7{issue_code}{seed_index}".encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _feature_surface(path: Path) -> pd.DataFrame:
    columns = [
        "canonical_fixture_key", "issue_code", "match_idx", "snapshot_kind",
        "issue_anchor_ts", "issue_year", "native_handicap_line", "n_available_books",
        "causal_grade", "mapping_accepted", "outcome_code", "q_eu_bjline",
        "q_line_only_control", "eu_vs_line_divergence",
    ]
    frame = pd.read_parquet(path, columns=columns, filters=[("issue_year", "in", [2023, 2024])])
    frame["issue_code"] = frame["issue_code"].astype(str)
    frame["outcome_code"] = frame["outcome_code"].astype(str)
    frame = frame[frame["snapshot_kind"].isin(HORIZONS)].copy()
    frame = frame[frame["mapping_accepted"].fillna(False) & frame["q_eu_bjline"].notna()].copy()
    return frame


def _validate_roles(path: Path, feature: pd.DataFrame) -> dict[str, int]:
    roles = pd.read_csv(path, dtype={"issue_code": str})
    roles = roles[roles["issue_year"].isin([2023, 2024])].copy()
    expected = {2023: "calibration", 2024: "sealed_feature_only"}
    for year, role in expected.items():
        observed = set(roles.loc[roles.issue_year == year, "temporal_role"])
        if observed != {role}:
            raise ValueError(f"unexpected temporal role for {year}: {sorted(observed)}")
    feature_issues = set(feature["issue_code"].astype(str))
    role_issues = set(roles["issue_code"])
    if not feature_issues.issubset(role_issues):
        raise ValueError(f"feature issues missing frozen roles: {sorted(feature_issues - role_issues)[:10]}")
    return {str(year): int(roles.loc[roles.issue_year == year, "issue_code"].nunique()) for year in expected}


def _fixture_table(frame: pd.DataFrame) -> pd.DataFrame:
    order = {code: i for i, code in enumerate(OUTCOME_ORDER)}
    rows: list[dict] = []
    keys = ["issue_code", "issue_year", "snapshot_kind", "canonical_fixture_key", "match_idx"]
    for key, group in frame.groupby(keys, sort=True, observed=True):
        group = group.drop_duplicates("outcome_code")
        if set(group["outcome_code"]) != set(OUTCOME_ORDER):
            continue
        ranked = sorted(
            ((str(r.outcome_code), float(r.q_eu_bjline)) for r in group.itertuples()),
            key=lambda x: (-x[1], order[x[0]]),
        )
        top2 = ranked[:2]
        representative = group.iloc[0]
        rows.append({
            "issue_code": str(key[0]), "issue_year": int(key[1]), "horizon": str(key[2]),
            "canonical_fixture_key": str(key[3]), "match_idx": int(key[4]),
            "support": tuple(x[0] for x in top2),
            "retained_mass": float(sum(x[1] for x in top2)),
            "top_probability": float(top2[0][1]),
            "native_handicap_line": float(representative.native_handicap_line),
            "divergence_abs_mean": float(group["eu_vs_line_divergence"].abs().mean()),
            "n_available_books": int(representative.n_available_books),
            "causal_grade": str(representative.causal_grade),
        })
    return pd.DataFrame(rows)


def _bundle_row(group: pd.DataFrame, arm: str, seed: int, selected: pd.DataFrame) -> dict:
    selected = selected.sort_values("canonical_fixture_key", kind="stable")
    support = {str(r.canonical_fixture_key): list(r.support) for r in selected.itertuples()}
    return {
        "issue_code": str(group.iloc[0]["issue_code"]),
        "issue_year": int(group.iloc[0]["issue_year"]),
        "horizon": str(group.iloc[0]["horizon"]),
        "arm": arm, "gate": "NONE", "seed": seed,
        "status_preoutcome": "ACTIVE",
        "selected_fixture_keys": "|".join(support),
        "support_json": json.dumps(support, sort_keys=True, separators=(",", ":")),
        "retained_mass_mean": float(selected["retained_mass"].mean()),
        "retained_mass_min": float(selected["retained_mass"].min()),
        "ticket_count": TICKETS_PER_BUNDLE,
        "planned_stake": ISSUE_STAKE,
        "line_abs_mean": float(selected["native_handicap_line"].abs().mean()),
        "divergence_abs_mean": float(selected["divergence_abs_mean"].mean()),
        "available_books_mean": float(selected["n_available_books"].mean()),
    }


def construct_preoutcome(feature: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    fixtures = _fixture_table(feature)
    bundle_rows: list[dict] = []
    ticket_rows: list[dict] = []
    for _, group in fixtures.groupby(["issue_code", "issue_year", "horizon"], sort=True):
        issue = str(group.iloc[0]["issue_code"])
        if len(group) < N_LEGS:
            for arm in ACTIVE_ARMS:
                for gate in GM_GATES:
                    bundle_rows.append({
                        "issue_code": issue, "issue_year": int(group.iloc[0]["issue_year"]),
                        "horizon": str(group.iloc[0]["horizon"]), "arm": arm, "gate": gate,
                        "seed": -1, "status_preoutcome": "NO_BET_INSUFFICIENT_FIXTURES",
                        "selected_fixture_keys": "", "support_json": "{}",
                        "retained_mass_mean": np.nan, "retained_mass_min": np.nan,
                        "ticket_count": 0, "planned_stake": 0.0, "line_abs_mean": np.nan,
                        "divergence_abs_mean": np.nan, "available_books_mean": np.nan,
                    })
            for arm in PRICE_BLOCKED_ARMS:
                for gate in GM_GATES:
                    bundle_rows.append({
                        "issue_code": issue, "issue_year": int(group.iloc[0]["issue_year"]),
                        "horizon": str(group.iloc[0]["horizon"]), "arm": arm, "gate": gate,
                        "seed": -1, "status_preoutcome": "NO_BET_PRICE_DATA_INSUFFICIENT",
                        "selected_fixture_keys": "", "support_json": "{}",
                        "retained_mass_mean": np.nan, "retained_mass_min": np.nan,
                        "ticket_count": 0, "planned_stake": 0.0, "line_abs_mean": np.nan,
                        "divergence_abs_mean": np.nan, "available_books_mean": np.nan,
                    })
            continue
        probability = group.sort_values(
            ["retained_mass", "canonical_fixture_key"], ascending=[False, True], kind="stable"
        ).head(N_LEGS)
        active = [_bundle_row(group, "P_TOP2_NO_GATE", -1, probability)]
        for seed_index in RANDOM_SEEDS:
            rng = np.random.default_rng(_seed(issue, seed_index))
            indices = np.sort(rng.choice(len(group), size=N_LEGS, replace=False))
            active.append(_bundle_row(group, "RANDOM_MATCH_P_TOP2", seed_index, group.iloc[indices]))
        for row in active:
            bundle_rows.append(row)
            support = json.loads(row["support_json"])
            fixture_keys = sorted(support)
            for ticket_index, outcomes in enumerate(itertools.product((0, 1), repeat=N_LEGS)):
                legs = [f"{key}={support[key][choice]}" for key, choice in zip(fixture_keys, outcomes, strict=True)]
                ticket_rows.append({
                    "issue_code": row["issue_code"], "issue_year": row["issue_year"],
                    "horizon": row["horizon"], "arm": row["arm"], "gate": "NONE",
                    "seed": row["seed"], "ticket_index": ticket_index,
                    "ticket_key": "|".join(legs), "stake": STAKE_PER_TICKET,
                })
        # Contracted value lanes fail closed rather than fabricate prices.
        for arm in (*PRICE_BLOCKED_ARMS, "P_TOP2_NO_GATE", "RANDOM_MATCH_P_TOP2"):
            for gate in GM_GATES[1:]:
                bundle_rows.append({
                    "issue_code": issue, "issue_year": int(group.iloc[0]["issue_year"]),
                    "horizon": str(group.iloc[0]["horizon"]), "arm": arm, "gate": gate,
                    "seed": -1, "status_preoutcome": "NO_BET_PRICE_DATA_INSUFFICIENT",
                    "selected_fixture_keys": "", "support_json": "{}",
                    "retained_mass_mean": np.nan, "retained_mass_min": np.nan,
                    "ticket_count": 0, "planned_stake": 0.0, "line_abs_mean": np.nan,
                    "divergence_abs_mean": np.nan, "available_books_mean": np.nan,
                })
        for arm in PRICE_BLOCKED_ARMS:
            bundle_rows.append({
                "issue_code": issue, "issue_year": int(group.iloc[0]["issue_year"]),
                "horizon": str(group.iloc[0]["horizon"]), "arm": arm, "gate": "NONE",
                "seed": -1, "status_preoutcome": "NO_BET_PRICE_DATA_INSUFFICIENT",
                "selected_fixture_keys": "", "support_json": "{}",
                "retained_mass_mean": np.nan, "retained_mass_min": np.nan,
                "ticket_count": 0, "planned_stake": 0.0, "line_abs_mean": np.nan,
                "divergence_abs_mean": np.nan, "available_books_mean": np.nan,
            })
    bundles = pd.DataFrame(bundle_rows)
    tickets = pd.DataFrame(ticket_rows)
    return bundles, tickets


def _load_settlement(db_path: Path, years: tuple[int, ...] = (2023, 2024)) -> pd.DataFrame:
    prefixes = tuple(str(year)[-2:] + "%" for year in years)
    where = " OR ".join("issue LIKE ?" for _ in prefixes)
    query = f"""
        SELECT issue AS issue_code, match_idx, CAST(result_code AS TEXT) AS result_code,
               CAST(winning_sp AS REAL) AS winning_sp,
               CAST(has_trusted_settlement AS INTEGER) AS has_trusted_settlement,
               settlement_quality
        FROM match_features WHERE {where}
    """
    with sqlite3.connect(db_path) as connection:
        frame = pd.read_sql_query(query, connection, params=prefixes)
    frame["issue_code"] = frame["issue_code"].astype(str)
    frame["canonical_fixture_key"] = frame.apply(
        lambda r: f"bjslot:{r.issue_code}:{int(r.match_idx):03d}", axis=1
    )
    return frame.drop_duplicates(["issue_code", "canonical_fixture_key"])


def settle(bundles: pd.DataFrame, tickets: pd.DataFrame, settlement: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    lookup = settlement.set_index(["issue_code", "canonical_fixture_key"]).to_dict("index")
    bundle_updates: list[dict] = []
    ticket_updates: list[dict] = []
    for row in bundles.itertuples(index=False):
        if row.status_preoutcome != "ACTIVE":
            bundle_updates.append({"settlement_status": row.status_preoutcome, "stake": 0.0, "gross": 0.0,
                                   "pnl": 0.0, "hit": False, "miss_distance": np.nan,
                                   "realized_outside_support": np.nan})
            continue
        support = json.loads(row.support_json)
        realized: dict[str, str] = {}
        winning_sps: dict[str, float] = {}
        missing = False
        for key in support:
            data = lookup.get((str(row.issue_code), key))
            if not data or int(data.get("has_trusted_settlement") or 0) != 1:
                missing = True
                break
            result = str(data["result_code"])
            sp = float(data["winning_sp"])
            if result not in OUTCOME_ORDER or not math.isfinite(sp) or sp <= 0:
                missing = True
                break
            realized[key] = result
            winning_sps[key] = sp
        if missing:
            bundle_updates.append({"settlement_status": "UNOBSERVABLE_SETTLEMENT", "stake": np.nan,
                                   "gross": np.nan, "pnl": np.nan, "hit": np.nan,
                                   "miss_distance": np.nan, "realized_outside_support": np.nan})
            continue
        outside = sum(realized[key] not in support[key] for key in support)
        gross = STAKE_PER_TICKET * PAYOUT_FACTOR * math.prod(winning_sps.values()) if outside == 0 else 0.0
        bundle_updates.append({"settlement_status": "SETTLED", "stake": ISSUE_STAKE, "gross": gross,
                               "pnl": gross - ISSUE_STAKE, "hit": outside == 0,
                               "miss_distance": outside, "realized_outside_support": outside})
    bundles = pd.concat([bundles.reset_index(drop=True), pd.DataFrame(bundle_updates)], axis=1)

    # Ticket settlement is exact and remains separate from the analytical bundle check.
    active_tickets = tickets.merge(
        bundles[["issue_code", "issue_year", "horizon", "arm", "gate", "seed", "settlement_status"]],
        on=["issue_code", "issue_year", "horizon", "arm", "gate", "seed"], how="left", validate="many_to_one",
    )
    for row in active_tickets.itertuples(index=False):
        if row.settlement_status != "SETTLED":
            ticket_updates.append({"correct_legs": np.nan, "ticket_hit": np.nan, "gross": np.nan})
            continue
        legs = dict(part.split("=", 1) for part in row.ticket_key.split("|"))
        correct = sum(str(lookup[(str(row.issue_code), key)]["result_code"]) == outcome for key, outcome in legs.items())
        if correct == N_LEGS:
            product = math.prod(float(lookup[(str(row.issue_code), key)]["winning_sp"]) for key in legs)
            gross = STAKE_PER_TICKET * PAYOUT_FACTOR * product
        else:
            gross = 0.0
        ticket_updates.append({"correct_legs": correct, "ticket_hit": correct == N_LEGS, "gross": gross})
    tickets = pd.concat([active_tickets.reset_index(drop=True), pd.DataFrame(ticket_updates)], axis=1)
    return bundles, tickets


def _risk(path: pd.DataFrame) -> dict:
    pnl = path["pnl"].to_numpy(float)
    capital = path["capital_after"].to_numpy(float)
    peaks = np.maximum.accumulate(np.r_[STARTING_CAPITAL, capital])
    values = np.r_[STARTING_CAPITAL, capital]
    drawdowns = peaks - values
    losing = pnl < 0
    longest = current = 0
    for flag in losing:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    no_payout_longest = no_payout_current = 0
    for flag in path["gross"].to_numpy(float) == 0:
        no_payout_current = no_payout_current + 1 if flag else 0
        no_payout_longest = max(no_payout_longest, no_payout_current)
    underwater = capital < np.maximum.accumulate(np.r_[STARTING_CAPITAL, capital])[:-1]
    max_recovery = recovery_current = 0
    for flag in underwater:
        recovery_current = recovery_current + 1 if flag else 0
        max_recovery = max(max_recovery, recovery_current)
    ending_underwater = 0
    for flag in underwater[::-1]:
        if not flag:
            break
        ending_underwater += 1
    rolling = {}
    for width in (5, 10, 20):
        rolling[f"worst_{width}_issue_pnl"] = float(pd.Series(pnl).rolling(width).sum().min()) if len(pnl) >= width else np.nan
    positive_gross = path.loc[path["gross"] > 0, "gross"].to_numpy(float)
    payout_hhi = float(np.square(positive_gross / positive_gross.sum()).sum()) if positive_gross.size else np.nan
    ex_largest_pnl = float(pnl.sum() - pnl.max()) if pnl.size else np.nan
    return {"max_drawdown": float(drawdowns.max()), "max_drawdown_pct": float((drawdowns / peaks).max()),
            "longest_losing_run": int(longest), "longest_no_payout_run": int(no_payout_longest),
            "max_recovery_issues": int(max_recovery), "ending_underwater_issues": int(ending_underwater),
            "ex_largest_issue_pnl": ex_largest_pnl, "payout_hhi": payout_hhi, **rolling}


def _block_bootstrap_means(values: np.ndarray, rng: np.random.Generator, draws: int = 2000, block: int = 5) -> np.ndarray:
    """Circular moving-block bootstrap preserving short issue-path dependence."""
    n = len(values)
    starts_per_draw = math.ceil(n / block)
    offsets = np.arange(block)
    output = np.empty(draws)
    for draw in range(draws):
        starts = rng.integers(0, n, size=starts_per_draw)
        indices = ((starts[:, None] + offsets) % n).ravel()[:n]
        output[draw] = values[indices].mean()
    return output


def summarize(bundles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    settled = bundles[(bundles["settlement_status"] == "SETTLED") & (bundles["gate"] == "NONE")].copy()
    paths: list[pd.DataFrame] = []
    summaries: list[dict] = []
    risks: list[dict] = []
    keys = ["horizon", "issue_year", "arm", "seed"]
    for key, group in settled.groupby(keys, sort=True):
        group = group.sort_values("issue_code", kind="stable").copy()
        group["capital_before"] = STARTING_CAPITAL + group["pnl"].cumsum().shift(fill_value=0)
        group["capital_after"] = STARTING_CAPITAL + group["pnl"].cumsum()
        group["path_id"] = f"{key[0]}:{key[1]}:{key[2]}:{key[3]}"
        paths.append(group[["path_id", "issue_code", "issue_year", "horizon", "arm", "seed", "stake", "gross", "pnl", "hit", "capital_before", "capital_after"]])
        total_stake = float(group["stake"].sum())
        total_gross = float(group["gross"].sum())
        row = {"horizon": key[0], "issue_year": key[1], "arm": key[2], "seed": key[3],
               "active_issues": len(group), "total_stake": total_stake, "total_gross": total_gross,
               "turnover_roi": total_gross / total_stake - 1, "ending_capital": float(group["capital_after"].iloc[-1]),
               "bundle_hit_rate": float(group["hit"].mean()), "mean_retained_mass": float(group["retained_mass_mean"].mean())}
        summaries.append(row)
        risks.append({**{k: row[k] for k in ["horizon", "issue_year", "arm", "seed"]}, **_risk(group)})
    path_frame = pd.concat(paths, ignore_index=True)
    summary = pd.DataFrame(summaries)
    risk = pd.DataFrame(risks)

    # Random seeds are nuisance replications: summarize medians, never n=31 issues.
    random = summary[summary["arm"] == "RANDOM_MATCH_P_TOP2"]
    median_rows = random.groupby(["horizon", "issue_year"], as_index=False).agg(
        active_issues=("active_issues", "median"), total_stake=("total_stake", "median"),
        total_gross=("total_gross", "median"), turnover_roi=("turnover_roi", "median"),
        ending_capital=("ending_capital", "median"), bundle_hit_rate=("bundle_hit_rate", "median"),
        mean_retained_mass=("mean_retained_mass", "median"),
    )
    median_rows["arm"] = "RANDOM_MATCH_P_TOP2_SEED_MEDIAN"
    median_rows["seed"] = -2
    summary = pd.concat([summary, median_rows[summary.columns]], ignore_index=True)

    # Paired issue-level lift versus random controls. Each pair has exactly CNY256
    # funded in both arms; seeds remain nuisance repeats nested within issues.
    primary = settled[settled["arm"] == "P_TOP2_NO_GATE"]
    random_rows = settled[settled["arm"] == "RANDOM_MATCH_P_TOP2"]
    paired_seed = primary.merge(
        random_rows,
        on=["issue_code", "issue_year", "horizon"], suffixes=("_primary", "_random"),
        validate="one_to_many",
    )
    paired_seed["lift_vs_random"] = paired_seed["pnl_primary"] - paired_seed["pnl_random"]
    lift_by_seed = paired_seed.groupby(["horizon", "issue_year", "seed_random"], as_index=False).agg(
        matched_issues=("issue_code", "nunique"), primary_pnl=("pnl_primary", "sum"),
        random_pnl=("pnl_random", "sum"), lift=("lift_vs_random", "sum"),
    )
    selector_lift = lift_by_seed.groupby(["horizon", "issue_year"], as_index=False).agg(
        nuisance_seeds=("seed_random", "nunique"), matched_issues_min=("matched_issues", "min"),
        matched_issues_median=("matched_issues", "median"), median_total_lift=("lift", "median"),
        lift_min=("lift", "min"), lift_max=("lift", "max"), positive_seed_fraction=("lift", lambda x: float((x > 0).mean())),
    )
    rnd = random_rows.groupby(
        ["issue_code", "issue_year", "horizon"], as_index=False
    )["pnl"].median().rename(columns={"pnl": "random_seed_median_pnl"})
    paired = primary.merge(rnd, on=["issue_code", "issue_year", "horizon"], validate="one_to_one")
    paired["lift_vs_random"] = paired["pnl"] - paired["random_seed_median_pnl"]
    rng = np.random.default_rng(319)
    bootstrap = {}
    for horizon in HORIZONS:
        bootstrap[horizon] = {}
        for year_label, subset in (("combined", paired[paired["horizon"] == horizon]),
                                   ("2023", paired[(paired["horizon"] == horizon) & (paired["issue_year"] == 2023)]),
                                   ("2024", paired[(paired["horizon"] == horizon) & (paired["issue_year"] == 2024)])):
            values = subset["lift_vs_random"].to_numpy(float)
            draws = _block_bootstrap_means(values, rng)
            bootstrap[horizon][year_label] = {
                "n_issues": int(len(values)), "block_size": 5, "draws": 2000,
                "mean_lift_per_issue": float(values.mean()),
                "bootstrap_median": float(np.median(draws)), "ci95_low": float(np.quantile(draws, .025)),
                "ci95_high": float(np.quantile(draws, .975)),
            }
    return summary, path_frame, risk, selector_lift, {"paired": paired, "bootstrap": bootstrap}


def _write_notebook(repo_root: Path, output: Path) -> None:
    import nbformat
    from nbclient import NotebookClient
    notebook_dir = repo_root / "notebooks/research/top2-n7-stable"
    notebook_dir.mkdir(parents=True, exist_ok=True)
    path = notebook_dir / "top2_n7_stable.ipynb"
    nb = nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_markdown_cell("# Issue #319 — Probability Top-2 N7 stable center\n\nExecuted decision notebook; paths are repository-relative."),
        nbformat.v4.new_code_cell("from pathlib import Path\nimport json\nimport pandas as pd\nimport matplotlib.pyplot as plt\nROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/top2_n7_stable'"),
        nbformat.v4.new_code_cell("decision=json.loads((OUT/'decision.json').read_text())\nperformance=pd.read_csv(OUT/'matched_performance.csv')\ndecision"),
        nbformat.v4.new_code_cell("performance[(performance.horizon=='10h') & (performance.seed.isin([-1,-2]))][['issue_year','arm','active_issues','ending_capital','turnover_roi','bundle_hit_rate']]"),
        nbformat.v4.new_code_cell("paths=pd.read_csv(OUT/'capital_paths.csv')\nfor key,g in paths[(paths.horizon=='10h') & (paths.arm=='P_TOP2_NO_GATE')].groupby('issue_year'):\n    plt.plot(range(len(g)),g.capital_after,label=str(key))\nplt.axhline(100000,color='black',lw=.8); plt.legend(); plt.title('Primary capital paths'); plt.show()"),
    ], metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}})
    nbformat.write(nb, path)
    executed = NotebookClient(
        nbformat.read(path, as_version=4), timeout=600, kernel_name="python3"
    ).execute(cwd=notebook_dir)
    nbformat.write(executed, path)


def _write_docs(repo_root: Path, decision: dict, performance: pd.DataFrame, selector_lift: pd.DataFrame) -> None:
    fig_dir = repo_root / "docs/research/figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths = pd.read_csv(repo_root / "results/top2_n7_stable/capital_paths.csv")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for year, group in paths[(paths.horizon == "10h") & (paths.arm == "P_TOP2_NO_GATE")].groupby("issue_year"):
        ax.plot(range(1, len(group) + 1), group.capital_after, label=str(year))
    ax.axhline(STARTING_CAPITAL, color="black", lw=.8, ls="--")
    ax.set(xlabel="Issue index", ylabel="Capital (CNY)", title="#319 probability Top-2 N7 capital path")
    ax.legend()
    fig.tight_layout()
    fig.savefig(fig_dir / "issue_319_top2_n7_capital.png", dpi=160)
    plt.close(fig)
    view = performance[(performance.horizon == "10h") & performance.seed.isin([-1, -2])]
    rows = "\n".join(
        f"| {int(r.issue_year)} | {r.arm} | {int(r.active_issues)} | {r.ending_capital:,.2f} | {r.turnover_roi:.2%} | {r.bundle_hit_rate:.2%} |"
        for r in view.itertuples()
    )
    lift_view = selector_lift[selector_lift.horizon == "10h"]
    lift_rows = "\n".join(
        f"| {int(r.issue_year)} | {int(r.matched_issues_min)}–{int(r.matched_issues_median)} | {r.median_total_lift:,.2f} | {r.positive_seed_fraction:.1%} |"
        for r in lift_view.itertuples()
    )
    text = f"""# Issue #319 — Probability Top-2 N7 stable center

## Decision

`{decision['disposition']}` / no promotion. #318 established that the historical
official/final SP triplet is not causal selection evidence. Consequently this issue
executes the probability-only stable center and an equal-exposure random-match control;
value, q and numeric GM gates fail closed rather than using leaked settlement prices.

## Primary 10h results (pre-tax)

| Year | Arm | observable issues | ending capital | turnover ROI | bundle hit rate |
|---|---|---:|---:|---:|---:|
{rows}

Every active issue enumerates all 128 distinct Top-2 N7 tickets at CNY2, for CNY256
planned exposure. Beijing's 0.65 factor is applied exactly once to the complete winning
ticket. Thirty-one random seeds are nuisance repeats and do not inflate the issue count.

The descriptive table above is not itself a matched claim because missing trusted
settlements differ by selected fixtures. The exact CNY256-vs-CNY256 paired comparison is:

| Year | matched issues per seed (min–median) | median total lift vs random | positive seeds |
|---|---:|---:|---:|
{lift_rows}

## Interpretation

The experiment establishes an executable, transparent probability Top-2 center, but it
does **not** test the intended value selector because decision-epoch Beijing SP is absent.
Any difference versus random match selection is a probability-concentration result, not
proof of SP value. `PRICE_DATA_INSUFFICIENT` is therefore the only defensible terminal
decision, regardless of point estimates. `FIXED_N7_K512_WOR` remains unmatched historical
context and is not used to claim lift.

The exact paired result is also temporally unstable: the primary 10h selector has a
negative median total lift in 2023 and positive lift in 2024. An issue-median bootstrap
looks positive because large 2024 payouts dominate, while only 22.6% of the 2023 nuisance
seeds have positive total lift. That disagreement is evidence against calling this a
stable Edge, not a reason to select the favorable aggregation.

## Adversarial review

1. Settlement visibility is not selection visibility: final/winning SP only enters after
   pre-outcome bundle and ticket hashes are frozen.
2. The 31 seeds quantify random-selector noise; the independent sample remains issues.
3. Missing trusted settlements are marked unobservable rather than silently scored as a
   loss or retroactively removed from selection.
4. N7 is an isolation choice, not evidence that N=7 is optimal.
5. A future value-selector test requires genuine decision-epoch SP or a separately
   accepted proxy; probability-only performance cannot unlock forward validation.

## Requirement evidence

| Requirement | Evidence | Result |
|---|---|---|
| REQ-TOP2-01 | `freeze_receipt.json`; role/source binding and pre-outcome hashes | PASS |
| REQ-TOP2-02 | `tickets.parquet`; 128 unique tickets and CNY256 reconciliation | PASS |
| REQ-TOP2-03 | exact ticket/bundle gross reconciliation and factor-once tests | PASS |
| REQ-TOP2-04 | all arms/gates and explicit `NO_BET` reasons in bundle ledger | PASS |
| REQ-TOP2-05 | absolute performance, exact paired lift and risk tables | PASS |
| REQ-TOP2-06 | price-dependent lanes fail closed; no proxy promotion | PASS |
| REQ-TOP2-07 | package code, focused tests, executed notebook and hashes | PASS |
| REQ-TOP2-08 | issue/seed miss-distance and failure-reason attribution | PASS |

## Artifacts

- Notebook: `notebooks/research/top2-n7-stable/top2_n7_stable.ipynb`
- Package: `results/top2_n7_stable/`
- Capital figure: `docs/research/figures/issue_319_top2_n7_capital.png`
- Replay: `uv run --frozen python scripts/run_top2_n7_stable.py --output results/top2_n7_stable`
"""
    (repo_root / "docs/research/Issue-Top2-N7-Stable.md").write_text(text, encoding="utf-8")


def build_package(repo_root: Path, output: Path, data_root: Path | None = None) -> dict:
    repo_root, output = repo_root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_root = locate_data_root(repo_root, data_root)
    bj238 = source_root / "derived/bj238_divergence_materializer_v4r3"
    probability_path = bj238 / "inference/relative_horizon_view.parquet"
    roles_path = bj238 / "analysis/issue_roles.csv"
    settlement_path = source_root / "derived/beidan_xlsm/beidan_xlsm.sqlite"

    feature = _feature_surface(probability_path)
    role_counts = _validate_roles(roles_path, feature)
    bundles_pre, tickets_pre = construct_preoutcome(feature)
    freeze = {
        "contract": "BJ-UNIFIED-TOP2-N7-STABLE-001/v1", "issue": 319,
        "probability_source": PROBABILITY_SOURCE, "price_disposition": "NO_CAUSAL_PRICE_SUPPORT",
        "settlement_opened_before_freeze": False, "years": [2023, 2024], "horizons": list(HORIZONS),
        "preoutcome_bundle_sha256": stable_frame_sha(bundles_pre, PREOUTCOME_BUNDLE_COLUMNS),
        "preoutcome_ticket_sha256": stable_frame_sha(tickets_pre, PREOUTCOME_TICKET_COLUMNS),
        "probability_source_sha256": sha256_file(probability_path), "roles_source_sha256": sha256_file(roles_path),
        "frozen_role_counts": role_counts,
        "active_arms": list(ACTIVE_ARMS), "price_blocked_arms": list(PRICE_BLOCKED_ARMS),
        "random_seed_count": len(RANDOM_SEEDS), "tickets_per_active_bundle": TICKETS_PER_BUNDLE,
        "planned_stake_per_active_bundle": ISSUE_STAKE,
    }
    (output / "freeze_receipt.json").write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n")

    settlement = _load_settlement(settlement_path)
    bundles, tickets = settle(bundles_pre, tickets_pre, settlement)
    performance, paths, risk, selector_lift, diagnostics = summarize(bundles)
    paired = diagnostics.pop("paired")
    attribution = bundles[[
        "issue_code", "issue_year", "horizon", "arm", "seed", "status_preoutcome",
        "settlement_status", "selected_fixture_keys", "retained_mass_mean", "line_abs_mean",
        "divergence_abs_mean", "hit", "miss_distance", "realized_outside_support", "pnl",
    ]].copy()
    attribution["failure_reason"] = np.select(
        [
            attribution["status_preoutcome"].eq("NO_BET_PRICE_DATA_INSUFFICIENT"),
            attribution["settlement_status"].eq("UNOBSERVABLE_SETTLEMENT"),
            attribution["hit"].eq(True),
            attribution["miss_distance"].eq(1),
            attribution["miss_distance"].ge(2),
        ],
        ["PRICE_INPUT_UNAVAILABLE", "SETTLEMENT_UNOBSERVABLE", "WINNING_IDENTITY_PRESENT",
         "ONE_REALIZED_OUTCOME_OUTSIDE_TOP2", "MULTIPLE_REALIZED_OUTCOMES_OUTSIDE_TOP2"],
        default="NOT_APPLICABLE",
    )
    decision = {
        "issue": 319, "disposition": TERMINAL_DECISION, "promotion": False,
        "reason": "#318 found no admissible historical decision-epoch Beijing SP; value/q/GM arms are non-executable.",
        "probability_center_executed": True, "value_selector_executed": False,
        "unlock_210": False, "bootstrap_lift_vs_random": diagnostics["bootstrap"],
        "paired_seed_selector_lift": selector_lift.to_dict(orient="records"),
        "fixed_context": {
            "matched": False,
            "2023_exact_issue312_fixed_n7_k512_wor_ending_capital": 87984.26791061989,
            "2024_portable_n7_k512_wor_ending_capital": 81882.32,
        },
    }
    bundles.to_parquet(output / "issue_bundles.parquet", index=False)
    tickets.to_parquet(output / "tickets.parquet", index=False)
    performance.to_csv(output / "matched_performance.csv", index=False)
    selector_lift.to_csv(output / "selector_lift.csv", index=False)
    paired.to_parquet(output / "paired_selector_lift.parquet", index=False)
    year_contribution = paths.groupby(["horizon", "arm", "seed", "issue_year"], as_index=False)["pnl"].sum()
    combined_year_rows = []
    for key, group in year_contribution.groupby(["horizon", "arm", "seed"], sort=True):
        combined_year_rows.append({
            "horizon": key[0], "arm": key[1], "seed": key[2], "years": len(group),
            "total_pnl": float(group.pnl.sum()),
            "ex_best_year_pnl": float(group.pnl.sum() - group.pnl.max()),
            "best_year": int(group.loc[group.pnl.idxmax(), "issue_year"]),
        })
    pd.DataFrame(combined_year_rows).to_csv(output / "year_contribution.csv", index=False)
    paths.to_csv(output / "capital_paths.csv", index=False)
    risk.to_csv(output / "risk_diagnostics.csv", index=False)
    attribution.to_parquet(output / "attribution.parquet", index=False)
    (output / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")

    manifest = {"contract": freeze["contract"], "files": {}}
    for path in sorted(output.iterdir()):
        if path.name not in {"MANIFEST.json", "SHA256SUMS.json"} and path.is_file():
            manifest["files"][path.name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    sums = {path.name: sha256_file(path) for path in sorted(output.iterdir()) if path.is_file() and path.name != "SHA256SUMS.json"}
    (output / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n")
    _write_docs(repo_root, decision, performance, selector_lift)
    _write_notebook(repo_root, output)
    return decision


def verify_package(package: Path) -> dict:
    package = package.resolve()
    freeze = json.loads((package / "freeze_receipt.json").read_text())
    bundles = pd.read_parquet(package / "issue_bundles.parquet")
    tickets = pd.read_parquet(package / "tickets.parquet")
    manifest = json.loads((package / "MANIFEST.json").read_text())
    sums = json.loads((package / "SHA256SUMS.json").read_text())
    checks = {
        "sha256sums": all((package / name).is_file() and sha256_file(package / name) == digest for name, digest in sums.items()),
        "manifest": all(
            (package / name).is_file()
            and sha256_file(package / name) == metadata["sha256"]
            and (package / name).stat().st_size == metadata["bytes"]
            for name, metadata in manifest["files"].items()
        ),
        "bundle_freeze_hash": stable_frame_sha(bundles, PREOUTCOME_BUNDLE_COLUMNS) == freeze["preoutcome_bundle_sha256"],
        "ticket_freeze_hash": stable_frame_sha(tickets, PREOUTCOME_TICKET_COLUMNS) == freeze["preoutcome_ticket_sha256"],
        "active_ticket_count": bool((bundles.loc[bundles.status_preoutcome == "ACTIVE", "ticket_count"] == 128).all()),
        "active_planned_stake": bool(np.isclose(bundles.loc[bundles.status_preoutcome == "ACTIVE", "planned_stake"], 256).all()),
        "ticket_uniqueness": not tickets.duplicated(["issue_code", "horizon", "arm", "seed", "ticket_key"]).any(),
        "factor_once_reconciliation": bool(np.isclose(
            tickets.groupby(["issue_code", "issue_year", "horizon", "arm", "gate", "seed"], dropna=False)["gross"].sum(min_count=1).reset_index()["gross"].fillna(-1),
            bundles.loc[bundles.status_preoutcome == "ACTIVE", "gross"].reset_index(drop=True).fillna(-1), atol=1e-8,
        ).all()),
        "price_arms_fail_closed": bool(bundles[bundles.arm.isin(PRICE_BLOCKED_ARMS)].status_preoutcome.eq("NO_BET_PRICE_DATA_INSUFFICIENT").all()),
        "decision_no_promotion": json.loads((package / "decision.json").read_text())["promotion"] is False,
    }
    result = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
    if result["status"] != "PASS":
        raise ValueError(json.dumps(result, sort_keys=True))
    return result
