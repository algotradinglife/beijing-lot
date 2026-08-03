#!/usr/bin/env python3
"""Fail-closed bounded recovery for the interrupted #167 v3r1 Gate-B screen.

The archived screen is never modified.  This executable verifies every
archived cell shard, streams only S1_NO_GATE_K4 identities from Gate A, and
replays the preregistered bootstrap/stability target registry with the frozen
native allocator.  It deliberately has no path that evaluates the 492x24723
surface again.
"""
from __future__ import annotations

import argparse, array, csv, ctypes, gzip, hashlib, importlib.util, json, math, os, shutil, subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "settle_bj167_strategy_atlas_gate_b_exact.py"
POSTSCREEN_PATH = ROOT / "scripts" / "settle_bj167_atlas_postscreen_exact.py"
ARCHIVE_DEFAULT = ROOT / "results" / "bj167_gate_b_strategy_atlas_v3r1_exact.failed-stability-label-20260803T2247"
SELECTOR = "S1_NO_GATE_K4"
CHECKPOINT_CONTRACT = "bj167-gate-b-v3r1-bounded-recovery-checkpoint-v1"

spec = importlib.util.spec_from_file_location("bj167_exact", RUNNER_PATH)
R = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(R)
post_spec = importlib.util.spec_from_file_location("bj167_postscreen", POSTSCREEN_PATH)
POST = importlib.util.module_from_spec(post_spec); assert post_spec.loader is not None; post_spec.loader.exec_module(POST)

def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def ptr(a, typ):
    return ctypes.cast((typ * len(a)).from_buffer(a), ctypes.POINTER(typ))

def execution_snapshot():
    return {
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                    text=True, stdout=subprocess.PIPE).stdout.strip(),
        "recovery_runner_path": str(Path(__file__).relative_to(ROOT)),
        "recovery_runner_sha256": sha(Path(__file__)),
        "screen_runner_path": str(RUNNER_PATH.relative_to(ROOT)),
        "screen_runner_sha256": sha(RUNNER_PATH),
        "native_wrapper_path": "scripts/bj167_exact_atlas.cpp",
        "native_wrapper_sha256": sha(ROOT / "scripts" / "bj167_exact_atlas.cpp"),
        "frozen_allocator_path": "scripts/bj145_fast_alloc.cpp",
        "frozen_allocator_sha256": sha(ROOT / "scripts" / "bj145_fast_alloc.cpp"),
    }

def checkpoint_binding(archive: Path, census: dict, snapshot: dict) -> dict:
    """All immutable identities a resumed finalizer must reproduce exactly."""
    return {
        "contract": CHECKPOINT_CONTRACT,
        "archive_path": str(archive.relative_to(ROOT)),
        "archive_payload_sha256": census["payload_sha256"],
        "archive_anchor": census["anchor"],
        "gate_a_manifest_sha256": sha(R.GA / "SHA256SUMS.json"),
        "gate_a_content_identity_sha256": sha(R.GA / "CONTENT_IDENTITY.json"),
        "outcome_manifest_sha256": R.EXPECTED_OUTCOME_MANIFEST,
        "outcome_payload_sha256": sha(R.OUTCOMES),
        "execution": snapshot,
    }

def deterministic_gz_rows(path: Path, fields: list[str], rows) -> None:
    with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as raw, __import__("io").TextIOWrapper(raw, newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for row in rows: w.writerow({k: row.get(k, "") for k in fields})

def archive_census(archive: Path) -> dict:
    shards = sorted(archive.glob("cell_metrics-*.csv.gz"))
    if len(shards) != R.NSEL: raise RuntimeError(f"archive needs {R.NSEL} cell shards, found {len(shards)}")
    hashes, rows = {}, 0
    for p in shards:
        hashes[p.name] = sha(p)
        with gzip.open(p, "rt", newline="") as f:
            n = sum(1 for _ in csv.DictReader(f))
        if n != R.NCELL: raise RuntimeError(f"archive cell census drift {p.name}: {n}")
        rows += n
    for name in ("ensemble_metrics.csv.gz", "seed_prefix_summaries.csv.gz", "issue_cluster_bootstrap.csv", "bootstrap_target_registry.csv", "issue_order.csv"):
        p = archive / name
        if not p.exists(): raise RuntimeError(f"archive missing {name}")
        hashes[name] = sha(p)
    if rows != R.NSEL * R.NCELL: raise RuntimeError("archive total cell census drift")
    anchor = None
    with gzip.open(archive / "ensemble_metrics.csv.gz", "rt", newline="") as f:
        for row in csv.DictReader(f):
            if (row["selector_id"], row["weight_source"], row["mechanism"], row["M"], row["seed_scope"]) == (SELECTOR, "Q_WEIGHT", "WOR_DISTINCT", "64", "ENSEMBLE_100"):
                anchor = row; break
    if anchor is None: raise RuntimeError("archive lacks S1 Q/WOR/M64 ensemble anchor")
    if abs(float(anchor["no_tax_roi"]) - float(R.COMMON_SUPPORT_INCUMBENT_ROI)) > 1e-10: raise RuntimeError("archive S1 incumbent ROI anchor drift")
    if abs(float(anchor["matched_full_lift"]) - float(R.COMMON_SUPPORT_INCUMBENT_LIFT)) > 1e-10: raise RuntimeError("archive S1 matched-FULL lift anchor drift")
    return {"archive": archive.name, "cell_shards": len(shards), "cell_rows": rows, "payload_sha256": hashes,
            "anchor": {"no_tax_roi": anchor["no_tax_roi"], "matched_full_lift": anchor["matched_full_lift"]}}

def canonical_s1_support(issue, mids, roles, outcomes):
    """Build one exact S1 canonical support from retained Gate-A role rows."""
    if len(mids) != 7 or [x["match_id"] for x in roles] != mids:
        raise RuntimeError("S1 support role mismatch")
    missing = tuple(x for x in mids if x not in outcomes)
    truth_codes = tuple(outcomes[x][0] for x in mids) if not missing else tuple(-1 for _ in mids)
    payout = 2.0 * .65 * math.prod(outcomes[x][1] for x in mids) if not missing else 0.0
    return {"issue": issue, "mids": mids, "roles": roles,
            "truth": sum(max(t, 0) * (3 ** (6-i)) for i,t in enumerate(truth_codes)),
            "payout": payout, "available": not missing}

def iter_s1_supports(outcomes, selector_idx):
    """Stream the identity/role lockstep, retaining only one selector."""
    idr = R.GzipRows(sorted(R.GA.glob("selector_identities-*.csv.gz")))
    rvr = R.GzipRows(sorted(R.GA.glob("selector_role_vectors-*.csv.gz")))
    supports = {}
    row = idr.next()
    while row:
        roles = []
        for _ in range(7):
            rr = rvr.next()
            if rr is None or (rr["selector_id"], rr["issue_instance"], rr["portfolio_id"]) != (row["selector_id"], row["issue_instance"], row["portfolio_id"]):
                raise RuntimeError("Gate-A identity/role lockstep mismatch")
            roles.append(R.role_values(rr))
        if row["selector_id"] == SELECTOR:
            key = (row["issue_instance"], row["selected_match_ids"])
            if key not in supports:
                mids = row["selected_match_ids"].split("|")
                supports[key] = canonical_s1_support(row["issue_instance"], mids, roles, outcomes)
        row = idr.next()
    if not supports: raise RuntimeError("S1 stream empty")
    return supports

def target_specs(cell_by_key, maps, selector_index):
    out=[]
    for m in (64,128):
        for seed in R.SEEDS:
            out.append((f"{SELECTOR}/Q_WEIGHT/WOR_DISTINCT/M{m}/{seed}", cell_by_key[("Q_WEIGHT","WOR_DISTINCT","NA",str(m),seed)]))
    for ws,me,cap,m,label in (("Q_WEIGHT","RESIDUAL_SYSTEMATIC","NA",64,"Q_WEIGHT/RESIDUAL_SYSTEMATIC/M64"), ("Q_WEIGHT","CAPPED_REPEAT","1",64,"Q_WEIGHT/CAPPED_REPEAT/cap1/M64"), ("Q_WEIGHT","CAPPED_REPEAT","2",64,"Q_WEIGHT/CAPPED_REPEAT/cap2/M64"), ("Q_WEIGHT","CAPPED_REPEAT","4",64,"Q_WEIGHT/CAPPED_REPEAT/cap4/M64"), ("Q_WEIGHT","CAPPED_REPEAT","8",64,"Q_WEIGHT/CAPPED_REPEAT/cap8/M64"), ("Q_WEIGHT","DETERMINISTIC_TOP_MASS","NA",64,"Q_WEIGHT/DETERMINISTIC_TOP_MASS/M64")):
        out.append((f"{SELECTOR}/{label}",cell_by_key[(ws,me,cap,str(m),"NA")]))
    out += [(f"{SELECTOR}/FULL_ENUMERATED", maps["struct"]["full"]), (f"{SELECTOR}/P_MIN_GLOBAL_DELETE",maps["struct"]["p"]), (f"{SELECTOR}/Q_MIN_GLOBAL_DELETE",maps["struct"]["q"])]
    return out

def recovery_policy_status(supports):
    status = {}
    with (R.GA / "selector_census.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            if row["selector_id"] == SELECTOR:
                status[row["issue_instance"]] = "SETTLED" if int(row["selected_identity_count"]) and row.get("selection_status", "AVAILABLE") in ("AVAILABLE", "") else "NO_BET_FROZEN"
    for s in supports.values():
        if not s["available"] and status.get(s["issue"]) == "SETTLED": status[s["issue"]] = "UNAVAILABLE_CANONICAL_OUTCOME"
    return status

def load_issue_order(archive):
    with (archive / "issue_order.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, {r["issue_instance"]: i for i,r in enumerate(rows)}

def validate_archive_policy_boundary(status, supports, archive_issues):
    """Return the policy map restricted to the archived identity chronology.

    The exact screen's chronology was built from actual Gate-A identities. A
    selector census can additionally contain an explicit K-unsatisfied
    no-bet row, which has no identity and therefore no issue-array position.
    That narrow difference is safe only if it is proved to be zero-support and
    already frozen as a no-bet. Every other mismatch is scientific drift.
    """
    archive_issues = set(archive_issues)
    support_issues = {s["issue"] for s in supports.values()}
    extra = set(status) - archive_issues
    invalid_extra = sorted(
        issue for issue in extra
        if status[issue] != "NO_BET_FROZEN" or issue in support_issues
    )
    if invalid_extra:
        raise RuntimeError(
            "S1 census/archive chronology mismatch is not an explicit zero-support "
            f"frozen no-bet: {invalid_extra[:3]}"
        )
    for issue in archive_issues:
        status.setdefault(issue, "NO_BET_FROZEN")
    return {issue: status[issue] for issue in archive_issues}

def archive_target_rows(archive, selector_index):
    target = selector_index * R.NCELL
    for p in sorted(archive.glob("cell_metrics-*.csv.gz")):
        with gzip.open(p, "rt", newline="") as f:
            rows = csv.DictReader(f)
            first = next(rows, None)
            if first is None or first["selector_id"] != SELECTOR: continue
            out = {int(first["global_cell"]): first}
            out.update({int(r["global_cell"]): r for r in rows})
            if min(out) != target or len(out) != R.NCELL: raise RuntimeError("archive S1 shard/global-cell binding drift")
            return out
    raise RuntimeError("archive lacks S1 cell shard")

def configure_profile():
    lib = R.compile_engine(ROOT, "bj167_recovery_sparse.so")
    pd, pi = ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int)
    lib.bj167_profile_allocation.argtypes = [pd, ctypes.c_int, ctypes.c_char_p, pi, pi, pi, pi, pi, pi]
    return lib

def replay_bounded_targets(archive):
    R.verify_ga(); outcomes = R.load_outcomes()
    selectors, selector_idx, _, cells, maps = R.load_surface(); si = selector_idx[SELECTOR]
    support = iter_s1_supports(outcomes, selector_idx); status = recovery_policy_status(support)
    issue_rows, issue_index = load_issue_order(archive)
    status = validate_archive_policy_boundary(status, support, issue_index)
    specs = target_specs({(r["weight_source"],r["mechanism"],r["cap"],r["M"],r["seed"]):i for i,r in enumerate(cells)}, maps, si)
    nissue, ntarget = len(issue_rows), len(specs); net = [[0.0]*nissue for _ in range(ntarget)]; stake = [[0.0]*nissue for _ in range(ntarget)]
    cell_to_target = {cell:i for i,(_,cell) in enumerate(specs)}; mpos={m:i for i,m in enumerate(R.M_GRID)}
    lib = configure_profile()
    wr=array.array("i",[0])*(100*20*4); wor=array.array("i",[0])*(100*20*4); residual=array.array("i",[0])*(20*4); capped=array.array("i",[0])*(4*20*4); top=array.array("i",[0])*(20*4); full=array.array("i",[0])*4
    for s in support.values():
        ii=issue_index[s["issue"]]
        if status[s["issue"]] != "SETTLED": continue
        q=array.array("d",[v for role in s["roles"] for v in role["source"]["Q_WEIGHT"]])
        lib.bj167_profile_allocation(ptr(q,ctypes.c_double),s["truth"],"|".join(s["mids"]).encode(),ptr(wr,ctypes.c_int),ptr(wor,ctypes.c_int),ptr(residual,ctypes.c_int),ptr(capped,ctypes.c_int),ptr(top,ctypes.c_int),ptr(full,ctypes.c_int))
        pl,pc,ql,qc=R.derive_delete(s["roles"])
        for cell,ti in cell_to_target.items():
            c=cells[cell]; me=c["mechanism"]; m=int(c["M"]) if c["M"] != "NA" else 0
            if me == "WOR_DISTINCT": metric=wor[(R.SEEDS.index(c["seed"])*20+mpos[m])*4:(R.SEEDS.index(c["seed"])*20+mpos[m]+1)*4]
            elif me == "RESIDUAL_SYSTEMATIC": metric=residual[mpos[m]*4:(mpos[m]+1)*4]
            elif me == "CAPPED_REPEAT": metric=capped[(R.CAPS.index(int(c["cap"]))*20+mpos[m])*4:(R.CAPS.index(int(c["cap"]))*20+mpos[m]+1)*4]
            elif me == "DETERMINISTIC_TOP_MASS": metric=top[mpos[m]*4:(mpos[m]+1)*4]
            elif me == "FULL_ENUMERATED": metric=full
            elif me == "P_MIN_GLOBAL_DELETE": metric=(int(((s["truth"] // (3**(6-pl))) % 3) != pc),1458,0,0)
            elif me == "Q_MIN_GLOBAL_DELETE": metric=(int(((s["truth"] // (3**(6-ql))) % 3) != qc),1458,0,0)
            else: raise RuntimeError(f"unexpected bounded mechanism {me}")
            st=2.0*(metric[1]+metric[2]); stake[ti][ii] += st; net[ti][ii] += s["payout"]*metric[0]-st
    archived = archive_target_rows(archive, si)
    for ti,(_,cell) in enumerate(specs):
        row=archived[si*R.NCELL+cell]; got_st=sum(stake[ti]); got_net=sum(net[ti])
        if abs(got_st-float(row["stake_yuan"])) > 1e-6 or abs(got_net-float(row["pre_tax_net_yuan"])) > 1e-6:
            raise RuntimeError(f"bounded target replay drift for global cell {si*R.NCELL+cell}")
    return specs, issue_rows, net, stake, status

def write_sparse_checkpoint(checkpoint: Path, archive: Path, census: dict, specs, issue_rows, net, stake, status, snapshot: dict) -> Path:
    """Atomically retain the exact bounded replay before any finalization work.

    This is deliberately a standalone immutable package.  A later recovery
    phase must consume these arrays after checking both their own manifest and
    every bound input identity; it must never silently invoke the allocator
    again just because a downstream reporting step failed.
    """
    if checkpoint.exists():
        raise RuntimeError(f"refusing to replace immutable sparse checkpoint: {checkpoint}")
    stage = Path(str(checkpoint) + ".stage")
    if stage.exists():
        raise RuntimeError(f"refusing to reuse sparse checkpoint staging path: {stage}")
    stage.mkdir(parents=True)
    binding = checkpoint_binding(archive, census, snapshot)
    (stage / "checkpoint_binding.json").write_text(json.dumps(binding, sort_keys=True, indent=2) + "\n")
    (stage / "issue_order.csv").write_text((archive / "issue_order.csv").read_text())
    target_fields = ["target_index", "target", "global_cell"]
    with (stage / "target_registry.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=target_fields); w.writeheader()
        for ti, (label, cell) in enumerate(specs):
            w.writerow({"target_index": ti, "target": label, "global_cell": cell})
    def rows():
        for ti, (label, cell) in enumerate(specs):
            for ii, issue in enumerate(issue_rows):
                yield {"target_index": ti, "target": label, "global_cell": cell,
                       "issue_index": ii, "issue_instance": issue["issue_instance"],
                       "pre_tax_net_yuan": f"{net[ti][ii]:.6f}",
                       "stake_yuan": f"{stake[ti][ii]:.6f}"}
    deterministic_gz_rows(stage / "sparse_issue_arrays.csv.gz",
                          ["target_index", "target", "global_cell", "issue_index", "issue_instance", "pre_tax_net_yuan", "stake_yuan"], rows())
    summary = {
        "bounded_target_count": len(specs), "issue_count": len(issue_rows),
        "policy_status_counts": {k: list(status.values()).count(k) for k in sorted(set(status.values()))},
        "array_shape": [len(specs), len(issue_rows)],
        "replay_equivalence": "every target total stake_yuan and pre_tax_net_yuan equals archived S1 cell_metrics within 1e-6",
    }
    (stage / "checkpoint_summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    R.write_file_census(stage)
    R.finalize_package_identity(stage, CHECKPOINT_CONTRACT, {
        "archive_payload_sha256": census["payload_sha256"],
        "gate_a_manifest_sha256": binding["gate_a_manifest_sha256"],
        "gate_a_content_identity_sha256": binding["gate_a_content_identity_sha256"],
        "outcome_manifest_sha256": binding["outcome_manifest_sha256"],
        "outcome_payload_sha256": binding["outcome_payload_sha256"],
        "recovery_runner_sha256": snapshot["recovery_runner_sha256"],
        "native_wrapper_sha256": snapshot["native_wrapper_sha256"],
        "frozen_allocator_sha256": snapshot["frozen_allocator_sha256"],
    })
    R.atomic_publish(stage, checkpoint)
    return checkpoint

def verify_sparse_checkpoint(checkpoint: Path, archive: Path, census: dict, snapshot: dict | None = None):
    """Load only a fully bound sparse checkpoint; fail closed on any drift."""
    sums_path, identity_path = checkpoint / "SHA256SUMS.json", checkpoint / "CONTENT_IDENTITY.json"
    if not sums_path.exists() or not identity_path.exists():
        raise RuntimeError("sparse checkpoint lacks immutable manifest/identity")
    sums = json.loads(sums_path.read_text())
    for name, digest in sums.items():
        p = checkpoint / name
        if not p.exists() or sha(p) != digest:
            raise RuntimeError(f"sparse checkpoint payload drift: {name}")
    binding = json.loads((checkpoint / "checkpoint_binding.json").read_text())
    # The checkpoint records the executable which produced the bounded native
    # replay.  A reporting-only finalizer is intentionally a later executable:
    # bind archive inputs to the recorded producer snapshot, never silently
    # substitute today's source hash for the immutable producer provenance.
    if binding != checkpoint_binding(archive, census, binding.get("execution", {})):
        raise RuntimeError("sparse checkpoint immutable input/executable binding drift")
    with (checkpoint / "target_registry.csv").open(newline="") as f:
        specs = [(r["target"], int(r["global_cell"])) for r in csv.DictReader(f)]
    with (checkpoint / "issue_order.csv").open(newline="") as f:
        issue_rows = list(csv.DictReader(f))
    net = [[0.0] * len(issue_rows) for _ in specs]; stake = [[0.0] * len(issue_rows) for _ in specs]
    by_issue = {r["issue_instance"]: int(r["issue_index"]) for r in issue_rows}
    with gzip.open(checkpoint / "sparse_issue_arrays.csv.gz", "rt", newline="") as f:
        count = 0
        for row in csv.DictReader(f):
            ti, ii = int(row["target_index"]), by_issue.get(row["issue_instance"], -1)
            if not (0 <= ti < len(specs) and 0 <= ii < len(issue_rows)):
                raise RuntimeError("sparse checkpoint array key drift")
            net[ti][ii] = float(row["pre_tax_net_yuan"]); stake[ti][ii] = float(row["stake_yuan"]); count += 1
    if count != len(specs) * len(issue_rows):
        raise RuntimeError("sparse checkpoint array census drift")
    return specs, issue_rows, net, stake

def file_hashes(root: Path) -> dict[str, str]:
    """Exact payload census, excluding package self-manifests."""
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*"))
            if p.is_file() and p.name not in {"SHA256SUMS.json", "CONTENT_IDENTITY.json"}}

def selector_policy_details() -> tuple[list[dict], dict[str, dict]]:
    """Recreate the selector-by-issue fail-closed denominator from Gate A."""
    outcomes = R.load_outcomes()
    policies = {}
    with (R.GA / "selector_census.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            policies[(row["selector_id"], row["issue_instance"])] = {
                "selector_id": row["selector_id"], "issue_instance": row["issue_instance"],
                "status": "SETTLED" if int(row["selected_identity_count"]) and row.get("selection_status", "AVAILABLE") in {"", "AVAILABLE"} else "NO_BET_FROZEN",
                "selected_identity_count": row["selected_identity_count"],
            }
    # Identity rows establish whether *any* member of a selected policy lacks
    # an outcome.  This is intentionally policy-level, never support-level.
    rows = R.GzipRows(sorted(R.GA.glob("selector_identities-*.csv.gz")))
    row = rows.next()
    while row:
        key = (row["selector_id"], row["issue_instance"])
        p = policies.get(key)
        if p and p["status"] == "SETTLED":
            if any(mid not in outcomes for mid in row["selected_match_ids"].split("|")):
                p["status"] = "UNAVAILABLE_CANONICAL_OUTCOME"
        row = rows.next()
    if rows.f: rows.f.close()
    detail = defaultdict(lambda: {"issues": defaultdict(int), "identities": defaultdict(int), "tokens": [], "missing_matches": defaultdict(lambda: {"supports": set(), "selectors": set()})})
    rows = R.GzipRows(sorted(R.GA.glob("selector_identities-*.csv.gz")))
    row = rows.next()
    while row:
        p = policies[(row["selector_id"], row["issue_instance"])]
        detail[row["selector_id"]]["identities"][p["status"]] += 1
        if p["status"] == "SETTLED":
            detail[row["selector_id"]]["tokens"].append(f"{row['issue_instance']}|{row['portfolio_id']}")
        else:
            for mid in row["selected_match_ids"].split("|"):
                if mid not in outcomes:
                    q=detail[row["selector_id"]]["missing_matches"][mid]; q["supports"].add((row["issue_instance"],row["portfolio_id"])); q["selectors"].add(row["selector_id"])
        row = rows.next()
    if rows.f: rows.f.close()
    for p in policies.values(): detail[p["selector_id"]]["issues"][p["status"]] += 1
    return [policies[k] for k in sorted(policies)], detail

def write_policy_artifacts(stage: Path) -> list[dict]:
    rows, detail = selector_policy_details()
    fields = ["selector_id", "issue_instance", "status", "selected_identity_count"]
    with (stage / "selector_policy_census.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    shutil.copyfile(stage / "selector_policy_census.csv", stage / "chart_source_policy_status.csv")
    missing=defaultdict(lambda:{"supports":set(),"selectors":set()})
    for d in detail.values():
        for mid, q in d["missing_matches"].items(): missing[mid]["supports"].update(q["supports"]); missing[mid]["selectors"].update(q["selectors"])
    with (stage/"missing_outcome_matches.csv").open("w",newline="") as f:
        w=csv.writer(f); w.writerow(["match_id","support_count","policy_selector_count"])
        for mid,q in sorted(missing.items()): w.writerow([mid,len(q["supports"]),len(q["selectors"])])
    return rows, detail

def target_metadata(archive: Path) -> dict[int, dict]:
    result = {}
    with (archive / "bootstrap_target_registry.csv").open(newline="") as f:
        for r in csv.DictReader(f): result[int(r["global_cell"])] = r
    return result

def arrays_by_global(specs, net, stake) -> dict[int, tuple[list[float], list[float]]]:
    return {cell: (net[i], stake[i]) for i, (_, cell) in enumerate(specs)}

def aggregate_m64_wor(specs, net, stake) -> tuple[list[float], list[float]]:
    ix = [i for i, (label, _) in enumerate(specs) if "/Q_WEIGHT/WOR_DISTINCT/M64/" in label]
    if len(ix) != 100: raise RuntimeError(f"checkpoint must retain 100 S1 Q/WOR/M64 seed arrays, got {len(ix)}")
    return ([sum(net[i][j] for i in ix) for j in range(len(net[0]))],
            [sum(stake[i][j] for i in ix) for j in range(len(stake[0]))])

def write_stability_from_checkpoint(stage: Path, archive: Path, specs, issue_rows, net, stake) -> int:
    """Actual YEAR/FOLD/LOYO slices from the retained exact arrays only."""
    fields = ["target", "selector_id", "mechanism", "M", "seed_scope", "slice_type", "slice_label", "year", "fold", "loyo", "first_kickoff_ts_order", "stake_yuan", "pre_tax_net_yuan", "no_tax_roi", "scope"]
    groups = {"YEAR": sorted({r["year"] for r in issue_rows}), "FOLD": sorted({r["fold"] for r in issue_rows})}
    _, _, _, cells, _ = R.load_surface()
    registry = {r["target"]: r for r in csv.DictReader((archive / "bootstrap_target_registry.csv").open(newline=""))}
    targets = [(label, cell, n, s, registry[label], "TARGET") for (label, cell), n, s in zip(specs, net, stake)]
    n, s = aggregate_m64_wor(specs, net, stake)
    inc = registry[f"{SELECTOR}/Q_WEIGHT/WOR_DISTINCT/M64/ENSEMBLE_100"]
    targets.append((inc["target"], -1, n, s, inc, "ENSEMBLE_100"))
    count = 0
    with (stage / "stability_year_fold_loyo.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for label, cell, nets, stakes, spec, seed_scope in targets:
            mechanism, m = R.stability_mechanism_m({"role": spec["role"], "global_cell": int(spec["global_cell"] or -1)}, cells)
            for year in groups["YEAR"]:
                include = [i for i, r in enumerate(issue_rows) if r["year"] == year]
                exclude = [i for i, r in enumerate(issue_rows) if r["year"] != year]
                for kind, label2, ix in (("YEAR", year, include), ("LOYO", f"EXCLUDE_{year}", exclude)):
                    st=sum(stakes[i] for i in ix); nt=sum(nets[i] for i in ix)
                    w.writerow({"target":label,"selector_id":SELECTOR,"mechanism":mechanism,"M":m,"seed_scope":seed_scope,"slice_type":kind,"slice_label":label2,"year":year if kind=="YEAR" else "","fold":f"OOS_{year}" if kind=="YEAR" else "","loyo":f"LOYO_{year}","first_kickoff_ts_order":"first_kickoff_ts ASC; issue_instance ASC tie-break","stake_yuan":f"{st:.6f}","pre_tax_net_yuan":f"{nt:.6f}","no_tax_roi":f"{nt/st:.12f}" if st else "","scope":"CHECKPOINT_TARGETS_PLUS_ENSEMBLE_100"}); count += 1
            for fold in groups["FOLD"]:
                ix=[i for i,r in enumerate(issue_rows) if r["fold"] == fold]; st=sum(stakes[i] for i in ix); nt=sum(nets[i] for i in ix)
                w.writerow({"target":label,"selector_id":SELECTOR,"mechanism":mechanism,"M":m,"seed_scope":seed_scope,"slice_type":"FOLD","slice_label":fold,"year":fold.replace("OOS_", ""),"fold":fold,"loyo":"","first_kickoff_ts_order":"first_kickoff_ts ASC; issue_instance ASC tie-break","stake_yuan":f"{st:.6f}","pre_tax_net_yuan":f"{nt:.6f}","no_tax_roi":f"{nt/st:.12f}" if st else "","scope":"CHECKPOINT_TARGETS_PLUS_ENSEMBLE_100"}); count += 1
    return count

def write_raw_pareto(stage: Path) -> int:
    """Exact aggregate-only primary front; seed ledgers never enter it."""
    frontier = []
    def dominates(a, b):
        av=(float(a["no_tax_roi"]), float(a["matched_full_lift"]), float(a["seed_mean_drawdown_no_tax_yuan"]), float(a["seed_gross_weighted_mean_issue_hhi"]))
        bv=(float(b["no_tax_roi"]), float(b["matched_full_lift"]), float(b["seed_mean_drawdown_no_tax_yuan"]), float(b["seed_gross_weighted_mean_issue_hhi"]))
        return av[0]>=bv[0] and av[1]>=bv[1] and av[2]<=bv[2] and av[3]<=bv[3] and av != bv
    with gzip.open(stage / "ensemble_metrics.csv.gz", "rt", newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("no_tax_roi") or float(row.get("stake_yuan", 0)) <= 0: continue
            if row.get("seed_scope") not in {"ENSEMBLE_100", "DETERMINISTIC"}: continue
            if any(dominates(x, row) for x in frontier): continue
            frontier[:] = [x for x in frontier if not dominates(row, x)]
            frontier.append(row)
    fields=["selector_id","weight_source","mechanism","cap","M","seed","seed_scope","no_tax_roi","matched_full_lift","seed_mean_drawdown_no_tax_yuan","seed_gross_weighted_mean_issue_hhi","global_cell","front_definition"]
    with (stage / "raw_pareto_front.csv").open("w", newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in sorted(frontier, key=lambda r:(r["selector_id"],r["weight_source"],r["mechanism"],r["cap"],r["M"],r["seed"])):
            w.writerow({**{k:r.get(k,"") for k in fields},"front_definition":"aggregate ENSEMBLE_100 plus deterministic arms; ROI/lift high, drawdown/HHI low"})
    return len(frontier)

def write_robust_pareto(stage: Path, archive: Path, specs, issue_rows, net, stake) -> int:
    """Bounded, exact robust front from checkpoint arrays and frozen bootstrap."""
    boot={r["target"]:r for r in csv.DictReader((stage/"issue_cluster_bootstrap.csv").open(newline=""))}
    reg={r["target"]:r for r in csv.DictReader((archive/"bootstrap_target_registry.csv").open(newline=""))}
    _, si, _, _, _ = R.load_surface(); cells=archive_target_rows(archive,si[SELECTOR])
    ensemble={}
    with gzip.open(stage/"ensemble_metrics.csv.gz","rt",newline="") as f:
        for r in csv.DictReader(f): ensemble[(r["selector_id"],r["weight_source"],r["mechanism"],r["cap"],r["M"],r["seed_scope"])]=r
    candidates=[]
    def add(label,cell,nets,stakes,meta,row):
        b=boot.get(label)
        if not b or not b.get("candidate_ci95_low"): raise RuntimeError(f"bootstrap bound missing for {label}")
        total_n,total_s=sum(nets),sum(stakes); k=max(range(len(nets)),key=lambda i:nets[i]); exi=(total_n-nets[k])/(total_s-stakes[k]) if total_s-stakes[k] else 0.0
        year=defaultdict(lambda:[0.0,0.0])
        for i,(v,x) in enumerate(zip(nets,stakes)): year[issue_rows[i]["year"]][0]+=v; year[issue_rows[i]["year"]][1]+=x
        bad=max(year,key=lambda y:year[y][0]); es=sum(x for i,x in enumerate(stakes) if issue_rows[i]["year"]!=bad); en=sum(v for i,v in enumerate(nets) if issue_rows[i]["year"]!=bad)
        drawdown, hhi = robust_metric_pair(row)
        candidates.append({"selector_id":SELECTOR,"weight_source":row["weight_source"],"mechanism":row["mechanism"],"cap":row["cap"],"M":row["M"],"seed":row["seed"],"bootstrap_ci95_low":float(b["candidate_ci95_low"]),"ex_largest_issue_no_tax_roi":exi,"ex_largest_year_no_tax_roi":en/es if es else 0.0,"ex_largest_year":bad,"drawdown_no_tax_yuan":float(drawdown),"gross_issue_hhi":float(hhi),"global_cell":cell,"target_role":meta["role"]})
    for (label,cell),n,s in zip(specs,net,stake):
        meta=reg[label]
        if meta["role"] == "SEED_PANEL_SCREEN": continue
        row=cells[si[SELECTOR]*R.NCELL+cell]
        add(label,cell,n,s,meta,row)
    label=f"{SELECTOR}/Q_WEIGHT/WOR_DISTINCT/M64/ENSEMBLE_100"; n,s=aggregate_m64_wor(specs,net,stake)
    row=ensemble[(SELECTOR,"Q_WEIGHT","WOR_DISTINCT","NA","64","ENSEMBLE_100")]
    add(label,-1,n,s,reg[label],row)
    def dominates(a,b):
        av=(a["bootstrap_ci95_low"],a["ex_largest_issue_no_tax_roi"],a["ex_largest_year_no_tax_roi"],a["drawdown_no_tax_yuan"],a["gross_issue_hhi"]); bv=(b["bootstrap_ci95_low"],b["ex_largest_issue_no_tax_roi"],b["ex_largest_year_no_tax_roi"],b["drawdown_no_tax_yuan"],b["gross_issue_hhi"])
        return av[0]>=bv[0] and av[1]>=bv[1] and av[2]>=bv[2] and av[3]<=bv[3] and av[4]<=bv[4] and av!=bv
    front=[]
    for row in sorted(candidates,key=lambda r:(-r["bootstrap_ci95_low"],-r["ex_largest_issue_no_tax_roi"],-r["ex_largest_year_no_tax_roi"],r["drawdown_no_tax_yuan"],r["gross_issue_hhi"])):
        if any(dominates(x,row) for x in front): continue
        front[:]=[x for x in front if not dominates(row,x)]; front.append(row)
    fields=["selector_id","weight_source","mechanism","cap","M","seed","bootstrap_ci95_low","ex_largest_issue_no_tax_roi","ex_largest_year_no_tax_roi","ex_largest_year","drawdown_no_tax_yuan","gross_issue_hhi","global_cell","target_role","front_definition"]
    with (stage/"robust_pareto_front.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in front: w.writerow({**r,"front_definition":"checkpoint exact arrays; immutable bootstrap lower bound + ex-largest issue/year ROI high; drawdown/HHI low"})
    return len(front)

def robust_metric_pair(row: dict) -> tuple[float, float]:
    """Normalize direct-cell and aggregate metric field names explicitly."""
    drawdown = row.get("seed_mean_drawdown_no_tax_yuan", row.get("drawdown_no_tax_yuan", ""))
    hhi = row.get("seed_gross_weighted_mean_issue_hhi", row.get("gross_issue_hhi", ""))
    if drawdown == "" or hhi == "": raise RuntimeError("robust metric schema drift")
    return float(drawdown), float(hhi)

def write_baseline_registry(stage: Path, policies: list[dict], detail: dict, specs, issue_rows, net, stake) -> None:
    fields=["baseline_id","source_issue_package","source_manifest","source_gate_a_manifest","source_gate_b_manifest","outcome_input_manifest","generated_package_identity","reference_outcome_package","cohort_denominator","common_support_hash","selector","weight_vector","mechanism","M","seed_aggregation","stake_rule","pre_tax_roi","matched_full_lift","seed_mcse","positive_seed_fraction","bootstrap_lower","bootstrap_upper","ex_largest_issue_roi","ex_largest_year_roi","evidence_grade","incumbent_or_challenger","added_lever","decision_reason","outcome_boundary"]
    _, _, _, _, _ = R.load_surface()
    full_rows = {}
    incumbent = None
    with gzip.open(stage / "ensemble_metrics.csv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["mechanism"] == "FULL_ENUMERATED": full_rows[r["selector_id"]] = r
            if (r["selector_id"],r["weight_source"],r["mechanism"],r["M"],r["seed_scope"]) == (SELECTOR,"Q_WEIGHT","WOR_DISTINCT","64","ENSEMBLE_100"): incumbent=r
    if incumbent is None or len(full_rows) != R.NSEL: raise RuntimeError("baseline FULL/incumbent registry drift")
    R.assert_s1_incumbent_anchors(incumbent)
    inc_net, inc_stake = aggregate_m64_wor(specs, net, stake)
    total_net,total_stake=sum(inc_net),sum(inc_stake); k=max(range(len(inc_net)),key=lambda i:inc_net[i])
    ex_i=(total_net-inc_net[k])/(total_stake-inc_stake[k]) if total_stake-inc_stake[k] else 0.0
    year_totals=defaultdict(lambda:[0.0,0.0])
    for i,(v,x) in enumerate(zip(inc_net,inc_stake)): year_totals[issue_rows[i]["year"]][0]+=v; year_totals[issue_rows[i]["year"]][1]+=x
    ex_year=max(year_totals,key=lambda y:year_totals[y][0]); ex_st=sum(x for i,x in enumerate(inc_stake) if issue_rows[i]["year"]!=ex_year); ex_nt=sum(v for i,v in enumerate(inc_net) if issue_rows[i]["year"]!=ex_year)
    bootstrap={r["target"]:r for r in csv.DictReader((stage/"issue_cluster_bootstrap.csv").open(newline=""))}
    inc_boot=bootstrap[f"{SELECTOR}/Q_WEIGHT/WOR_DISTINCT/M64/ENSEMBLE_100"]
    prefix=next((r for r in csv.DictReader(gzip.open(stage/"seed_prefix_summaries.csv.gz","rt",newline="")) if (r["selector_id"],r["weight_source"],r["mechanism"],r["M"],r["seed_prefix"]) == (SELECTOR,"Q_WEIGHT","WOR_DISTINCT","64","100")),None)
    if prefix is None: raise RuntimeError("seed-prefix bridge missing")
    def base(**kw): x={k:"" for k in fields}; x.update(kw); return x
    with (stage / "baseline_registry.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        s1=detail[SELECTOR]; common_hash=hashlib.sha256("\n".join(sorted(s1["tokens"])).encode()).hexdigest()
        denom=lambda d: f"issue policies: SETTLED={d['issues']['SETTLED']}; UNAVAILABLE_CANONICAL_OUTCOME={d['issues']['UNAVAILABLE_CANONICAL_OUTCOME']}; NO_BET_FROZEN={d['issues']['NO_BET_FROZEN']}; identities: SETTLED={d['identities']['SETTLED']}; UNAVAILABLE_CANONICAL_OUTCOME={d['identities']['UNAVAILABLE_CANONICAL_OUTCOME']}; NO_BET_FROZEN={d['identities']['NO_BET_FROZEN']}"
        w.writerow(base(baseline_id="B167_V3R1_COMMON_SUPPORT_ENSEMBLE_100",source_issue_package="#167 Gate-B v2r3 common-support incumbent",source_manifest=R.COMMON_SUPPORT_INCUMBENT_MANIFEST,source_gate_a_manifest=R.EXPECTED_GA_MANIFEST,source_gate_b_manifest=R.COMMON_SUPPORT_INCUMBENT_MANIFEST,reference_outcome_package="#95 v2r8",cohort_denominator=denom(s1),common_support_hash=common_hash,selector=SELECTOR,weight_vector="Q_WEIGHT",mechanism="WOR_DISTINCT",M="64",seed_aggregation="ENSEMBLE_100",stake_rule="¥2 per realized ticket; per-ticket tax",pre_tax_roi=incumbent["no_tax_roi"],matched_full_lift=R.COMMON_SUPPORT_INCUMBENT_LIFT,seed_mcse=prefix["candidate_mcse_roi"],positive_seed_fraction=prefix["candidate_positive_roi_fraction"],bootstrap_lower=inc_boot["candidate_ci95_low"],bootstrap_upper=inc_boot["candidate_ci95_high"],ex_largest_issue_roi=f"{ex_i:.12f}",ex_largest_year_roi=f"{ex_nt/ex_st:.12f}" if ex_st else "",evidence_grade="DISCOVERY",incumbent_or_challenger="INCUMBENT_BRIDGE",added_lever="Q_WEIGHT + WOR_DISTINCT + M64",decision_reason="accepted v2r3 common-support incumbent; v3r1 reproduction anchored; no promotion",outcome_boundary="#95 v2r8 trusted outcomes"))
        for seed,roi,lift in (("137001",.163755668115,.321452386816),("137002",.117735771069,.275432489770),("137003",.026680342104,.184377060805)):
            w.writerow(base(baseline_id="B137_151_THREE_SEED",source_issue_package="#137/#151 Gate-B accepted anchor",source_manifest=R.BJ151_GATE_B_MANIFEST,source_gate_a_manifest=R.BJ151_GATE_A_MANIFEST,source_gate_b_manifest=R.BJ151_GATE_B_MANIFEST,reference_outcome_package="#95 v2r8",cohort_denominator="accepted three-seed complete-issue cohort",common_support_hash="accepted-anchor",selector=SELECTOR,weight_vector="Q_WEIGHT",mechanism="WOR_DISTINCT",M="64",seed_aggregation=seed,stake_rule="¥2 per realized ticket",pre_tax_roi=f"{roi:.12f}",matched_full_lift=f"{lift:.12f}",evidence_grade="DISCOVERY",incumbent_or_challenger="CHALLENGER",added_lever="WOR_DISTINCT",decision_reason="historical transfer only; not a promotion baseline",outcome_boundary="#95 v2r8 trusted outcomes"))
        w.writerow(base(baseline_id="B127_LEGACY",source_issue_package="#127 historical reference",source_manifest="a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da",reference_outcome_package="#95 v2r8",cohort_denominator="legacy reported denominator",common_support_hash="SEGMENT_SCOPE_ONLY",selector="ESP300_GM305_LOWP20",weight_vector="NA",mechanism="FULL",M="NA",seed_aggregation="NA",stake_rule="legacy",pre_tax_roi="-0.083500000000",evidence_grade="LEGACY_REFERENCE",incumbent_or_challenger="LEGACY",decision_reason="historical bridge; not recomputed",outcome_boundary="legacy source"))
        summary=json.loads((ROOT/"results"/"bj159_gate_b_outcome_settlement_v2r1"/"analysis_summary.json").read_text()); r159=next(r for r in summary["m64_seed_stability"] if int(r["n"])==7)
        if abs(float(r159["seed_no_tax_roi"]["mean"])+.222262319469)>1e-12: raise RuntimeError("#159 N7 transfer bridge drift")
        w.writerow(base(baseline_id="B159_N7_M64_TRANSFER",source_issue_package="#159 Gate-B v2r1",source_manifest=R.BJ159_GATE_B_MANIFEST,source_gate_a_manifest=R.BJ159_GATE_A_MANIFEST,source_gate_b_manifest=R.BJ159_GATE_B_MANIFEST,reference_outcome_package="#95 v2r8",cohort_denominator="N7 M64; complete issue denominator; three seed rows",common_support_hash="#159-accepted-support",selector="selected-WOR",weight_vector="NA",mechanism="WOR_DISTINCT",M="64",seed_aggregation="N7",stake_rule="#159 declared stake",pre_tax_roi=f"{float(r159['seed_no_tax_roi']['mean']):.12f}",evidence_grade="DISCOVERY",incumbent_or_challenger="TRANSFER",decision_reason="N7/M64 numeric transfer verified",outcome_boundary="#159 accepted outcome bundle"))
        for selector,row in sorted(full_rows.items()):
            d=detail[selector]; h=hashlib.sha256("\n".join(sorted(d["tokens"])).encode()).hexdigest()
            w.writerow(base(baseline_id="MATCHED_FULL",source_issue_package="#167 Gate-B v3r1 exact generated control",source_manifest=R.EXPECTED_GA_MANIFEST,source_gate_a_manifest=R.EXPECTED_GA_MANIFEST,outcome_input_manifest=R.EXPECTED_OUTCOME_MANIFEST,generated_package_identity="GENERATED_AT_FINALIZATION",reference_outcome_package="#95 v2r8",cohort_denominator=denom(d),common_support_hash=h,selector=selector,weight_vector="NA",mechanism="FULL_ENUMERATED",M="2187",seed_aggregation="DETERMINISTIC",stake_rule="¥2 per full ticket",pre_tax_roi=row["no_tax_roi"],matched_full_lift="0.000000000000",evidence_grade="DISCOVERY",incumbent_or_challenger="MATCHED_FULL",decision_reason="selector-specific fail-closed matched FULL control",outcome_boundary="#95 v2r8 trusted outcomes"))
    shutil.copyfile(stage / "baseline_registry.csv", stage / "chart_source_baseline_bridge.csv")

def write_screen_candidate_freeze(stage: Path, checkpoint: Path, rows: list[dict]) -> tuple[str, float]:
    """Freeze the exact POST candidate union without a self-referential hash."""
    by_key = {}
    with gzip.open(stage / "ensemble_metrics.csv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f): by_key[POST.canonical_key(r)] = r
    fields=["candidate_index","selector_id","weight_source","mechanism","cap","M","seed","seed_scope","global_cell","candidate_inclusion","screen_no_tax_roi","screen_matched_full_lift","screen_stake_yuan"]
    cost=0.0
    with (stage/"candidate_freeze.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for i,row in enumerate(rows):
            source=by_key.get(POST.canonical_key(row),row); st=float(source.get("stake_yuan") or 0); cost+=st
            w.writerow({"candidate_index":i,"selector_id":row.get("selector_id", ""),"weight_source":row.get("weight_source", ""),"mechanism":row.get("mechanism", ""),"cap":row.get("cap", ""),"M":row.get("M", ""),"seed":row.get("seed", ""),"seed_scope":row.get("seed_scope", ""),"global_cell":row.get("global_cell", ""),"candidate_inclusion":row["candidate_inclusion"],"screen_no_tax_roi":source.get("no_tax_roi",row.get("no_tax_roi", "")),"screen_matched_full_lift":source.get("matched_full_lift",row.get("matched_full_lift", "")),"screen_stake_yuan":f"{st:.6f}"})
    digest=sha(stage/"candidate_freeze.csv")
    (stage/"candidate_freeze.json").write_text(json.dumps({"contract":"bj167-gate-b-v3r1-recovery-finalizer-v1","screen_checkpoint_sha256s":sha(checkpoint/"SHA256SUMS.json"),"candidate_count":len(rows),"candidate_freeze_sha256":digest,"candidate_total_screen_stake_yuan":f"{cost:.6f}","inclusion_rule":"union(absolute positive aggregate cells, raw Pareto cells, robust Pareto cells)"},sort_keys=True,indent=2)+"\n")
    return digest,cost

def write_recovery_provenance(stage: Path, archive: Path, checkpoint: Path, census: dict, finalizer_start: dict, finalizer_end: dict) -> None:
    # This archive died during the stability writer.  Only that incomplete
    # payload is regenerated; every other archived input must remain bytewise.
    regenerated={"stability_year_fold_loyo.csv"}
    archive_hashes=file_hashes(archive); immutable={k:v for k,v in archive_hashes.items() if k not in regenerated}
    copied={name:sha(stage/name) for name in immutable}
    if copied != immutable: raise RuntimeError("archived immutable payload byte identity drift during finalizer staging")
    checkpoint_identity=json.loads((checkpoint/"CONTENT_IDENTITY.json").read_text())
    payload={"contract":"bj167-gate-b-v3r1-recovery-finalizer-v1","no_full_replay":True,"archive":{"path":str(archive.relative_to(ROOT)),"payload_sha256":archive_hashes,"immutable_payload_sha256":immutable,"explicitly_regenerated_incomplete_or_derived_files":sorted(regenerated),"screen_census":census},"checkpoint":{"path":str(checkpoint.relative_to(ROOT)),"content_identity_sha256":sha(checkpoint/"CONTENT_IDENTITY.json"),"producer_execution":json.loads((checkpoint/"checkpoint_binding.json").read_text())["execution"]},"finalizer_execution_start":finalizer_start,"finalizer_execution_end":finalizer_end,"archive_immutable_payloads_copied_byte_for_byte":True}
    (stage/"recovery_provenance.json").write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n")

def finalize_from_checkpoint(final_out: Path, checkpoint: Path, archive: Path, census: dict) -> dict:
    """Report-only atomic finalization.  This path never calls the allocator."""
    start=execution_snapshot(); specs, issue_rows, net, stake = verify_sparse_checkpoint(checkpoint, archive, census)
    if final_out.exists(): raise RuntimeError(f"refusing to replace immutable final output: {final_out}")
    stage=Path(str(final_out)+".stage")
    if stage.exists(): raise RuntimeError(f"refusing to reuse finalizer stage: {stage}")
    shutil.copytree(archive, stage)
    # The archive's partial writer crashed while beginning stability; replace
    # only generated reporting artifacts in a private staging directory.
    policies, detail=write_policy_artifacts(stage)
    stability_rows=write_stability_from_checkpoint(stage,archive,specs,issue_rows,net,stake)
    raw_count=write_raw_pareto(stage)
    robust_count=write_robust_pareto(stage,archive,specs,issue_rows,net,stake)
    R.write_chart_source_pareto(stage/"chart_source_pareto.csv",stage/"raw_pareto_front.csv",stage/"robust_pareto_front.csv")
    POST.write_full_atlas_chart_sources(stage,stage,policy_rows=policies)
    write_baseline_registry(stage, policies, detail, specs, issue_rows, net, stake)
    candidates=POST.candidate_rows(stage); candidate_hash,candidate_cost=write_screen_candidate_freeze(stage,checkpoint,candidates)
    counts=defaultdict(int)
    for r in policies: counts[r["status"]]+=1
    ensemble_rows=0; ensemble_100=0; deterministic=0
    with gzip.open(stage/"ensemble_metrics.csv.gz","rt",newline="") as f:
        for r in csv.DictReader(f): ensemble_rows+=1; ensemble_100 += r["seed_scope"]=="ENSEMBLE_100"; deterministic += r["seed_scope"]=="DETERMINISTIC"
    (stage/"multiple_search_adjustment.json").write_text(json.dumps({"nominal_alpha":.05,"tested_surface_cells":ensemble_rows,"ensemble_rows":ensemble_100,"deterministic_rows":deterministic,"seed_ledger_rows":R.NSEL*R.NCELL,"stochastic_ensemble_families":len(R.SOURCES)*2*len(R.M_GRID),"bonferroni_alpha_surface":.05/ensemble_rows,"sidak_alpha_surface":1-(1-.05)**(1/ensemble_rows),"primary_confirmatory_family":f"{SELECTOR}/Q_WEIGHT/WOR_DISTINCT/M64/ENSEMBLE_100 paired with selector-matched FULL","screening_vs_confirmation":"primary/raw surface uses 100-seed ensembles plus deterministic arms once; individual seed ledger diagnostic only","multiple_search_rule":"no historical aggregate promoted on nominal ROI alone; held-out/forward validation required"},sort_keys=True,indent=2)+"\n")
    missing=[r for r in csv.DictReader((stage/"missing_outcome_matches.csv").open(newline=""))]
    (stage/"source_binding.json").write_text(json.dumps({"issue":167,"contract":"GATE_B_EXACT_TICKET_REPLAY_V3R1_RECOVERY_FINALIZER","sqlite_used":False,"gate_a":{"package":"bj167_gate_a_strategy_atlas_v3r1","SHA256SUMS.json":R.EXPECTED_GA_MANIFEST,"CONTENT_IDENTITY.json":R.EXPECTED_GA_CONTENT},"outcome":{"package":"bj95_gate_b_outcome_settlement_v2r8","SHA256SUMS.json":R.EXPECTED_OUTCOME_MANIFEST,"canonical_outcome_join.csv":R.EXPECTED_OUTCOME_PAYLOAD,"rows":len(R.load_outcomes())},"accepted_gate_a_bridges":{"bj151":R.BJ151_GATE_A_MANIFEST,"bj159":R.BJ159_GATE_A_MANIFEST},"accepted_gate_b_bridges":{"bj167_v2r3_common_support":R.COMMON_SUPPORT_INCUMBENT_MANIFEST,"bj151":R.BJ151_GATE_B_MANIFEST,"bj159":R.BJ159_GATE_B_MANIFEST},"missing_outcome_matches":[r["match_id"] for r in missing],"policy_denominator":"selector×issue; any missing selected identity closes policy","source_files":["#167 Gate-A v3r1 selector/role/allocation shards","#95 v2r8 canonical_outcome_join.csv","#167 v2r3 common-support incumbent","#151 Gate-A/Gate-B settlement","#159 Gate-A/Gate-B settlement"],"chronology_key":"first_kickoff_ts, issue_instance"},sort_keys=True,indent=2)+"\n")
    (stage/"settlement_card.json").write_text(json.dumps({"issue":167,"contract":"GATE_B_EXACT_TICKET_REPLAY_V3R1_RECOVERY_FINALIZER","gate_a_manifest":R.EXPECTED_GA_MANIFEST,"gate_a_content_identity":R.EXPECTED_GA_CONTENT,"outcome_manifest_sha256":R.EXPECTED_OUTCOME_MANIFEST,"outcome_payload_sha256":R.EXPECTED_OUTCOME_PAYLOAD,"bridge_manifests":{"bj167_gate_b_v2r3":R.COMMON_SUPPORT_INCUMBENT_MANIFEST,"bj151_gate_a":R.BJ151_GATE_A_MANIFEST,"bj151_gate_b":R.BJ151_GATE_B_MANIFEST,"bj159_gate_a":R.BJ159_GATE_A_MANIFEST,"bj159_gate_b":R.BJ159_GATE_B_MANIFEST},"no_full_replay":True,"checkpoint_array_shape":[len(specs),len(issue_rows)],"selector_count":R.NSEL,"cell_count":R.NCELL,"policy_status_counts":dict(counts),"missing_match_count":len(missing),"seed_panel":list(R.SEEDS),"seed_prefixes":[3,10,25,50,100],"M_grid":list(R.M_GRID),"caps":list(R.CAPS),"stability_row_count":stability_rows,"raw_pareto_count":raw_count,"robust_pareto_count":robust_count,"candidate_freeze_count":len(candidates),"candidate_freeze_sha256":candidate_hash,"candidate_cost_rule":"screen stake_yuan is reported per frozen ensemble/deterministic cell; no companion settlement authorized","primary_metric":"pre-tax no_tax_roi","tax_rule":"20% per independent winning ¥2 ticket gross >= ¥10000; no pooling","outcome_boundary":"#95 v2r8 only; no SQLite fallback; selector×issue fail-closed","matched_full_denominator":"identical SETTLED selector×issue policies","bootstrap":"one immutable common deterministic issue draw matrix; checkpoint retains bounded target arrays","chart_sources":["selector_full_surface","allocation_lift_fixed_M64","full_dense_M_ensemble_curves","absolute_lift_heatmaps","capital_risk_tax_hit_frontiers","raw_robust_aggregate_pareto","seed_convergence","baseline_bridge"],"promotion_authorized":False,"chronology_key":"first_kickoff_ts, issue_instance"},sort_keys=True,indent=2)+"\n")
    (stage/"README.md").write_text("# #167 v3r1 recovered final screen\n\nThis atomic recovery finalizes immutable archived exact-screen payloads and the PI-audited 209×343 sparse checkpoint. It does not replay the 492×24,723 scientific surface and does not authorize companion settlement or promotion.\n")
    end=execution_snapshot()
    if start != end: raise RuntimeError("finalizer executable identity changed in flight")
    write_recovery_provenance(stage,archive,checkpoint,census,start,end)
    R.write_file_census(stage)
    R.finalize_package_identity(stage,"bj167-gate-b-v3r1-recovery-finalizer-v1",{"archive_payload_sha256":census["payload_sha256"],"checkpoint_content_identity_sha256":sha(checkpoint/"CONTENT_IDENTITY.json"),"no_full_replay":True,"finalizer_execution":end})
    R.atomic_publish(stage,final_out)
    return {"final_output":str(final_out),"candidate_freeze_count":len(candidates),"candidate_cost_yuan":candidate_cost,"raw_pareto_count":raw_count,"robust_pareto_count":robust_count,"stability_rows":stability_rows,"policy_status_counts":dict(counts)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--archive",type=Path,default=ARCHIVE_DEFAULT); ap.add_argument("--verify-only",action="store_true"); ap.add_argument("--checkpoint",type=Path,default=ROOT / "results" / "bj167_gate_b_strategy_atlas_v3r1_recovery_checkpoint_v1"); ap.add_argument("--resume-checkpoint",action="store_true"); ap.add_argument("--finalize-output",type=Path); args=ap.parse_args()
    census=archive_census(args.archive); snapshot=execution_snapshot(); print(json.dumps(census,sort_keys=True),flush=True)
    if args.verify_only: return
    if args.resume_checkpoint:
        if args.finalize_output:
            print(json.dumps(finalize_from_checkpoint(args.finalize_output,args.checkpoint,args.archive,census),sort_keys=True),flush=True)
        else:
            specs, issue_rows, net, stake = verify_sparse_checkpoint(args.checkpoint, args.archive, census, snapshot)
            print(json.dumps({"checkpoint": str(args.checkpoint), "resume": "verified", "bounded_target_count": len(specs), "issue_count": len(issue_rows)}, sort_keys=True), flush=True)
        return
    specs, issue_rows, net, stake, status = replay_bounded_targets(args.archive)
    checkpoint = write_sparse_checkpoint(args.checkpoint, args.archive, census, specs, issue_rows, net, stake, status, snapshot)
    print(json.dumps({"checkpoint":str(checkpoint),"bounded_target_count":len(specs),"issue_count":len(issue_rows),"policy_status_counts":{k:list(status.values()).count(k) for k in sorted(set(status.values()))}},sort_keys=True),flush=True)

if __name__ == "__main__": main()
