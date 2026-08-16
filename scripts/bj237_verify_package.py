#!/usr/bin/env python3
"""#237 independent package verifier — R2 (EV re-runnable).

Re-verifies the immutable package from artifacts alone: hash integrity, schema
domains, FAIL-CLOSED line semantics (C-01), triplet normalization, causal epoch
ordering, sealed-label policy, cross-table consistency (E-01), aggregate
recomputation (C-03), and the REQ-PW06 / REQ-PW08 headline numbers.  Also
re-attacks the package (REQ-E06) with ~13 remanifested semantic tampers: each
tamper mutates the artifact AND refreshes SHA256SUMS.json (simulating a
re-manifest attack), then asserts production verify() FAILs.

Exit 0 = package verified; exit 1 = defect found.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bj237_power_lib as lib  # noqa: E402

VALID_LINES = lib.VALID_LINES
OUTCOME_CODES = lib.OUTCOME_CODES


def sha256_file(path: Path) -> str:
    return lib.sha256_file(path)


def verify(pkg: Path, root: Path | None = None,
           source_hash_cache: dict[str, str] | None = None) -> list[str]:
    """Return defect strings; empty list == verified.

    ``root`` is the worktree root used to recompute source receipts.  When
    None, source-hash receipt checks that need the live DB are skipped (the
    manifest is still checked for presence and internal consistency).
    ``source_hash_cache`` maps absolute DB path -> sha256 to avoid re-hashing
    the multi-GB xlsm DB in every tamper round.
    """
    if source_hash_cache is None:
        source_hash_cache = {}
    defects: list[str] = []

    # 1. manifest + SHA256SUMS integrity
    sums_path = pkg / "SHA256SUMS.json"
    manifest_path = pkg / "manifest.json"
    if not sums_path.exists() or not manifest_path.exists():
        defects.append("missing SHA256SUMS.json or manifest.json")
        return defects
    sums = json.loads(sums_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    for name, expected in sums.items():
        actual = sha256_file(pkg / name)
        if actual != expected:
            defects.append(f"SHA mismatch {name}: {actual[:12]} != {expected[:12]}")
    if manifest.get("contract") != "BJ-UNIFIED-POWER-FEATURE-SUPPORT-001":
        defects.append("contract mismatch")
    if not manifest.get("producer_commit_sha"):
        defects.append("producer_commit_sha missing (E-02)")

    # 2. FAIL-CLOSED line semantics (C-01)
    feats = pd.read_parquet(pkg / "power_features.parquet")
    diag = pd.read_parquet(pkg / "power_feature_diagnostics.parquet")
    if feats.empty:
        defects.append("power_features empty")
    # line_ok rows MUST carry a non-null grid line; ~line_ok rows MUST NOT.
    line_ok_rows = feats[feats["line_ok"]]
    if line_ok_rows["native_handicap_line"].isna().any():
        defects.append("C-01: line_ok rows with NULL native_handicap_line")
    bad_lines = line_ok_rows["native_handicap_line"].dropna()
    if not set(bad_lines.unique()) <= VALID_LINES:
        defects.append("line outside native BJ grid")
    no_line_ok = feats[~feats["line_ok"]]
    if no_line_ok["native_handicap_line"].notna().any():
        defects.append("C-01: ~line_ok rows carry a line value (must be NULL)")

    # 3. triplet semantics
    triplets = feats[feats["triplet_ok"]]
    sums_ = triplets.groupby(["issue", "match_idx"])["power_probability"].sum()
    if not ((sums_ - 1.0).abs() < 1e-9).all():
        defects.append("triplet normalization violated")
    if (triplets["power_probability"] < 0).any() or (triplets["power_probability"] > 1).any():
        defects.append("probability domain violated")
    if (feats.loc[~feats["line_ok"], "triplet_ok"] == True).any():  # noqa: E712
        defects.append("line-less rows marked triplet_ok")
    # every triplet_ok row must have a probability (non-null)
    if triplets["power_probability"].isna().any():
        defects.append("triplet_ok rows with NULL probability")

    # 4. causal epoch ordering (REQ-PW01)
    kick = pd.to_datetime(feats["kickoff_ts_utc"], utc=True)
    epoch = pd.to_datetime(feats["decision_epoch_utc"], utc=True)
    if (kick < epoch).any():
        defects.append(f"{int((kick < epoch).sum())} rows kickoff < epoch")
    if epoch.isna().any():
        defects.append("missing decision epoch")

    # 5. unseen mask semantics (REQ-PW03)
    unseen = feats[feats["unseen_mask"]]
    if (unseen["min_history_n"] != 0).any():
        defects.append("unseen_mask rows must have min_history_n == 0")
    seen = feats[~feats["unseen_mask"]]
    if (seen["min_history_n"] < 1).any():
        defects.append("seen rows must have min_history_n >= 1")

    # 6. sealed-label policy (REQ-PW07)
    cal = pd.read_parquet(pkg / "calibration_through_2023.parquet")
    if len(cal) and cal["year"].max() > 2023:
        defects.append("calibration opens 2024+ labels")

    # 7. cross-table consistency (E-01): every decision-facing field in
    # power_features must match its duplicate in diagnostics.
    key_cols = ["issue", "match_idx"]
    feats_key = feats.drop_duplicates(key_cols).set_index(key_cols)
    diag_key = diag.set_index(key_cols)
    common = feats_key.index.intersection(diag_key.index)
    if len(common) != len(feats_key):
        defects.append(f"diagnostics missing {len(feats_key) - len(common)} feature rows")
    for field in ("native_handicap_line", "line_ok", "unseen_mask",
                  "min_history_n", "home_team_id", "away_team_id",
                  "league", "decision_epoch_utc", "triplet_ok"):
        if field not in diag_key.columns or field not in feats_key.columns:
            continue
        a = feats_key.loc[common, field]
        b = diag_key.loc[common, field]
        if field in ("native_handicap_line",):
            a = a.fillna(-999.0)
            b = b.fillna(-999.0)
        mismatch = (a.astype(str) != b.astype(str)).sum()
        if mismatch:
            defects.append(f"E-01: cross-table mismatch on {field} ({mismatch} rows)")
    # outcome probabilities cross-check (power_p3/p1/p0 in diagnostics) —
    # only triplet_ok matches are compared (line-less rows carry no published
    # probabilities by design).
    if "power_p3" in diag_key.columns:
        f_pivot = (
            feats[feats["triplet_ok"]]
            .pivot_table(index=key_cols, columns="outcome_code",
                         values="power_probability", aggfunc="first")
        )
        # restrict to matches that are triplet_ok in features AND carry a
        # published triplet in diagnostics
        triplet_common = common.intersection(f_pivot.index)
        for code in OUTCOME_CODES:
            diag_col = f"power_p{code}"
            if diag_col not in diag_key.columns:
                continue
            if code not in f_pivot.columns:
                continue
            a = f_pivot[code].reindex(triplet_common).fillna(-1.0)
            b = diag_key.loc[triplet_common, diag_col].fillna(-2.0)
            mismatch = int(((a - b).abs() > 1e-9).sum())
            if mismatch:
                defects.append(
                    f"E-01: probability mismatch outcome {code} ({mismatch} rows)"
                )

    # 7b. per-issue digest anchor (E-01): diagnostics digest must equal the
    # manifest's build-time issue_digests map.
    issue_digests = manifest.get("issue_digests") or {}
    if issue_digests:
        diag_digests = (
            diag.groupby("issue")["history_event_sha256"].first().astype(str)
        )
        for issue, claimed in issue_digests.items():
            if issue in diag_digests.index and str(diag_digests[issue]) != str(claimed):
                defects.append(f"E-01: issue {issue} digest mismatch vs manifest")
    else:
        defects.append("E-01: manifest missing issue_digests anchor")

    # 7c. file-existence closure (E-01/E-02): every manifest-declared table and
    # every SHA256SUMS entry must exist as a file; no declared file may vanish.
    declared_tables = manifest.get("tables", {})
    for name, rel in declared_tables.items():
        if not (pkg / rel).exists():
            defects.append(f"E-02: manifest declares {rel} but file missing")
    for name in sums:
        if not (pkg / name).exists():
            defects.append(f"E-02: SHA256SUMS entry {name} missing on disk")

    # 8. aggregate recomputation (C-03): support_summary and calibration must
    # be exactly recomputable from power_features (+ labels).
    try:
        recomputed = _recompute_support(feats)
        committed = pd.read_parquet(pkg / "support_summary.parquet")
        _assert_frame_equal(recomputed, committed, "support_summary", defects)
    except Exception as exc:  # noqa: BLE001
        defects.append(f"support_summary recompute failed: {exc}")

    # calibration recompute needs the xlsm labels (available when root given);
    # otherwise check structural consistency only.  The matches frame is
    # cached so tamper rounds don't re-read the multi-GB DB every time.
    if root is not None:
        try:
            if "xlsm_matches" not in source_hash_cache:
                source_hash_cache["xlsm_matches"] = lib.load_xlsm_matches()
            matches = source_hash_cache["xlsm_matches"]
            recomputed_cal = _recompute_calibration(feats, matches)
            committed_cal = pd.read_parquet(pkg / "calibration_through_2023.parquet")
            _assert_frame_equal(recomputed_cal, committed_cal, "calibration", defects)
        except Exception as exc:  # noqa: BLE001
            defects.append(f"calibration recompute failed: {exc}")
    else:
        if len(cal):
            req_cols = {"issue", "year", "league", "native_handicap_line",
                        "outcome_code", "n", "mean_pred", "mean_actual"}
            if not req_cols.issubset(set(cal.columns)):
                defects.append("calibration missing contract key columns")

    # 9. headline numbers (REQ-PW08) — recompute from the artifact, never
    # trust the manifest's claimed numbers.
    publishable = feats[
        feats["triplet_ok"] & feats["line_ok"]
        & feats["native_handicap_line"].notna() & ~feats["unseen_mask"]
    ]
    if len(publishable) <= 234:
        defects.append("causal publishable cells not > 234")
    if publishable["issue"].nunique() <= 9:
        defects.append("causal publishable issues not > 9")

    # 10. REQ-PW06 reproduction files present
    for name in ("support_loss_waterfall.csv", "ppower_intersection_reconstruction.csv",
                 "external_football_data_census.csv", "waterfall_receipt.json"):
        if not (pkg / name).exists():
            defects.append(f"missing {name}")

    # 11. schema / receipt closure (E-02)
    schema_defects = _verify_schema(pkg, feats, diag)
    defects.extend(schema_defects)

    # 12. source receipt closure: manifest must reference the same source
    # hashes that the live xlsm DB currently has (when root provided).
    if root is not None:
        receipt = manifest.get("source_receipt", {})
        dbs = receipt.get("databases", {})
        if "xlsm" not in dbs:
            defects.append("E-02: source_receipt missing xlsm")
        else:
            xlsm = lib.XLSM_DB
            if xlsm.exists():
                key = str(xlsm)
                if key not in source_hash_cache:
                    source_hash_cache[key] = sha256_file(xlsm)
                actual = source_hash_cache[key]
                claimed = dbs["xlsm"].get("sha256")
                if claimed != actual:
                    defects.append("E-02: xlsm source hash mismatch")
        pkgs = receipt.get("packages", {})
        for name, path_attr in (
            ("bj203_issue_offsets", lib.BJ203_ISSUE_OFFSETS),
            ("bj229_inference_cells", lib.BJ229_INFERENCE_CELLS),
            ("bj180_freeze", lib.BJ180_FREEZE),
        ):
            path = root / path_attr
            if path.exists():
                actual = sha256_file(path)
                claimed = pkgs.get(name)
                if claimed != actual:
                    defects.append(f"E-02: package source hash mismatch {name}")

    return defects


def _recompute_support(feats: pd.DataFrame) -> pd.DataFrame:
    ok = feats[
        feats["triplet_ok"] & feats["line_ok"]
        & feats["native_handicap_line"].notna() & ~feats["unseen_mask"]
    ]
    return (
        ok.groupby(["issue", "year", "league", "native_handicap_line"])
        .agg(rows=("outcome_code", "count"),
             issues=("issue", "nunique"),
             matches=("match_idx", "nunique"))
        .reset_index()
    )


def _recompute_calibration(feats: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    cal = feats[
        feats["triplet_ok"] & feats["line_ok"]
        & feats["native_handicap_line"].notna()
        & feats["year"].le(2023) & ~feats["unseen_mask"]
    ].copy()
    if cal.empty:
        return pd.DataFrame(columns=["issue", "year", "league",
                                     "native_handicap_line", "outcome_code",
                                     "n", "mean_pred", "mean_actual"])
    actual = matches[["issue", "match_idx", "result_code"]].drop_duplicates(
        ["issue", "match_idx"]
    )
    actual["issue"] = actual["issue"].astype(str)
    merged = cal.merge(actual, on=["issue", "match_idx"], how="left")
    merged["actual"] = merged["result_code"].astype(str)
    valid = merged[merged["actual"].isin(OUTCOME_CODES)].copy()
    if valid.empty:
        return pd.DataFrame(columns=["issue", "year", "league",
                                     "native_handicap_line", "outcome_code",
                                     "n", "mean_pred", "mean_actual"])
    valid["hit"] = valid["outcome_code"] == valid["actual"]
    return (
        valid.groupby(["issue", "year", "league", "native_handicap_line", "outcome_code"])
        .agg(n=("hit", "count"),
             mean_pred=("power_probability", "mean"),
             mean_actual=("hit", "mean"))
        .reset_index()
    )


def _assert_frame_equal(recomputed: pd.DataFrame, committed: pd.DataFrame,
                        label: str, defects: list[str]) -> None:
    if list(recomputed.columns) != list(committed.columns):
        defects.append(f"{label}: column mismatch "
                       f"{list(recomputed.columns)} vs {list(committed.columns)}")
        return
    if len(recomputed) != len(committed):
        defects.append(f"{label}: row count mismatch {len(recomputed)} vs {len(committed)}")
        return
    a = recomputed.sort_values(recomputed.columns[:-3].tolist()).reset_index(drop=True)
    b = committed.sort_values(committed.columns[:-3].tolist()).reset_index(drop=True)
    for col in recomputed.columns:
        if recomputed[col].dtype.kind == "f":
            if not ((a[col] - b[col]).abs() < 1e-9).all():
                defects.append(f"{label}: value mismatch in {col}")
        else:
            if not (a[col] == b[col]).all():
                defects.append(f"{label}: value mismatch in {col}")


def _verify_schema(pkg: Path, feats: pd.DataFrame, diag: pd.DataFrame) -> list[str]:
    defects: list[str] = []
    schema_path = pkg / "feature_schema.json"
    if not schema_path.exists():
        defects.append("E-02: feature_schema.json missing")
        return defects
    schema = json.loads(schema_path.read_text())
    tables = schema.get("tables", {})
    expected_tables = {"power_features", "power_feature_diagnostics",
                       "support_summary", "calibration_through_2023"}
    if not expected_tables.issubset(set(tables)):
        defects.append(f"E-02: schema missing tables "
                       f"{expected_tables - set(tables)}")
    # every schema table column must exist in the physical parquet
    for name, spec in tables.items():
        parquet_path = pkg / f"{name}.parquet"
        if not parquet_path.exists():
            defects.append(f"E-02: schema declares {name}.parquet but file missing")
            continue
        frame = pd.read_parquet(parquet_path)
        declared = {c["name"] for c in spec.get("columns", [])}
        missing = declared - set(frame.columns)
        if missing:
            defects.append(f"E-02: schema columns missing from {name}: {missing}")
        # physical type spot-check for a few columns
        for c in spec.get("columns", []):
            if c["name"] in frame.columns:
                ptype = str(frame[c["name"]].dtype)
                want = c.get("physical_type", "")
                if want and want.startswith("timestamp") and "datetime" not in ptype:
                    defects.append(f"E-02: {name}.{c['name']} expected datetime got {ptype}")
    return defects


# ---------------------------------------------------------------------------
# REQ-E06 remanifested semantic tamper attacks (E-01)
# ---------------------------------------------------------------------------
def _copy_pkg(pkg: Path) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="bj237-tamper-"))
    for path in pkg.iterdir():
        if path.is_file():
            shutil.copy2(path, tmp / path.name)
    return tmp


def _remanifest(pkg: Path) -> None:
    """Refresh SHA256SUMS.json over the tampered tree (attack simulation)."""
    sums = {}
    for path in sorted(pkg.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.json":
            sums[path.name] = sha256_file(path)
    (pkg / "SHA256SUMS.json").write_text(
        json.dumps(sums, indent=2, sort_keys=True), encoding="utf-8"
    )


def tamper_attacks(pkg: Path, root: Path | None = None) -> list[str]:
    """Run ~13 remanifested semantic tampers; each MUST FAIL verification.

    Every tamper copies the package to a temp dir, mutates a decision-facing
    payload, refreshes SHA256SUMS.json (re-manifest), then asserts that
    production ``verify()`` reports at least one defect.  A tamper that passes
    verification is a delivery defect.
    """
    failures: list[str] = []
    # Cache the multi-GB xlsm hash once so 13 rounds don't re-hash it.
    source_hash_cache: dict[str, str] = {}
    if root is not None and lib.XLSM_DB.exists():
        source_hash_cache[str(lib.XLSM_DB)] = lib.sha256_file(lib.XLSM_DB)

    def run(name: str, mutator) -> None:
        tmp = _copy_pkg(pkg)
        try:
            mutator(tmp)
            _remanifest(tmp)
            defects = verify(tmp, root, source_hash_cache)
            if not defects:
                failures.append(f"{name}: tamper NOT detected after re-manifest")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # 1. outcome permutation: swap the probabilities of codes 3 and 0 on a
    #    publishable match while keeping the triplet normalized.
    def t1(tmp: Path):
        frame = pd.read_parquet(tmp / "power_features.parquet")
        pub = frame[frame["triplet_ok"]]
        idx = pub.index[0]
        issue = frame.loc[idx, "issue"]
        match_idx = frame.loc[idx, "match_idx"]
        rows = frame[
            (frame["triplet_ok"])
            & (frame["issue"] == issue)
            & (frame["match_idx"] == match_idx)
        ].index
        assert len(rows) == 3
        codes = frame.loc[rows, "outcome_code"].tolist()
        probs = frame.loc[rows, "power_probability"].tolist()
        swapped = dict(zip(codes, probs))
        # swap 3 and 0
        swapped["3"], swapped["0"] = swapped["0"], swapped["3"]
        frame.loc[rows, "power_probability"] = [swapped[c] for c in codes]
        frame.to_parquet(tmp / "power_features.parquet", index=False)
    run("tamper1_outcome_permutation", t1)

    # 2. legal line rewrite: change a line inside the grid (0.0 -> 0.5).
    def t2(tmp: Path):
        frame = pd.read_parquet(tmp / "power_features.parquet")
        idx = frame[frame["line_ok"] & (frame["native_handicap_line"] == 0.0)].index
        if len(idx):
            frame.loc[idx[0], "native_handicap_line"] = 0.5
            frame.to_parquet(tmp / "power_features.parquet", index=False)
    run("tamper2_line_rewrite", t2)

    # 3. home/away team swap.
    def t3(tmp: Path):
        frame = pd.read_parquet(tmp / "power_features.parquet")
        idx = frame.index[0]
        home, away = frame.loc[idx, "home_team_id"], frame.loc[idx, "away_team_id"]
        frame.loc[idx, "home_team_id"], frame.loc[idx, "away_team_id"] = away, home
        frame.to_parquet(tmp / "power_features.parquet", index=False)
    run("tamper3_team_swap", t3)

    # 4. league rewrite (valid string, wrong value).
    def t4(tmp: Path):
        frame = pd.read_parquet(tmp / "power_features.parquet")
        idx = frame.index[0]
        frame.loc[idx, "league"] = "__TAMPERED_LEAGUE__"
        frame.to_parquet(tmp / "power_features.parquet", index=False)
    run("tamper4_league_rewrite", t4)

    # 5. epoch shift earlier (still kickoff >= epoch must hold after shift ->
    #    we shift epoch backward by 1 day; kickoff stays, so kickoff >= epoch
    #    holds but decision_epoch_utc differs from diagnostics).
    def t5(tmp: Path):
        frame = pd.read_parquet(tmp / "power_features.parquet")
        idx = frame.index[0]
        ep = pd.to_datetime(frame.loc[idx, "decision_epoch_utc"], utc=True)
        frame.loc[idx, "decision_epoch_utc"] = ep - pd.Timedelta(days=1)
        frame.to_parquet(tmp / "power_features.parquet", index=False)
    run("tamper5_epoch_shift", t5)

    # 6. history depth forgery: inflate min_history_n of a publishable row.
    def t6(tmp: Path):
        frame = pd.read_parquet(tmp / "power_features.parquet")
        idx = frame[frame["triplet_ok"] & ~frame["unseen_mask"]].index[0]
        frame.loc[idx, "min_history_n"] = 999
        frame.to_parquet(tmp / "power_features.parquet", index=False)
    run("tamper6_history_depth_forgery", t6)

    # 7. outcome domain forgery: set a probability outside [0,1] but keep the
    #    triplet sum == 1 (e.g. 1.2 / -0.2 compensation within one match).
    def t7(tmp: Path):
        frame = pd.read_parquet(tmp / "power_features.parquet")
        pub = frame[frame["triplet_ok"]]
        idx = pub.index[0]
        match_rows = frame[
            (frame["triplet_ok"])
            & (frame["issue"] == frame.loc[idx, "issue"])
            & (frame["match_idx"] == frame.loc[idx, "match_idx"])
        ].index
        frame.loc[match_rows[0], "power_probability"] = 1.2
        frame.loc[match_rows[1], "power_probability"] = -0.2
        frame.to_parquet(tmp / "power_features.parquet", index=False)
    run("tamper7_outcome_domain_forgery", t7)

    # 8. whole-issue history digest forgery: replace every row of one issue's
    #    digest with a different valid 64-hex (keeps per-issue consistency).
    def t8(tmp: Path):
        d = pd.read_parquet(tmp / "power_feature_diagnostics.parquet")
        issue = d["issue"].iloc[0]
        d.loc[d["issue"] == issue, "history_event_sha256"] = "a" * 64
        d.to_parquet(tmp / "power_feature_diagnostics.parquet", index=False)
    run("tamper8_issue_digest_forgery", t8)

    # 9. support zeroing: drop rows from support_summary.
    def t9(tmp: Path):
        frame = pd.read_parquet(tmp / "support_summary.parquet")
        if len(frame):
            frame = frame.iloc[:-1]
            frame.to_parquet(tmp / "support_summary.parquet", index=False)
    run("tamper9_support_zeroing", t9)

    # 10. calibration forgery: change mean_actual.
    def t10(tmp: Path):
        frame = pd.read_parquet(tmp / "calibration_through_2023.parquet")
        if len(frame):
            frame.loc[frame.index[0], "mean_actual"] = 0.99
            frame.to_parquet(tmp / "calibration_through_2023.parquet", index=False)
    run("tamper10_calibration_forgery", t10)

    # 11. manifest output/source hash forgery: edit manifest's source hash.
    def t11(tmp: Path):
        manifest_path = tmp / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["source_receipt"]["databases"]["xlsm"]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest, indent=2))
    run("tamper11_manifest_source_hash", t11)

    # 12. schema clearing: remove tables from feature_schema.json.
    def t12(tmp: Path):
        schema_path = tmp / "feature_schema.json"
        schema = json.loads(schema_path.read_text())
        schema["tables"] = {}
        schema_path.write_text(json.dumps(schema, indent=2))
    run("tamper12_schema_clear", t12)

    # 13. delete support_summary file.
    def t13(tmp: Path):
        (tmp / "support_summary.parquet").unlink()
    run("tamper13_delete_support", t13)

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pkg", default="results/bj237_power_feature_support_v2")
    parser.add_argument("--root", default=None,
                        help="worktree root for source-hash recompute "
                             "(default: None = skip live-DB source checks)")
    args = parser.parse_args()
    pkg = Path(args.pkg)
    root = Path(args.root).resolve() if args.root else None

    defects = verify(pkg, root)
    if defects:
        print("DEFECTS:")
        for d in defects:
            print(" -", d)
    else:
        print("PACKAGE VERIFIED OK")

    attacks = tamper_attacks(pkg, root)
    if attacks:
        print("TAMPER GAPS:")
        for a in attacks:
            print(" -", a)
    else:
        print("TAMPER SELF-DEFENSE OK (13/13 attacks detected)")

    if defects or attacks:
        sys.exit(1)
    print("VERDICT: PASS")


if __name__ == "__main__":
    main()
