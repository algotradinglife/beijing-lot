#!/usr/bin/env python3
"""Exact bounded post-screening evidence for #167 Gate B v3r1.

The first pass is deliberately left immutable: it settles the full frozen
492 x 24,723 surface.  This second pass consumes that completed package,
freezes every absolute-positive and raw-Pareto aggregate cell, and replays
only that frozen set from canonical supports.  It therefore supplies paired
20,000 issue-cluster draws, BH descriptive adjustments, actual concentration
and chronology diagnostics without restarting or reducing the screen.
"""
from __future__ import annotations

import argparse, array, csv, ctypes, gzip, hashlib, importlib.util, json, math, os, shutil, statistics, subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "settle_bj167_strategy_atlas_gate_b_exact.py"
spec = importlib.util.spec_from_file_location("bj167_exact_runner", RUNNER_PATH)
R = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(R)

REPLICATES = 20_000
DRAW_SEED = 167137
CONTRACT = "bj167-gate-b-v3r1-postscreen-exact"
SCREENING_EXECUTION_HEAD = "d1717395a2ca5fc5e16554756723f296ec6053e8"
SCREENING_RUNNER_SHA256 = "4d9ee1313ac66df5cf5f41d8db12a39352c626459c7c4d55af3d5074cc560f32"
SCREENING_NATIVE_WRAPPER_SHA256 = "db6960d5a81ccde49f0bcb62a7c4424174feae1a4e754e64ef01de88a8b47829"
NATIVE_WRAPPER_PATH = ROOT / "scripts" / "bj167_exact_atlas.cpp"


def canonical_key(row: dict) -> tuple[str, str, str, str, str, str]:
    return tuple(row.get(k, "") for k in ("selector_id", "weight_source", "mechanism", "cap", "M", "seed_scope"))


def git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE).stdout.strip()


def execution_snapshot() -> dict:
    """The post-screen executable identity, captured at real start and end."""
    return {"git_head": git_head(), "runner_path": str(Path(__file__).relative_to(ROOT)),
            "runner_sha256": R.sha(Path(__file__)),
            "native_wrapper_path": str(NATIVE_WRAPPER_PATH.relative_to(ROOT)),
            "native_wrapper_sha256": R.sha(NATIVE_WRAPPER_PATH),
            "frozen_allocator_path": "scripts/bj145_fast_alloc.cpp",
            "frozen_allocator_sha256": R.sha(ROOT / "scripts" / "bj145_fast_alloc.cpp")}


def write_execution_provenance(out: Path, screen: Path, post_start: dict, post_end: dict) -> None:
    if post_start != post_end:
        raise RuntimeError("post-screen executable identity changed during run")
    # The current Python screening runner must remain byte-identical to the
    # process started at d171; the native wrapper is recorded separately
    # because it later gained bounded post-screen entry points.
    if R.sha(RUNNER_PATH) != SCREENING_RUNNER_SHA256:
        raise RuntimeError("current screening runner no longer proves d171 execution semantics")
    payload = {
        "contract": CONTRACT,
        "screening_execution": {
            "git_head": SCREENING_EXECUTION_HEAD,
            "runner_path": str(RUNNER_PATH.relative_to(ROOT)),
            "runner_sha256": SCREENING_RUNNER_SHA256,
            "native_wrapper_path": str(NATIVE_WRAPPER_PATH.relative_to(ROOT)),
            "native_wrapper_sha256": SCREENING_NATIVE_WRAPPER_SHA256,
            "screening_package": screen.name,
            "screening_manifest_sha256": R.sha(screen / "SHA256SUMS.json"),
            "screening_content_identity_sha256": R.sha(screen / "CONTENT_IDENTITY.json"),
            "semantics_proof": "runner SHA equals the process-start d171 runner; later native wrapper additions are recorded only as post-screen identity and covered by production-path tests",
        },
        "postscreen_execution_start": post_start,
        "postscreen_execution_end": post_end,
    }
    (out / "execution_provenance.json").write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")


def write_gz_rows(path: Path, fields: list[str], rows) -> None:
    with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as gb, __import__("io").TextIOWrapper(gb, newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for row in rows: w.writerow({k: row.get(k, "") for k in fields})


def write_full_atlas_chart_sources(screen: Path, out: Path, selector_rows: list[dict] | None = None,
                                   policy_rows: list[dict] | None = None) -> None:
    """Render-ready full-atlas sources, derived only from immutable screen data.

    The original screen's in-memory code predates these schema fields.  This
    companion keeps that monetary package immutable and creates a keyed chart
    layer with every deterministic dense-M arm retained once.
    """
    if selector_rows is None:
        with (R.GA / "selector_grid.csv").open(newline="") as f: selector_rows = list(csv.DictReader(f))
    if policy_rows is None:
        with (screen / "selector_policy_census.csv").open(newline="") as f: policy_rows = list(csv.DictReader(f))
    selectors = {r["selector_id"]: r for r in selector_rows}
    census = defaultdict(lambda: {"selector_policy_count": 0, "settled_policy_count": 0,
                                  "unavailable_policy_count": 0, "no_bet_policy_count": 0})
    for row in policy_rows:
        c = census[row["selector_id"]]; c["selector_policy_count"] += 1
        status = row.get("status", "")
        if status == "SETTLED": c["settled_policy_count"] += 1
        elif status == "UNAVAILABLE_CANONICAL_OUTCOME": c["unavailable_policy_count"] += 1
        elif status in {"NO_BET", "NO_BET_FROZEN"}:
            # Gate-B's pre-frozen zero-exposure policy is a no-bet, not an
            # unavailable outcome; retain it in the denominator at zero stake.
            c["no_bet_policy_count"] += 1
        else: raise RuntimeError(f"unknown selector policy status: {status}")
    with gzip.open(screen / "ensemble_metrics.csv.gz", "rt", newline="") as f:
        rows = list(csv.DictReader(f))
    full_gross = {r["selector_id"]: float(r["gross_pre_tax_yuan"])
                  for r in rows if r["mechanism"] == "FULL_ENUMERATED"}
    if set(full_gross) != set(selectors):
        raise RuntimeError("selector FULL chart control is incomplete")
    def joined(row: dict) -> dict:
        sid = row["selector_id"]
        if sid not in selectors or sid not in census: raise RuntimeError(f"chart source selector join drift: {sid}")
        outrow = dict(row); outrow.update(selectors[sid]); outrow.update(census[sid])
        gross = float(row["gross_pre_tax_yuan"]); fg = full_gross[sid]
        # Ensemble rows pool 100 seed ledgers whereas selector FULL is one
        # deterministic realization.  Compare one seed-equivalent candidate
        # gross to one matched-FULL gross; deterministic rows retain scale 1.
        scale = int(row.get("seed_count") or (100 if row["seed_scope"] == "ENSEMBLE_100" else 1))
        if scale <= 0: raise RuntimeError("invalid gross-retention normalization scale")
        normalized_gross = gross / scale
        outrow["gross_retention_normalization_scale"] = str(scale)
        outrow["normalized_stake_yuan"] = f"{float(row['stake_yuan']) / scale:.6f}"
        outrow["normalized_gross_pre_tax_yuan"] = f"{normalized_gross:.6f}"
        outrow["gross_return_retention_vs_matched_full"] = "" if fg == 0 else f"{normalized_gross / fg:.12f}"
        # The immutable primary surface retains monetary tax exactly.  Its
        # pre-screen ledger did not retain taxable ticket counts, so expose
        # count/rate as explicitly unavailable rather than inventing them.
        tax = float(row["tax_yuan"])
        outrow["tax_line_exposure_yuan"] = f"{tax / .20:.6f}"
        outrow["normalized_tax_yuan"] = f"{tax / scale:.6f}"
        outrow["normalized_tax_line_exposure_yuan"] = f"{tax / .20 / scale:.6f}"
        outrow["taxable_winning_ticket_count"] = ""
        outrow["taxable_winning_ticket_rate"] = ""
        outrow["taxable_ticket_metric_status"] = "NOT_RETAINED_IN_SCREEN_LEDGER"
        return outrow
    rendered = [joined(r) for r in rows]
    selector_fields = ["selector_id", "family", "gate_id", "top_k", "lowp_source", "lowp_threshold", "ranker",
                       "selector_policy_count", "settled_policy_count", "unavailable_policy_count", "no_bet_policy_count",
                       "stake_yuan", "gross_pre_tax_yuan", "no_tax_roi", "tax_adjusted_roi", "coverage_hit_rate",
                       "ticket_hit_rate", "capital_utilization_vs_full", "seed_mean_drawdown_no_tax_yuan"]
    write_gz_rows(out / "chart_source_selector_full_surface_v3r1.csv.gz", selector_fields,
                  (r for r in rendered if r["mechanism"] == "FULL_ENUMERATED"))
    dense_fields = ["selector_id", "family", "gate_id", "top_k", "lowp_source", "lowp_threshold", "ranker",
                    "weight_source", "mechanism", "cap", "M", "seed", "seed_scope", "stake_yuan", "gross_pre_tax_yuan",
                    "no_tax_roi", "matched_full_lift", "coverage_hit_rate", "ticket_hit_rate", "capital_utilization_vs_full"]
    write_gz_rows(out / "chart_source_full_dense_m_curve_v3r1.csv.gz", dense_fields, rendered)
    capital_fields = ["selector_id", "family", "gate_id", "top_k", "lowp_source", "lowp_threshold", "ranker",
                      "weight_source", "mechanism", "cap", "M", "seed", "seed_scope", "stake_yuan", "gross_pre_tax_yuan",
                      "no_tax_roi", "tax_adjusted_roi", "tax_yuan", "tax_line_exposure_yuan", "normalized_tax_yuan", "normalized_tax_line_exposure_yuan",
                      "gross_retention_normalization_scale", "normalized_stake_yuan", "normalized_gross_pre_tax_yuan", "gross_return_retention_vs_matched_full", "taxable_winning_ticket_count", "taxable_winning_ticket_rate",
                      "taxable_ticket_metric_status", "coverage_hit_rate", "ticket_hit_rate", "seed_mean_drawdown_no_tax_yuan",
                      "seed_gross_weighted_mean_issue_hhi", "selector_policy_count", "settled_policy_count",
                      "unavailable_policy_count", "no_bet_policy_count"]
    write_gz_rows(out / "chart_source_capital_risk_tax_hit_v3r1.csv.gz", capital_fields, rendered)


def candidate_rows(screen: Path) -> list[dict]:
    """Freeze the required union before doing any second-pass settlement."""
    selected: dict[tuple[str, str, str, str, str, str], dict] = {}
    with gzip.open(screen / "ensemble_metrics.csv.gz", "rt", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("no_tax_roi") and float(row["no_tax_roi"]) > 0 and float(row["stake_yuan"]) > 0:
                key = canonical_key(row)
                selected[key] = dict(row, candidate_inclusion="ABSOLUTE_POSITIVE")
    with (screen / "raw_pareto_front.csv").open(newline="") as f:
        for raw in csv.DictReader(f):
            key = canonical_key(raw)
            if key in selected:
                selected[key]["candidate_inclusion"] += ";RAW_PARETO"
            else:
                selected[key] = dict(raw, candidate_inclusion="RAW_PARETO")
    # The previous bounded robust screen is not final evidence, but retaining
    # its identities makes the replacement front a superset rather than a
    # winner-picked omission.
    old_robust = screen / "robust_pareto_front.csv"
    if old_robust.exists():
        with old_robust.open(newline="") as f:
            for raw in csv.DictReader(f):
                raw.setdefault("seed_scope", "ENSEMBLE_100" if raw.get("seed") == "ENSEMBLE_100" else "DETERMINISTIC")
                key = canonical_key(raw)
                if key in selected:
                    selected[key]["candidate_inclusion"] += ";PREDECLARED_ROBUST_SCREEN"
                else:
                    selected[key] = dict(raw, candidate_inclusion="PREDECLARED_ROBUST_SCREEN")
    return [selected[k] for k in sorted(selected)]


def write_candidate_freeze(out: Path, rows: list[dict], screen: Path) -> str:
    fields = ["candidate_index", "selector_id", "weight_source", "mechanism", "cap", "M", "seed", "seed_scope", "global_cell", "candidate_inclusion", "screen_no_tax_roi", "screen_matched_full_lift"]
    p = out / "candidate_freeze.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for i, row in enumerate(rows):
            row["candidate_index"] = i
            w.writerow({"candidate_index": i, "selector_id": row.get("selector_id", ""), "weight_source": row.get("weight_source", ""),
                        "mechanism": row.get("mechanism", ""), "cap": row.get("cap", ""), "M": row.get("M", ""),
                        "seed": row.get("seed", ""), "seed_scope": row.get("seed_scope", ""), "global_cell": row.get("global_cell", ""),
                        "candidate_inclusion": row["candidate_inclusion"], "screen_no_tax_roi": row.get("no_tax_roi", ""),
                        "screen_matched_full_lift": row.get("matched_full_lift", "")})
    payload = {"contract": CONTRACT, "screening_sha256s": R.sha(screen / "SHA256SUMS.json"),
               "candidate_count": len(rows), "candidate_freeze_sha256": R.sha(p),
               "inclusion_rule": "union(absolute positive aggregate cells, raw Pareto cells, prior bounded robust-screen identities)"}
    (out / "candidate_freeze.json").write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    return payload["candidate_freeze_sha256"]


def configure_native() -> ctypes.CDLL:
    lib = R.compile_engine(ROOT, "bj167_postscreen_exact.so")
    pi = ctypes.POINTER(ctypes.c_int); pd = ctypes.POINTER(ctypes.c_double); pu = ctypes.POINTER(ctypes.c_uint)
    lib.bj167_profile_allocation.argtypes = [pd, ctypes.c_int, ctypes.c_char_p, pi, pi, pi, pi, pi, pi]
    lib.bj167_paired_issue_bootstrap.argtypes = [pd, pd, pd, pd, ctypes.c_int, ctypes.c_int, pu, ctypes.c_int, pd, pd, pd]
    return lib


def profile_buffers() -> tuple[array.array, ...]:
    return (array.array("i", [0]) * (100 * 20 * 4), array.array("i", [0]) * (100 * 20 * 4),
            array.array("i", [0]) * (20 * 4), array.array("i", [0]) * (4 * 20 * 4),
            array.array("i", [0]) * (20 * 4), array.array("i", [0]) * 4)


def metric_for(candidate: dict, roles: list[dict], truth: int, profiles: dict[str, tuple[array.array, ...]]) -> tuple[int, int, int, int]:
    """Return frozen-engine ticket metrics; Python only chooses the cell."""
    mech = candidate["mechanism"]
    if mech == "FULL_ENUMERATED": return (1, 2187, 0, 0)
    if mech in {"P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE"}:
        pl, pc, ql, qc = R.derive_delete(roles)
        leg, code = (pl, pc) if mech.startswith("P_") else (ql, qc)
        actual = (truth // (3 ** (6 - leg))) % 3
        return (int(actual != code), 1458, 0, 0)
    p = profiles[candidate["weight_source"]]
    mi = R.M_GRID.index(int(candidate["M"]))
    if mech == "WR_DUPLICATE_STAKE":
        vals = [p[0][(si * 20 + mi) * 4:(si * 20 + mi + 1) * 4] for si in range(100)]
        return tuple(sum(v[j] for v in vals) for j in range(4))
    if mech == "WOR_DISTINCT":
        vals = [p[1][(si * 20 + mi) * 4:(si * 20 + mi + 1) * 4] for si in range(100)]
        return tuple(sum(v[j] for v in vals) for j in range(4))
    if mech == "RESIDUAL_SYSTEMATIC": return tuple(p[2][mi * 4:(mi + 1) * 4])
    if mech == "CAPPED_REPEAT":
        ci = R.CAPS.index(int(candidate["cap"]))
        return tuple(p[3][(ci * 20 + mi) * 4:(ci * 20 + mi + 1) * 4])
    if mech == "DETERMINISTIC_TOP_MASS": return tuple(p[4][mi * 4:(mi + 1) * 4])
    raise RuntimeError(f"unknown candidate mechanism: {mech}")


def candidate_multiplier(candidate: dict) -> int:
    return 100 if candidate["mechanism"] in {"WR_DUPLICATE_STAKE", "WOR_DISTINCT"} and candidate["seed_scope"] == "ENSEMBLE_100" else 1


def replay_candidates(rows: list[dict], issue_order: list[str], issue_meta: dict, out: Path) -> dict[str, list[array.array]]:
    R.verify_ga(); outcomes = R.load_outcomes(); selectors, selector_idx, _alloc, _cell_meta, _maps = R.load_surface()
    supports, by_issue, _ignored_order, _identity_count = R.build_supports(outcomes, selector_idx)
    with (R.GA / "selector_census.csv").open(newline="") as f: census_rows = list(csv.DictReader(f))
    R.build_policy_status(census_rows, supports, selector_idx)
    if set(issue_order) != set(by_issue): raise RuntimeError("screening issue order does not match canonical support universe")
    n, c = len(issue_order), len(rows)
    values = {name: [array.array("d", [0.0]) * n for _ in range(c)] for name in ("net", "stake", "gross", "tax", "hit", "tax_line_hit", "full_net", "full_stake", "full_gross", "full_tax")}
    by_selector: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        row["selector_index"] = selector_idx[row["selector_id"]]
        by_selector[row["selector_index"]].append(row)
    lib = configure_native(); pd = ctypes.POINTER(ctypes.c_double); pi = ctypes.POINTER(ctypes.c_int)
    for ii, issue in enumerate(issue_order):
        for support in by_issue[issue]:
            relevant = [r for si in support["eligible_selectors"] for r in by_selector.get(si, ())]
            if not relevant: continue
            need_sources = {r["weight_source"] for r in relevant if r["mechanism"] not in {"FULL_ENUMERATED", "P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE"}}
            profiles: dict[str, tuple[array.array, ...]] = {}
            for source in need_sources:
                b = profile_buffers(); roles = array.array("d", [v for role in support["roles"] for v in role["source"][source]])
                lib.bj167_profile_allocation(R.ptr(roles, ctypes.c_double), support["truth"], "|".join(support["mids"]).encode(),
                                             *(R.ptr(x, ctypes.c_int) for x in b))
                profiles[source] = b
            for candidate in relevant:
                ci = candidate["candidate_index"]
                hit, unique, duplicate, _ = metric_for(candidate, support["roles"], support["truth"], profiles)
                stake = 2.0 * (unique + duplicate); gross = support["payout"] * hit
                tax = support["payout"] * 0.20 * hit if support["payout"] >= 10_000.0 else 0.0
                values["stake"][ci][ii] += stake; values["gross"][ci][ii] += gross; values["tax"][ci][ii] += tax; values["hit"][ci][ii] += hit
                if support["payout"] >= 10_000.0: values["tax_line_hit"][ci][ii] += hit
                values["net"][ci][ii] += gross - stake
                mult = candidate_multiplier(candidate)
                full_stake = 2.0 * 2187 * mult; full_gross = support["payout"] * mult
                full_tax = support["payout"] * .20 * mult if support["payout"] >= 10_000.0 else 0.0
                values["full_stake"][ci][ii] += full_stake; values["full_gross"][ci][ii] += full_gross; values["full_tax"][ci][ii] += full_tax
                values["full_net"][ci][ii] += full_gross - full_stake
        if (ii + 1) % 10 == 0: print(f"postscreen replay issues {ii + 1}/{n}", flush=True)
    return values


def quantile(values: list[float], q: float) -> float | None:
    x = sorted(v for v in values if math.isfinite(v))
    return None if not x else x[min(len(x) - 1, max(0, int(q * len(x))))]


def point(values: array.array, stakes: array.array) -> float | None:
    denom = sum(stakes)
    return sum(values) / denom if denom else None


def bh(rows: list[dict], field: str, prefix: str, full_family_size: int) -> None:
    valid = [(i, float(r[field])) for i, r in enumerate(rows) if r.get(field, "") != ""]
    if full_family_size < len(valid):
        raise RuntimeError("searched-family count cannot be smaller than bootstrapped candidate count")
    # Unbootstrapped full-surface cells are conservatively represented as
    # p=1.  Their ordered ranks trail all finite candidate p-values, so the
    # BH adjustment below uses the immutable full search family without
    # pretending the candidate freeze was the scientific search universe.
    valid.sort(key=lambda x: x[1]); m = full_family_size; ceiling = 1.0
    # The remaining m-len(valid) implicit p=1 entries have adjusted p=1, so
    # start the monotone reverse pass at the last observed rank.
    for rank in range(len(valid), 0, -1):
        i, p = valid[rank - 1]; adjusted = min(ceiling, p * m / rank); ceiling = adjusted
        rows[i][prefix + "_bh_adjusted_p"] = adjusted
        rows[i][prefix + "_bonferroni_adjusted_p"] = min(1.0, p * m)
    for r in rows:
        r.setdefault(prefix + "_bh_adjusted_p", None); r.setdefault(prefix + "_bonferroni_adjusted_p", None)


def bootstrap_rows(rows: list[dict], values: dict[str, list[array.array]], issue_order: list[str], issue_meta: dict, out: Path, full_family_size: int) -> list[dict]:
    n, c = len(issue_order), len(rows)
    draws, draws_sha = R.build_common_draw_matrix(n, REPLICATES, DRAW_SEED)
    (out / "paired_bootstrap_draw_matrix.json").write_text(json.dumps({"seed": DRAW_SEED, "unit": "issue_instance", "issue_count": n, "replicate_count": REPLICATES, "sha256": draws_sha}, sort_keys=True, indent=2) + "\n")
    lib = configure_native(); out_rows = []
    for start in range(0, c, 32):
        end = min(c, start + 32); size = end - start
        def flat(name): return array.array("d", (x for ci in range(start, end) for x in values[name][ci]))
        cn, cs, fn, fs = (flat(name) for name in ("net", "stake", "full_net", "full_stake"))
        cr = array.array("d", [math.nan]) * (size * REPLICATES); fr = array.array("d", [math.nan]) * (size * REPLICATES); lr = array.array("d", [math.nan]) * (size * REPLICATES)
        lib.bj167_paired_issue_bootstrap(R.ptr(cn, ctypes.c_double), R.ptr(cs, ctypes.c_double), R.ptr(fn, ctypes.c_double), R.ptr(fs, ctypes.c_double), size, n, R.ptr(draws, ctypes.c_uint), REPLICATES, R.ptr(cr, ctypes.c_double), R.ptr(fr, ctypes.c_double), R.ptr(lr, ctypes.c_double))
        for local, ci in enumerate(range(start, end)):
            cand = [x for x in cr[local * REPLICATES:(local + 1) * REPLICATES] if math.isfinite(x)]
            full = [x for x in fr[local * REPLICATES:(local + 1) * REPLICATES] if math.isfinite(x)]
            lift = [x for x in lr[local * REPLICATES:(local + 1) * REPLICATES] if math.isfinite(x)]
            def pv(x):
                if not x: return None
                return min(1.0, 2.0 * min((sum(v <= 0 for v in x) + 1) / (len(x) + 1), (sum(v >= 0 for v in x) + 1) / (len(x) + 1)))
            net, stake, gross = values["net"][ci], values["stake"][ci], values["gross"][ci]
            full_net, full_stake = values["full_net"][ci], values["full_stake"][ci]
            roi, full_roi = point(net, stake), point(full_net, full_stake)
            by_year: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
            for i, issue in enumerate(issue_order): by_year[issue_meta[issue]["year"]][0] += net[i]; by_year[issue_meta[issue]["year"]][1] += stake[i]
            largest_issue = max(range(n), key=lambda i: net[i])
            ex_stake = sum(stake) - stake[largest_issue]; ex_issue = (sum(net) - net[largest_issue]) / ex_stake if ex_stake else None
            signed_year = max(by_year, key=lambda y: by_year[y][0])
            ex_year_stake = sum(s for i, s in enumerate(stake) if issue_meta[issue_order[i]]["year"] != signed_year)
            ex_year_net = sum(v for i, v in enumerate(net) if issue_meta[issue_order[i]]["year"] != signed_year)
            cum = peak = dd = 0.0
            for v, s in zip(net, stake):
                if s: cum += v; peak = max(peak, cum); dd = max(dd, peak - cum)
            total_gross = sum(gross); hhi = sum(g * g for g in gross) / (total_gross * total_gross) if total_gross else 0.0
            top = max(gross) / total_gross if total_gross else 0.0
            screen_roi = rows[ci].get("no_tax_roi", "")
            if screen_roi and abs(roi - float(screen_roi)) > 1e-12:
                raise RuntimeError(f"post-screen exact replay does not reproduce screening ROI for candidate {ci}: {roi} != {screen_roi}")
            screen_lift = rows[ci].get("matched_full_lift", "")
            if screen_lift and roi is not None and full_roi is not None and abs((roi - full_roi) - float(screen_lift)) > 1e-12:
                raise RuntimeError(f"post-screen exact replay does not reproduce screening FULL lift for candidate {ci}")
            out_rows.append({"candidate_index": ci, "candidate_point_roi": roi, "full_point_roi": full_roi,
                             "paired_lift_point": roi - full_roi if roi is not None and full_roi is not None else None,
                             "candidate_ci95_low": quantile(cand, .025), "candidate_ci95_high": quantile(cand, .975),
                             "full_ci95_low": quantile(full, .025), "full_ci95_high": quantile(full, .975),
                             "lift_ci95_low": quantile(lift, .025), "lift_ci95_high": quantile(lift, .975),
                             "candidate_two_sided_p": pv(cand), "paired_lift_two_sided_p": pv(lift),
                             "ex_largest_issue_no_tax_roi": ex_issue, "largest_signed_issue": issue_order[largest_issue],
                             "largest_signed_issue_net_yuan": net[largest_issue], "ex_largest_year_no_tax_roi": ex_year_net / ex_year_stake if ex_year_stake else None,
                             "largest_signed_year": signed_year, "drawdown_no_tax_yuan": dd, "gross_issue_hhi": hhi,
                             "gross_top_issue_share": top, "bootstrap_draw_matrix_sha256": draws_sha})
    bh(out_rows, "candidate_two_sided_p", "candidate", full_family_size)
    bh(out_rows, "paired_lift_two_sided_p", "paired_lift", full_family_size)
    for row in out_rows:
        row["candidate_freeze_count"] = len(rows)
        row["full_search_family_count"] = full_family_size
    return out_rows


def write_stability(rows: list[dict], values: dict[str, list[array.array]], issue_order: list[str], issue_meta: dict, out: Path) -> None:
    fields = ["candidate_index", "split_type", "split", "retained_issue_count", "candidate_no_tax_roi", "matched_full_no_tax_roi", "paired_lift", "candidate_stake_yuan", "matched_full_stake_yuan"]
    years = sorted({issue_meta[x]["year"] for x in issue_order}); folds = sorted({issue_meta[x]["fold"] for x in issue_order})
    with (out / "stability_year_fold_loyo.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for ci, _ in enumerate(rows):
            for split_type, names, keep in (("YEAR", years, lambda x, z: issue_meta[x]["year"] == z), ("FOLD", folds, lambda x, z: issue_meta[x]["fold"] == z), ("LOYO", years, lambda x, z: issue_meta[x]["year"] != z)):
                for name in names:
                    ix = [i for i, issue in enumerate(issue_order) if keep(issue, name)]
                    net = sum(values["net"][ci][i] for i in ix); stake = sum(values["stake"][ci][i] for i in ix)
                    fnet = sum(values["full_net"][ci][i] for i in ix); fstake = sum(values["full_stake"][ci][i] for i in ix)
                    roi = net/stake if stake else None; froi = fnet/fstake if fstake else None
                    w.writerow({"candidate_index": ci, "split_type": split_type, "split": name, "retained_issue_count": len(ix), "candidate_no_tax_roi": "" if roi is None else f"{roi:.12f}", "matched_full_no_tax_roi": "" if froi is None else f"{froi:.12f}", "paired_lift": "" if roi is None or froi is None else f"{roi-froi:.12f}", "candidate_stake_yuan": f"{stake:.6f}", "matched_full_stake_yuan": f"{fstake:.6f}"})


def write_seed_quantiles(screen: Path, out: Path) -> None:
    """Required min/max/p10/p90 summaries from the full seed-level ledger."""
    fields = ["selector_id", "weight_source", "mechanism", "cap", "M", "seed_count", "roi_min", "roi_p10", "roi_p25", "roi_median", "roi_p75", "roi_p90", "roi_max", "roi_mean", "roi_sd", "roi_mcse", "positive_roi_fraction", "lift_min", "lift_p10", "lift_p25", "lift_median", "lift_p75", "lift_p90", "lift_max", "lift_mean", "lift_sd", "lift_mcse", "positive_lift_fraction"]
    with gzip.GzipFile(filename=str(out / "seed_ensemble_quantiles.csv.gz"), mode="wb", mtime=0) as gb, __import__("io").TextIOWrapper(gb, newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for fp in sorted(screen.glob("cell_metrics-*.csv.gz")):
            groups: dict[tuple, list[tuple[float, float]]] = defaultdict(list)
            with gzip.open(fp, "rt", newline="") as src:
                for r in csv.DictReader(src):
                    if r["mechanism"] in {"WR_DUPLICATE_STAKE", "WOR_DISTINCT"} and r["no_tax_roi"] and r["matched_full_lift"]:
                        groups[(r["selector_id"], r["weight_source"], r["mechanism"], r["cap"], r["M"])].append((float(r["no_tax_roi"]), float(r["matched_full_lift"])))
            for key, pairs in sorted(groups.items()):
                if len(pairs) != 100: raise RuntimeError(f"incomplete seed ensemble {key}: {len(pairs)}")
                def summary(vals):
                    vals = sorted(vals); mean = statistics.mean(vals); sd = statistics.stdev(vals)
                    q = lambda p: vals[min(len(vals) - 1, int(p * len(vals)))]
                    return (f"{vals[0]:.12f}", f"{q(.10):.12f}", f"{q(.25):.12f}", f"{statistics.median(vals):.12f}", f"{q(.75):.12f}", f"{q(.90):.12f}", f"{vals[-1]:.12f}", f"{mean:.12f}", f"{sd:.12f}", f"{sd/math.sqrt(100):.12f}", f"{sum(v > 0 for v in vals)/100:.12f}")
                w.writerow(dict(zip(fields, (*key, 100, *summary([x[0] for x in pairs]), *summary([x[1] for x in pairs])))))


def write_outputs(rows: list[dict], boot: list[dict], values: dict[str, list[array.array]], issue_order: list[str], issue_meta: dict, out: Path) -> None:
    by_index = {x["candidate_index"]: x for x in boot}
    fields = ["candidate_index", "selector_id", "weight_source", "mechanism", "cap", "M", "seed_scope", "candidate_inclusion", "candidate_point_roi", "full_point_roi", "paired_lift_point", "candidate_ci95_low", "candidate_ci95_high", "lift_ci95_low", "lift_ci95_high", "candidate_two_sided_p", "candidate_bh_adjusted_p", "candidate_bonferroni_adjusted_p", "paired_lift_two_sided_p", "paired_lift_bh_adjusted_p", "paired_lift_bonferroni_adjusted_p", "ex_largest_issue_no_tax_roi", "ex_largest_year_no_tax_roi", "drawdown_no_tax_yuan", "gross_issue_hhi", "gross_top_issue_share", "largest_signed_issue", "largest_signed_year", "bootstrap_replicates", "bootstrap_unit", "candidate_freeze_count", "full_search_family_count", "descriptive_only"]
    joined = []
    for c in rows:
        b = by_index[c["candidate_index"]]; row = {k: c.get(k, "") for k in fields}; row.update({k: b.get(k, "") for k in fields}); row.update({"bootstrap_replicates": REPLICATES, "bootstrap_unit": "paired issue_instance", "descriptive_only": "TRUE"}); joined.append(row)
    with (out / "candidate_paired_bootstrap_20000.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in joined: w.writerow({k: "" if r.get(k) is None else (f"{r[k]:.12f}" if isinstance(r.get(k), float) else r.get(k, "")) for k in fields})
    def dominates(a, b):
        return a[0] >= b[0] and a[1] >= b[1] and a[2] >= b[2] and a[3] <= b[3] and a[4] <= b[4] and (a[0] > b[0] or a[1] > b[1] or a[2] > b[2] or a[3] < b[3] or a[4] < b[4])
    candidates = [(float(r["candidate_ci95_low"]), float(r["ex_largest_issue_no_tax_roi"]), float(r["ex_largest_year_no_tax_roi"]), float(r["drawdown_no_tax_yuan"]), float(r["gross_issue_hhi"]), r) for r in joined if r["candidate_ci95_low"] not in (None, "") and r["ex_largest_issue_no_tax_roi"] not in (None, "") and r["ex_largest_year_no_tax_roi"] not in (None, "")]
    front = []
    for x in sorted(candidates, key=lambda x: (-x[0], -x[1], -x[2], x[3], x[4], x[5]["candidate_index"])):
        if any(dominates(y, x) for y in front): continue
        front = [y for y in front if not dominates(x, y)]; front.append(x)
    with (out / "robust_pareto_front_exact.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields + ["front_definition"]); w.writeheader()
        for x in front: w.writerow(dict(x[5], front_definition="exact 20,000 paired-draw lower ROI + ex-largest issue/year ROI higher; drawdown/HHI lower"))
    # Exact issue contributions support the tax-line exposure and retention
    # charts; they are not reconstructed from aggregate tax amounts.
    with gzip.GzipFile(filename=str(out / "candidate_issue_contributions.csv.gz"), mode="wb", mtime=0) as gb, __import__("io").TextIOWrapper(gb, newline="") as f:
        fields2 = ["candidate_index", "issue_index", "issue_instance", "first_kickoff_ts", "year", "candidate_stake_yuan", "candidate_gross_yuan", "candidate_tax_yuan", "candidate_net_yuan", "matched_full_stake_yuan", "matched_full_gross_yuan", "matched_full_net_yuan"]
        w = csv.DictWriter(f, fieldnames=fields2); w.writeheader()
        for ci in range(len(rows)):
            for i, issue in enumerate(issue_order):
                w.writerow({"candidate_index": ci, "issue_index": i, "issue_instance": issue, "first_kickoff_ts": issue_meta[issue]["first_kickoff_ts"], "year": issue_meta[issue]["year"], "candidate_stake_yuan": f"{values['stake'][ci][i]:.6f}", "candidate_gross_yuan": f"{values['gross'][ci][i]:.6f}", "candidate_tax_yuan": f"{values['tax'][ci][i]:.6f}", "candidate_net_yuan": f"{values['net'][ci][i]:.6f}", "matched_full_stake_yuan": f"{values['full_stake'][ci][i]:.6f}", "matched_full_gross_yuan": f"{values['full_gross'][ci][i]:.6f}", "matched_full_net_yuan": f"{values['full_net'][ci][i]:.6f}"})
    with (out / "chart_source_tax_line_exposure_retention.csv").open("w", newline="") as f:
        fields3 = ["candidate_index", "gross_pre_tax_yuan", "matched_full_gross_yuan", "tax_yuan", "tax_line_exposure_yuan", "gross_return_retention_vs_matched_full", "after_tax_gross_retention", "tax_to_gross_fraction", "pre_tax_no_tax_roi", "tax_adjusted_roi", "tax_line_hit_ticket_count"]
        w = csv.DictWriter(f, fieldnames=fields3); w.writeheader()
        for ci, b in by_index.items():
            gross, tax, stake, full_gross = sum(values["gross"][ci]), sum(values["tax"][ci]), sum(values["stake"][ci]), sum(values["full_gross"][ci])
            w.writerow({"candidate_index": ci, "gross_pre_tax_yuan": f"{gross:.6f}", "matched_full_gross_yuan": f"{full_gross:.6f}", "tax_yuan": f"{tax:.6f}", "tax_line_exposure_yuan": f"{tax / .20:.6f}", "gross_return_retention_vs_matched_full": "" if full_gross == 0 else f"{gross/full_gross:.12f}", "after_tax_gross_retention": "" if gross == 0 else f"{(gross-tax)/gross:.12f}", "tax_to_gross_fraction": "" if gross == 0 else f"{tax/gross:.12f}", "pre_tax_no_tax_roi": "" if stake == 0 else f"{(gross-stake)/stake:.12f}", "tax_adjusted_roi": "" if stake == 0 else f"{(gross-tax-stake)/stake:.12f}", "tax_line_hit_ticket_count": f"{sum(values['tax_line_hit'][ci]):.0f}"})
    with (out / "bh_descriptive_significance.csv").open("w", newline="") as f:
        fields4 = ["candidate_index", "family", "candidate_freeze_count", "full_search_family_count", "nominal_two_sided_p", "bh_adjusted_p", "bonferroni_adjusted_p", "interpretation"]
        w = csv.DictWriter(f, fieldnames=fields4); w.writeheader()
        for r in joined:
            for family, p, bp, bonf in (("absolute_roi", r["candidate_two_sided_p"], r["candidate_bh_adjusted_p"], r["candidate_bonferroni_adjusted_p"]), ("paired_lift", r["paired_lift_two_sided_p"], r["paired_lift_bh_adjusted_p"], r["paired_lift_bonferroni_adjusted_p"])):
                w.writerow({"candidate_index": r["candidate_index"], "family": family, "candidate_freeze_count": r["candidate_freeze_count"], "full_search_family_count": r["full_search_family_count"], "nominal_two_sided_p": p, "bh_adjusted_p": bp, "bonferroni_adjusted_p": bonf, "interpretation": "descriptive post-screening adjustment; no promotion"})


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--screening-output", default="results/bj167_gate_b_strategy_atlas_v3r1_exact"); ap.add_argument("--output", default="results/bj167_gate_b_strategy_atlas_v3r1_postscreen_exact"); args = ap.parse_args()
    screen, final = ROOT / args.screening_output, ROOT / args.output
    post_start = execution_snapshot()
    if not (screen / "SHA256SUMS.json").exists(): raise RuntimeError("completed immutable screening package is required")
    sums = json.loads((screen / "SHA256SUMS.json").read_text())
    for name, digest in sums.items():
        p = screen / name
        if not p.exists() or R.sha(p) != digest: raise RuntimeError(f"screening package payload drift: {name}")
    if final.exists(): raise RuntimeError("refusing to replace immutable post-screening package")
    stage = Path(str(final) + ".stage")
    if stage.exists(): raise RuntimeError("refusing to reuse a stale staging package")
    stage.mkdir(parents=True); out = stage
    issue_rows = list(csv.DictReader((screen / "issue_order.csv").open(newline="")))
    issue_order = [r["issue_instance"] for r in issue_rows]
    issue_meta = {r["issue_instance"]: r for r in issue_rows}
    rows = candidate_rows(screen)
    write_candidate_freeze(out, rows, screen); print(f"frozen post-screening candidates={len(rows)}", flush=True)
    values = replay_candidates(rows, issue_order, issue_meta, out)
    adjustment = json.loads((screen / "multiple_search_adjustment.json").read_text())
    full_family_size = int(adjustment["tested_surface_cells"])
    boot = bootstrap_rows(rows, values, issue_order, issue_meta, out, full_family_size)
    write_stability(rows, values, issue_order, issue_meta, out)
    write_seed_quantiles(screen, out)
    write_outputs(rows, boot, values, issue_order, issue_meta, out)
    # Retain the accepted bridge in the companion package so its chart source
    # is explicit and carries the same v3r1 naming as the exact replay.
    shutil.copyfile(screen / "baseline_registry.csv", out / "baseline_registry_v3r1.csv")
    shutil.copyfile(out / "baseline_registry_v3r1.csv", out / "chart_source_baseline_bridge.csv")
    shutil.copyfile(out / "seed_ensemble_quantiles.csv.gz", out / "chart_source_seed_ensemble_quantiles.csv.gz")
    write_full_atlas_chart_sources(screen, out)
    post_end = execution_snapshot()
    write_execution_provenance(out, screen, post_start, post_end)
    (out / "settlement_card.json").write_text(json.dumps({"contract": CONTRACT, "screening_package": str(screen.name), "screening_manifest_sha256": R.sha(screen / "SHA256SUMS.json"), "screening_execution_head": SCREENING_EXECUTION_HEAD, "postscreen_execution_head": post_start["git_head"], "execution_provenance": "execution_provenance.json", "candidate_rule": "absolute positive + raw Pareto + prior robust screen", "candidate_freeze_count": len(rows), "full_search_family_count": full_family_size, "exact_replay": "frozen #145 native allocator; accepted tie behavior", "bootstrap": {"replicates": REPLICATES, "unit": "issue_instance", "shared_draw_seed": DRAW_SEED}, "primary_metric": "pre-tax no_tax_roi", "promotion_authorized": False}, sort_keys=True, indent=2) + "\n")
    (out / "README.md").write_text("# #167 post-screening exact evidence v3r1\n\nThis immutable companion package freezes the completed primary screen's absolute-positive and raw-Pareto aggregate cells, then replays those cells at ticket level. All candidate versus FULL resamples use one common 20,000-draw issue matrix. BH and Bonferroni values are descriptive post-screening adjustments only; they do not promote a policy.\n")
    R.write_file_census(out)
    R.finalize_package_identity(out, CONTRACT, {"screening_manifest_sha256": R.sha(screen / "SHA256SUMS.json"), "screening_execution_head": SCREENING_EXECUTION_HEAD, "screening_runner_sha256": SCREENING_RUNNER_SHA256, "screening_native_wrapper_sha256": SCREENING_NATIVE_WRAPPER_SHA256, "postscreen_execution_head": post_start["git_head"], "postscreen_runner_sha256": post_start["runner_sha256"], "postscreen_native_wrapper_sha256": post_start["native_wrapper_sha256"], "bootstrap_replicates": REPLICATES, "shared_draw_seed": DRAW_SEED, "allocator_sha256": R.EXPECTED_ALLOCATOR_SHA256})
    R.atomic_publish(stage, final)
    print(f"WROTE {final}", flush=True)


if __name__ == "__main__": main()
