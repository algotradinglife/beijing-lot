#!/usr/bin/env python3
"""Exact ticket-level Gate-B settlement for #167.

The frozen Gate-A surface is deliberately kept intact: 492 selectors and
24,723 effective allocation cells.  Settlement is factored only by the
outcome-identical N7 support (not by selector or cell), then joined back to
every selector membership.  Every stochastic mechanism is a realized ticket
ledger, with one shared maximum-M prefix for each seed and support.
"""
from __future__ import annotations

import argparse, array, csv, ctypes, gzip, hashlib, heapq, json, math, os, shutil, statistics, subprocess, sys, time
from collections import defaultdict
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 28
# This runner is executed from the dedicated nested worktree so the large
# frozen inputs and generated package never touch the user's /tmp.
ROOT = Path(__file__).resolve().parents[1]
GA = ROOT / "results" / "bj167_gate_a_strategy_atlas_v3r1"
OUTCOMES = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8" / "canonical_outcome_join.csv"
OUTCOME_DIR = OUTCOMES.parent
EXPECTED_GA_MANIFEST = "5a82422755723453638d25c90f91213da046a9e7bed87a851b2e5700faa9c724"
EXPECTED_GA_CONTENT = "0806185a7a68b99fd2a6a465308d11e2886995f992bfa722adb287a4e6a4d147"
EXPECTED_OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
EXPECTED_OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
EXPECTED_ALLOCATOR_SHA256 = "5f8f5d75dd15758e62dd2a05f7b674cb12824b38ccba35cfee772e8904a8bd93"
NSEL, NCELL, NROLE, NSUPPORT = 492, 24723, 9142973, 36830
M_GRID = (16,32,48,64,80,96,112,128,144,160,176,192,208,224,240,256,512,1024,1458,2187)
SEEDS = tuple(f"137{i:03d}" for i in range(1, 101))
CAPS = (1,2,4,8)
SOURCES = ("MODEL_P_CAL","MARKET_WF_CAL","BLEND_A25","BLEND_A50","BLEND_A75","Q_WEIGHT")
CODE_ORD = {"3": 0, "1": 1, "0": 2}
SOURCE_COLUMNS = {
    "MODEL_P_CAL": ("p_model3","p_model1","p_model0"),
    "MARKET_WF_CAL": ("p_market_cal3","p_market_cal1","p_market_cal0"),
    "BLEND_A25": ("p_blend_a25_3","p_blend_a25_1","p_blend_a25_0"),
    "BLEND_A50": ("p_blend_a50_3","p_blend_a50_1","p_blend_a50_0"),
    "BLEND_A75": ("p_blend_a75_3","p_blend_a75_1","p_blend_a75_0"),
    "Q_WEIGHT": ("q_weight3","q_weight1","q_weight0"),
}

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def verify_ga() -> None:
    sums = json.loads((GA / "SHA256SUMS.json").read_text())
    if sha(GA / "SHA256SUMS.json") != EXPECTED_GA_MANIFEST:
        raise RuntimeError("Gate-A SHA256SUMS.json does not match accepted v3r1 manifest")
    json.loads((GA / "CONTENT_IDENTITY.json").read_text())
    if sha(GA / "CONTENT_IDENTITY.json") != EXPECTED_GA_CONTENT:
        raise RuntimeError("Gate-A content identity does not match accepted v3r1 package")
    for name, digest in sums.items():
        if name in {"SHA256SUMS.json", "CONTENT_IDENTITY.json"}: continue
        p = GA / name
        if not p.exists() or sha(p) != digest: raise RuntimeError(f"Gate-A payload hash mismatch: {name}")
    allocator = ROOT / "scripts" / "bj145_fast_alloc.cpp"
    if sha(allocator) != EXPECTED_ALLOCATOR_SHA256:
        raise RuntimeError("frozen bj145 allocator source hash drift")

def load_outcomes() -> dict[str, tuple[int,float,str]]:
    if sha(OUTCOME_DIR / "SHA256SUMS.json") != EXPECTED_OUTCOME_MANIFEST:
        raise RuntimeError("canonical outcome SHA256SUMS.json drift")
    sums=json.loads((OUTCOME_DIR / "SHA256SUMS.json").read_text())
    if sums.get("canonical_outcome_join.csv") != EXPECTED_OUTCOME_PAYLOAD or sha(OUTCOMES) != EXPECTED_OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")
    out = {}
    with OUTCOMES.open(newline="") as f:
        for r in csv.DictReader(f):
            if r["result_code"] not in CODE_ORD or r["settlement_quality"] != "trusted" or r["has_trusted_settlement"] != "1":
                raise RuntimeError("canonical outcome bundle contains untrusted row")
            sp = float(r["winning_sp"])
            if sp <= 0: raise RuntimeError("canonical outcome bundle contains nonpositive SP")
            out[r["match_id"]] = (CODE_ORD[r["result_code"]], sp, r["winning_sp_source"])
    return out

def parse_key(r: dict) -> tuple[str,str,str,int,str]:
    return (r["weight_source"], r["mechanism"], r["cap"], int(r["M"]) if r["M"] != "NA" else -1, r["seed"])

class GzipRows:
    def __init__(self, paths):
        self.paths = [Path(p) for p in paths]; self.i = 0; self.f = None; self.r = None
        self.header = None; self._open()
    def _open(self):
        if self.f: self.f.close()
        if self.i >= len(self.paths): self.r = None; return
        self.f = gzip.open(self.paths[self.i], "rt", newline=""); self.i += 1
        self.r = csv.DictReader(self.f); self.header = self.r.fieldnames
    def next(self):
        if self.r is None: return None
        x = next(self.r, None)
        while x is None:
            self._open();
            if self.r is None: return None
            x = next(self.r, None)
        return x

def derive_delete(roles):
    # Frozen structural rule: P deletes the lowest p_min role, then its
    # lowest model-p code; Q deletes the globally lowest q-weight code.
    p_leg = min(range(7), key=lambda i: (roles[i]["p_min"], i))
    p_code = min(range(3), key=lambda c: (roles[p_leg]["p_model"][c], c))
    q_leg, q_code = min(((i,c) for i in range(7) for c in range(3)), key=lambda x: (roles[x[0]]["q_weight"][x[1]], x[0], x[1]))
    return p_leg, p_code, q_leg, q_code

def money(x): return f"{x:.6f}"
def ratio(net, stake): return "" if stake == 0 else f"{net/stake:.12f}"

COMMON_SUPPORT_INCUMBENT_ROI = "-0.132793126135"
COMMON_SUPPORT_INCUMBENT_LIFT = "0.024903592566"
COMMON_SUPPORT_INCUMBENT_MANIFEST = "e604ac63a977a375acc4808eb822cd7272fe52dac9d16ff646894677d43a9668"
BJ151_GATE_A_MANIFEST = "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6"
BJ151_GATE_B_MANIFEST = "7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2"
BJ159_GATE_A_MANIFEST = "a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325"
BJ159_GATE_B_MANIFEST = "17b42f65b834f2b5afff0e52795588f95340d76810f7faec75b193b6eecc4cc8"

def aggregate_ensemble_group(group, matched_full_stake, comparable_incumbent_roi=None, comparable_incumbent_manifest=""):
    """Aggregate one exact cell seed group for the primary atlas surface."""
    me=group[0]["mechanism"]; stochastic=me in {"WR_DUPLICATE_STAKE","WOR_DISTINCT"}
    if stochastic:
        if len(group)!=100 or len({x["seed"] for x in group})!=100:
            raise RuntimeError(f"ensemble seed group incomplete: {len(group)}")
        seed_count=100; seed_scope="ENSEMBLE_100"; seed="ENSEMBLE_100"
    else:
        if len(group)!=1: raise RuntimeError("deterministic group not singleton")
        seed_count=1; seed_scope="DETERMINISTIC"; seed=group[0]["seed"]
    def sm(field): return sum(float(x[field]) for x in group)
    stake=sm("stake_yuan"); gross=sm("gross_pre_tax_yuan"); tax=sm("tax_yuan"); net=gross-stake; tnet=gross-tax-stake
    fullroi=group[0]["matched_full_no_tax_roi"]
    roi=net/stake if stake else None
    hhi=sum(float(x["gross_issue_hhi"])*float(x["gross_pre_tax_yuan"]) for x in group)/gross if gross else 0.0
    top=sum(float(x["gross_top_issue_share"])*float(x["gross_pre_tax_yuan"]) for x in group)/gross if gross else 0.0
    mean_dd=sum(float(x["drawdown_no_tax_yuan"]) for x in group)/len(group)
    max_dd=max(float(x["drawdown_no_tax_yuan"]) for x in group)
    comparable = comparable_incumbent_roi if comparable_incumbent_roi is not None else ""
    comparable_manifest = comparable_incumbent_manifest or ""
    delta = roi-float(comparable) if roi is not None and comparable != "" else None
    disposition = "COMPARABLE_COMMON_SUPPORT_INCUMBENT" if comparable != "" else "INAPPLICABLE_NO_COMMON_SUPPORT_INCUMBENT"
    reason = "accepted #167-v2r3 common-support incumbent; matched FULL/lift retained separately" if comparable != "" else "no accepted common-support incumbent for this selector; matched FULL/lift retained as selector-local control"
    return {"selector_id":group[0]["selector_id"],"weight_source":group[0]["weight_source"],"mechanism":me,"cap":group[0]["cap"],"M":group[0]["M"],"seed":seed,"seed_count":seed_count,"seed_scope":seed_scope,"stake_yuan":money(stake),"gross_pre_tax_yuan":money(gross),"tax_yuan":money(tax),"pre_tax_net_yuan":money(net),"tax_adjusted_net_yuan":money(tnet),"no_tax_roi":f"{roi:.12f}" if roi is not None else "","tax_adjusted_roi":ratio(tnet,stake),"matched_full_no_tax_roi":fullroi,"matched_full_lift":f"{roi-float(fullroi):.12f}" if roi is not None and fullroi else "","capital_utilization_vs_full":f"{stake/(matched_full_stake*seed_count):.12f}" if matched_full_stake else "","coverage_hit_rate":f"{sm('coverage_hits')/sm('identity_count'):.12f}" if sm('identity_count') else "","ticket_hit_rate":f"{sm('hit_ticket_count')/(stake/2):.12f}" if stake else "","unique_ticket_coverage":f"{sm('unique_ticket_count')/(stake/2):.12f}" if stake else "","duplicate_ticket_ratio":f"{sm('duplicate_ticket_count')/(stake/2):.12f}" if stake else "","seed_gross_weighted_mean_issue_hhi":f"{hhi:.12f}","seed_gross_weighted_mean_top_issue_share":f"{top:.12f}","seed_mean_drawdown_no_tax_yuan":money(mean_dd),"seed_max_drawdown_no_tax_yuan":money(max_dd),"longest_miss_streak":max(int(x["longest_miss_streak"]) for x in group),"largest_signed_issue_no_tax_yuan":"","largest_signed_issue_index":"","global_cell":group[0]["global_cell"] if not stochastic else "","aggregation_definition":"pooled ticket-level monetary totals; concentration is seed gross-weighted mean and drawdown is seed mean (not pooled issue contributions)" if stochastic else "single deterministic arm","comparable_incumbent_roi":f"{float(comparable):.12f}" if comparable != "" else "","comparable_incumbent_manifest":comparable_manifest,"challenger_minus_comparable_incumbent":f"{delta:.12f}" if delta is not None else "","champion_common_support_disposition":disposition,"comparison_inapplicability_reason":reason}

def robust_dominates(a,b):
    ge=a[0]>=b[0] and a[1]>=b[1] and a[2]>=b[2] and a[3]<=b[3] and a[4]<=b[4]
    strict=a[0]>b[0] or a[1]>b[1] or a[2]>b[2] or a[3]<b[3] or a[4]<b[4]
    return ge and strict

def build_common_draw_matrix(issue_count: int, replicate_count: int, seed: int = 167137):
    """Build the one deterministic issue-resample matrix shared by all targets."""
    if issue_count <= 0 or replicate_count <= 0:
        raise ValueError("draw matrix dimensions must be positive")
    import random
    rng = random.Random(seed)
    draws = array.array("I", (rng.randrange(issue_count) for _ in range(replicate_count * issue_count)))
    return draws, hashlib.sha256(draws.tobytes()).hexdigest()

def write_common_draw_matrix(path: Path, issue_count: int, replicate_count: int, seed: int = 167137):
    draws, digest = build_common_draw_matrix(issue_count, replicate_count, seed)
    path.write_text(json.dumps({"seed": seed, "unit": "issue_instance", "issue_count": issue_count,
                                "replicate_count": replicate_count, "sha256": digest}, sort_keys=True, indent=2) + "\n")
    return draws, digest

def write_chart_source_pareto(path: Path, raw_path: Path, robust_path: Path):
    """Materialize the exact raw/robust chart source from production fronts."""
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["front_type", "selector_id", "weight_source", "mechanism", "cap", "M", "seed", "seed_scope", "metric_1", "metric_2", "metric_3", "metric_4", "global_cell"])
        with raw_path.open(newline="") as raw:
            for r in csv.DictReader(raw):
                w.writerow(["raw", r["selector_id"], r["weight_source"], r["mechanism"], r["cap"], r["M"], r["seed"], r["seed_scope"], r["no_tax_roi"], r["matched_full_lift"], r["seed_mean_drawdown_no_tax_yuan"], r["seed_gross_weighted_mean_issue_hhi"], r["global_cell"]])
        with robust_path.open(newline="") as robust_file:
            for r in csv.DictReader(robust_file):
                w.writerow(["robust", r["selector_id"], r["weight_source"], r["mechanism"], r["cap"], r["M"], r["seed"], "ENSEMBLE_100" if r["seed"] == "ENSEMBLE_100" else "DETERMINISTIC", r["bootstrap_ci95_low"], r["ex_largest_issue_no_tax_roi"], r["drawdown_no_tax_yuan"], r["gross_issue_hhi"], r["global_cell"]])

def finalize_package_identity(out: Path, contract_version: str, controls: dict):
    """Hash all staged payloads and write the final identity/manifest pair."""
    payload_hashes = {}
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name not in {"SHA256SUMS.json", "CONTENT_IDENTITY.json"}:
            payload_hashes[str(p.relative_to(out))] = sha(p)
    content_identity = {"contract_version": contract_version, "controls": controls, "payload_sha256": payload_hashes}
    (out / "CONTENT_IDENTITY.json").write_text(json.dumps(content_identity, sort_keys=True, indent=2) + "\n")
    sums = dict(payload_hashes); sums["CONTENT_IDENTITY.json"] = sha(out / "CONTENT_IDENTITY.json")
    (out / "SHA256SUMS.json").write_text(json.dumps(dict(sorted(sums.items())), sort_keys=True, indent=2) + "\n")
    return content_identity, sums

def atomic_publish(stage_out: Path, final_out: Path) -> None:
    """Expose a completed immutable package with one rename only."""
    if final_out.exists(): raise RuntimeError(f"refusing to replace final output: {final_out}")
    os.replace(stage_out, final_out)

def load_surface():
    with (GA / "selector_grid.csv").open(newline="") as f: selectors = list(csv.DictReader(f))
    if len(selectors) != NSEL: raise RuntimeError(f"selector count {len(selectors)} != {NSEL}")
    selector_idx = {r["selector_id"]: i for i,r in enumerate(selectors)}
    with (GA / "allocation_grid.csv").open(newline="") as f: alloc = list(csv.DictReader(f))
    if len(alloc) != NCELL: raise RuntimeError(f"allocation count {len(alloc)} != {NCELL}")
    cell_meta = []
    def empty(): return {"wr": [-1]*(100*20), "wor": [-1]*(100*20), "residual": [-1]*20, "top": [-1]*20, "capped": [-1]*(4*20)}
    # Stochastic/deterministic allocation cells are source-specific.  Keeping
    # one map here would overwrite the six vectors into the final (Q) source.
    maps = {src: empty() for src in SOURCES}; maps["struct"] = {"full": -1, "p": -1, "q": -1}
    for i,r in enumerate(alloc):
        ws,me,cap,m,seed = parse_key(r); cell_meta.append(r)
        if me == "WR_DUPLICATE_STAKE": maps[ws]["wr"][(int(seed)-137001)*20 + M_GRID.index(m)] = i
        elif me == "WOR_DISTINCT": maps[ws]["wor"][(int(seed)-137001)*20 + M_GRID.index(m)] = i
        elif me == "RESIDUAL_SYSTEMATIC": maps[ws]["residual"][M_GRID.index(m)] = i
        elif me == "DETERMINISTIC_TOP_MASS": maps[ws]["top"][M_GRID.index(m)] = i
        elif me == "CAPPED_REPEAT": maps[ws]["capped"][(CAPS.index(int(cap)))*20 + M_GRID.index(m)] = i
        elif me == "FULL_ENUMERATED": maps["struct"]["full"] = i
        elif me == "P_MIN_GLOBAL_DELETE": maps["struct"]["p"] = i
        elif me == "Q_MIN_GLOBAL_DELETE": maps["struct"]["q"] = i
    for k,v in maps.items():
        for name, vals in v.items():
            if any(x < 0 for x in vals) if isinstance(vals,list) else vals < 0: raise RuntimeError(f"incomplete allocation map {k}/{name}")
    return selectors, selector_idx, alloc, cell_meta, maps

def role_values(r):
    return {"match_id": r["match_id"], "match_idx": r.get("match_idx", ""), "kickoff_ts": r.get("kickoff_ts", ""), "p_min": float(r["p_min"]),
            "p_model": tuple(float(r[x]) for x in SOURCE_COLUMNS["MODEL_P_CAL"]),
            # The Q-delete structural arm ranks the exact frozen Q vector.
            # Retain it explicitly as well as in `source`, because its
            # delete rule is independent of the allocation replay loop.
            "q_weight": tuple(float(r[x]) for x in SOURCE_COLUMNS["Q_WEIGHT"]),
            "source": {s: tuple(float(r[x]) for x in cols) for s,cols in SOURCE_COLUMNS.items()}}

def build_supports(outcomes, selector_idx):
    idr = GzipRows(sorted(GA.glob("selector_identities-*.csv.gz")))
    rvr = GzipRows(sorted(GA.glob("selector_role_vectors-*.csv.gz")))
    supports = {}; issue_order = []; issue_seen = set(); identity_count = role_count = 0
    row = idr.next()
    while row:
        key = (row["issue_instance"], row["selected_match_ids"])
        roles = []
        for _ in range(7):
            rr = rvr.next()
            if rr is None or (rr["selector_id"],rr["issue_instance"],rr["portfolio_id"]) != (row["selector_id"],row["issue_instance"],row["portfolio_id"]):
                raise RuntimeError("identity/role row key mismatch")
            roles.append(role_values(rr)); role_count += 1
        identity_count += 1
        if row["issue_instance"] not in issue_seen: issue_seen.add(row["issue_instance"]); issue_order.append(row["issue_instance"])
        s = supports.get(key)
        if s is None:
            mids = row["selected_match_ids"].split("|")
            if len(mids) != 7 or [x["match_id"] for x in roles] != mids: raise RuntimeError("support role/match mismatch")
            missing = tuple(x for x in mids if x not in outcomes)
            if missing:
                # PI's frozen outcome-boundary ruling is fail-closed at the
                # support level: retain the support and every selector
                # membership, but do not invent a result/SP or settle it.
                truths = tuple(-1 for _ in mids); prod = 0.0
            else:
                truths = tuple(outcomes[x][0] for x in mids); prod = math.prod(outcomes[x][1] for x in mids)
            s = supports[key] = {"issue_instance": row["issue_instance"], "mids": mids, "roles": roles,
                "truth": sum(max(t,0)*(3**(6-i)) for i,t in enumerate(truths)), "truth_codes": truths,
                "payout": 2.0*0.65*prod, "selectors": [], "portfolio_ids_by_selector": defaultdict(list), "available": not missing, "missing_match_ids": missing}
        elif tuple(x["match_id"] for x in roles) != tuple(x["match_id"] for x in s["roles"]):
            raise RuntimeError("canonical support role mismatch")
        si = selector_idx[row["selector_id"]]
        if si not in s["selectors"]: s["selectors"].append(si)
        if row["portfolio_id"] not in s["portfolio_ids_by_selector"][si]: s["portfolio_ids_by_selector"][si].append(row["portfolio_id"])
        row = idr.next()
    if role_count != identity_count*7 or identity_count != 1306139 or len(supports) != NSUPPORT:
        raise RuntimeError(f"ledger census mismatch ids={identity_count} roles={role_count} supports={len(supports)}")
    by_issue = defaultdict(list)
    for s in supports.values(): by_issue[s["issue_instance"]].append(s)
    return supports, by_issue, issue_order, identity_count

def build_policy_status(census_rows, supports, selector_idx):
    """Return complete-issue selector policy status and eligible occurrences.

    A missing outcome anywhere in a selected identity closes the whole
    selector×issue policy.  This is intentionally stricter than support-level
    filtering and is the accepted #137 denominator rule.
    """
    status = {}; selected = {}
    for r in census_rows:
        key = (selector_idx[r["selector_id"]], r["issue_instance"])
        n = int(r["selected_identity_count"]); selected[key] = selected.get(key, 0) + n
        status[key] = "NO_BET_FROZEN" if n == 0 or r.get("selection_status") not in ("AVAILABLE", "") else "SETTLED"
    for s in supports.values():
        if not s["available"]:
            for si in s["selectors"]:
                key = (si, s["issue_instance"])
                if status.get(key) != "NO_BET_FROZEN": status[key] = "UNAVAILABLE_CANONICAL_OUTCOME"
    for s in supports.values():
        s["eligible_selectors"] = [si for si in s["selectors"] if status.get((si, s["issue_instance"])) == "SETTLED"]
    return status, selected

def common_support_identity_tokens(supports, selector_index):
    """Return canonical issue/identity tokens for one selector only."""
    return sorted(
        f"{s['issue_instance']}|{portfolio_id}"
        for s in supports.values()
        if selector_index in s.get("eligible_selectors", [])
        for portfolio_id in s.get("portfolio_ids_by_selector", {}).get(selector_index, [])
    )

def matched_full_denominator_metadata(supports, selector_index, selector_issue_total,
                                      selector_available_issues, selector_unavailable_issues,
                                      selector_no_bet_issues, selector_identity_total,
                                      selector_available_identity, selector_unavailable_identity,
                                      selector_no_bet_identity):
    """Return selector-local policy denominators and the settled support hash."""
    settled_issues = len(selector_available_issues[selector_index])
    unavailable_issues = len(selector_unavailable_issues[selector_index])
    no_bet_issues = len(selector_no_bet_issues[selector_index])
    if settled_issues + unavailable_issues + no_bet_issues != selector_issue_total[selector_index]:
        raise RuntimeError(f"selector issue-policy denominator drift for {selector_index}")
    settled_identities = selector_available_identity[selector_index]
    unavailable_identities = selector_unavailable_identity[selector_index]
    no_bet_identities = selector_no_bet_identity[selector_index]
    if settled_identities + unavailable_identities + no_bet_identities != selector_identity_total[selector_index]:
        raise RuntimeError(f"selector identity denominator drift for {selector_index}")
    tokens = common_support_identity_tokens(supports, selector_index)
    if len(tokens) != settled_identities:
        raise RuntimeError(f"selector settled support hash denominator drift for {selector_index}")
    support_hash = hashlib.sha256("\n".join(tokens).encode()).hexdigest()
    denominator = (
        f"issue policies: SETTLED={settled_issues}; UNAVAILABLE_CANONICAL_OUTCOME={unavailable_issues}; "
        f"NO_BET_FROZEN={no_bet_issues}; identities: SETTLED={settled_identities}; "
        f"UNAVAILABLE_CANONICAL_OUTCOME={unavailable_identities}; NO_BET_FROZEN={no_bet_identities}"
    )
    return denominator, support_hash

def assert_s1_incumbent_anchors(incumbent):
    """Protect the accepted #167-v2r3 absolute, FULL, and lift bridge."""
    anchors = (
        ("candidate ROI", incumbent["no_tax_roi"], COMMON_SUPPORT_INCUMBENT_ROI),
        ("matched FULL ROI", incumbent["matched_full_no_tax_roi"], "-0.157696718701"),
        ("matched FULL lift", incumbent["matched_full_lift"], COMMON_SUPPORT_INCUMBENT_LIFT),
    )
    for name, actual, expected in anchors:
        if abs(float(actual) - float(expected)) > 1e-12:
            raise RuntimeError(f"current v3r1 S1 common-support {name} does not match accepted v2r3 bridge")

def write_file_census(out: Path):
    """Census completed payloads only; never include a stale self-size row."""
    census_path = out / "file_census.csv"
    with census_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["relative_path", "bytes", "sha256"])
        for p in sorted(out.rglob("*")):
            if p.is_file() and p.name not in {"SHA256SUMS.json", "CONTENT_IDENTITY.json", "file_census.csv"}:
                w.writerow([str(p.relative_to(out)), p.stat().st_size, sha(p)])
    return census_path

def ptr(a, ctype): return ctypes.cast((ctype * len(a)).from_buffer(a), ctypes.POINTER(ctype))

def compile_engine(root: Path, so_name: str = "bj167_exact_atlas.so"):
    cpp = root / "scripts" / "bj167_exact_atlas.cpp"; so = root / ".scratch" / so_name
    # Keep compiler intermediates in the worktree scratch area.  The full
    # replay already keeps sort/staging there; this avoids a hidden /tmp
    # dependency on hosts where that filesystem is small.
    compile_tmp = root / ".scratch" / "bj167_compile_tmp"
    compile_tmp.mkdir(parents=True, exist_ok=True)
    compile_env = dict(os.environ, TMPDIR=str(compile_tmp), TEMP=str(compile_tmp), TMP=str(compile_tmp))
    subprocess.run(["g++","-O3","-std=c++17","-fopenmp","-shared","-fPIC",str(cpp),"-o",str(so)], check=True, env=compile_env)
    return ctypes.CDLL(str(so))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--output", default="results/bj167_gate_b_strategy_atlas_v3r1_exact"); ap.add_argument("--golden-only", action="store_true"); args = ap.parse_args()
    verify_ga(); outcomes = load_outcomes(); selectors, selector_idx, alloc, cell_meta, maps = load_surface()
    print(f"verified Gate-A; surface selectors={len(selectors)} cells={len(alloc)} outcomes={len(outcomes)}", flush=True)
    if args.golden_only:
        test = ROOT / "tests" / "scripts" / "test_bj167_exact_engine.py"
        subprocess.run(["pytest", "-q", str(test)], cwd=ROOT, check=True)
        print("GOLDEN_ONLY numeric engine/map/delete/backing-buffer assertions PASS", flush=True); return
    supports, by_issue, issue_order, identity_count = build_supports(outcomes, selector_idx)
    print(f"canonical support cache={len(supports)} identities={identity_count} issues={len(issue_order)}", flush=True)
    with (GA / "selector_census.csv").open(newline="") as f: census_rows = list(csv.DictReader(f))
    census_meta = {}
    for cr in census_rows:
        census_meta.setdefault(cr["issue_instance"], {"year": cr.get("year", ""), "fold": cr.get("fold", ""), "loyo": f"LOYO_{cr.get('year','')}"})
    # Native issue accumulation is chronological, never shard encounter
    # order.  Gate-A role rows carry the first-match kickoff timestamp; use
    # the earliest selected leg as the issue key and issue_instance as the
    # deterministic tie break for equal/missing timestamps.
    issue_meta = {}
    for issue, issue_supports in by_issue.items():
        timestamps = [str(role.get("kickoff_ts", "")) for s in issue_supports for role in s["roles"] if str(role.get("kickoff_ts", ""))]
        first_kickoff_ts = min(timestamps) if timestamps else ""
        cm = census_meta.get(issue, {})
        issue_meta[issue] = {"year": cm.get("year", ""), "fold": cm.get("fold", ""), "loyo": cm.get("loyo", ""), "first_kickoff_ts": first_kickoff_ts}
    issue_order = sorted(issue_meta, key=lambda issue: (issue_meta[issue]["first_kickoff_ts"] == "", issue_meta[issue]["first_kickoff_ts"], issue))
    policy_status, policy_identity_by_issue = build_policy_status(census_rows, supports, selector_idx)
    selector_issue_total = defaultdict(int); policy_identity_count = defaultdict(int); selector_identity_total = defaultdict(int)
    for r in census_rows:
        key=(selector_idx[r["selector_id"]],r["issue_instance"]); count=int(r["selected_identity_count"]); selector_issue_total[key[0]] += 1; policy_identity_count[key] += count; selector_identity_total[key[0]] += count
    if sum(selector_identity_total.values()) != identity_count:
        raise RuntimeError(f"selector identity total mismatch census={sum(selector_identity_total.values())} identities={identity_count}")
    selector_available_issues = defaultdict(set); selector_unavailable_issues = defaultdict(set); selector_no_bet_issues = defaultdict(set)
    for (si, issue), st in policy_status.items():
        (selector_available_issues if st == "SETTLED" else selector_unavailable_issues if st.startswith("UNAVAILABLE") else selector_no_bet_issues)[si].add(issue)
    selector_available_identity = defaultdict(int); selector_unavailable_identity = defaultdict(int); selector_no_bet_identity = defaultdict(int)
    for (si, issue), st in policy_status.items():
        count = policy_identity_count[(si, issue)]
        (selector_available_identity if st == "SETTLED" else selector_unavailable_identity if st.startswith("UNAVAILABLE") else selector_no_bet_identity)[si] += count
    n = NSEL*NCELL
    final_out=ROOT/args.output
    stage_out=Path(str(final_out)+".stage")
    if final_out.exists() and any(final_out.iterdir()):
        raise RuntimeError(f"refusing to overwrite non-empty output package: {final_out}")
    if stage_out.exists() and any(stage_out.iterdir()):
        raise RuntimeError(f"refusing to reuse non-empty staging package: {stage_out}")
    if stage_out.exists(): shutil.rmtree(stage_out)
    out=stage_out
    out.mkdir(parents=True,exist_ok=True)
    with (out/"issue_order.csv").open("w",newline="") as iof:
        iw=csv.writer(iof); iw.writerow(["issue_index","issue_instance","first_kickoff_ts","year","fold","loyo","ordering_rule"])
        for issue_index, issue in enumerate(issue_order):
            meta=issue_meta[issue]
            iw.writerow([issue_index,issue,meta["first_kickoff_ts"],meta["year"],meta["fold"],meta["loyo"],"first_kickoff_ts ASC; issue_instance ASC tie-break"])
    # Flat native double arrays retain exact six-decimal money and support
    # full-cell reconciliation without a Cartesian ledger.
    metrics = [array.array("d", [0.0])*n for _ in range(8)] # identity,stake,gross,tax,unique,dup,hit,coverage
    tmp = [array.array("d", [0.0])*n for _ in range(3)]
    mark = array.array("B", [0])*n; touched = array.array("i", [0])*n
    # ISSUE_TOP_NET is a signed maximum and must start at -inf; zero would
    # silently erase every all-negative issue.  Keep the issue index beside
    # the value so YEAR/FOLD/LOYO summaries can identify the same event.
    diag = [array.array("d", [0.0])*n for _ in range(5)]
    diag.append(array.array("d", [-math.inf])*n) # signed largest issue net
    diag.append(array.array("d", [0.0])*n)       # stake at largest issue
    largest_issue_index = array.array("i", [-1])*n
    miss = [array.array("i", [0])*n for _ in range(2)]
    # The issue-level bootstrap is a second-pass companion to the exact
    # surface replay.  Its targets are declared before replay (so no outcome
    # can choose a winner) and cover the complete Q/WOR seed panel at the two
    # observed M values, plus the incumbent/control/delete/top family.  The
    # first Q/WOR M64 anchor is the confirmatory incumbent (20,000 paired
    # issue resamples); the broad screening targets remain descriptive (2,000).
    primary_si = selector_idx.get("S1_NO_GATE_K4", 0)
    cell_by_key = {}
    for j, r in enumerate(cell_meta):
        cell_by_key[(r["weight_source"],r["mechanism"],r["cap"],r["M"],r["seed"])] = j
    direct_target_specs = []
    def add_target(label, global_cell, replicates, role, selector_index=primary_si):
        direct_target_specs.append({"label": label, "global_cell": global_cell, "replicates": replicates, "role": role, "selector_index": selector_index})
    for m in (64, 128):
        for seed in SEEDS:
            j = cell_by_key[("Q_WEIGHT", "WOR_DISTINCT", "NA", str(m), seed)]
            role = "SEED_PANEL_SCREEN"
            add_target(f"S1_NO_GATE_K4/Q_WEIGHT/WOR_DISTINCT/M{m}/{seed}", primary_si*NCELL+j, 20000 if role.startswith("CONFIRMATORY") else 2000, role)
    for ws, me, cap, m, label in (
        ("Q_WEIGHT", "RESIDUAL_SYSTEMATIC", "NA", 64, "Q_WEIGHT/RESIDUAL_SYSTEMATIC/M64"),
        ("Q_WEIGHT", "CAPPED_REPEAT", "1", 64, "Q_WEIGHT/CAPPED_REPEAT/cap1/M64"),
        ("Q_WEIGHT", "CAPPED_REPEAT", "2", 64, "Q_WEIGHT/CAPPED_REPEAT/cap2/M64"),
        ("Q_WEIGHT", "CAPPED_REPEAT", "4", 64, "Q_WEIGHT/CAPPED_REPEAT/cap4/M64"),
        ("Q_WEIGHT", "CAPPED_REPEAT", "8", 64, "Q_WEIGHT/CAPPED_REPEAT/cap8/M64"),
        ("Q_WEIGHT", "DETERMINISTIC_TOP_MASS", "NA", 64, "Q_WEIGHT/DETERMINISTIC_TOP_MASS/M64"),
    ):
        add_target(f"S1_NO_GATE_K4/{label}", primary_si*NCELL+cell_by_key[(ws,me,cap,str(m),"NA")], 2000, "ALLOCATION_FAMILY_SCREEN")
    add_target("S1_NO_GATE_K4/FULL_ENUMERATED", primary_si*NCELL+maps["struct"]["full"], 20000, "MATCHED_FULL_CONFIRMATORY")
    add_target("S1_NO_GATE_K4/P_MIN_GLOBAL_DELETE", primary_si*NCELL+maps["struct"]["p"], 2000, "DELETE_CONTROL_SCREEN")
    add_target("S1_NO_GATE_K4/Q_MIN_GLOBAL_DELETE", primary_si*NCELL+maps["struct"]["q"], 2000, "DELETE_CONTROL_SCREEN")
    # The 100-seed aggregate is a declared incumbent in its own right.  It is
    # not another fake cell: it is formed from the same per-issue realized
    # seed rows after replay, so candidate and matched FULL retain identical
    # issue-block bootstrap draws.
    for i, x in enumerate(direct_target_specs): x["direct_index"] = i
    wor_m64_direct = [i for i,x in enumerate(direct_target_specs) if "/WOR_DISTINCT/M64/" in x["label"]]
    direct_target_specs.append({"label":"S1_NO_GATE_K4/Q_WEIGHT/WOR_DISTINCT/M64/ENSEMBLE_100","global_cell":-1,"replicates":20000,"role":"CONFIRMATORY_INCUMBENT_100_SEED","aggregate_direct_indices":wor_m64_direct,"selector_index":primary_si})
    direct_target_specs[wor_m64_direct[0]]["replicates"] = 2000
    target_specs = direct_target_specs
    direct_boot_specs = [x for x in target_specs if x["global_cell"] >= 0]
    boot_targets = [x["global_cell"] for x in direct_boot_specs]
    target_map = array.array("i", [-1])*n
    for i, c in enumerate(boot_targets): target_map[c] = i
    nissue = len(issue_order); boot_net=array.array("d",[0.0])*(nissue*len(boot_targets)); boot_stake=array.array("d",[0.0])*(nissue*len(boot_targets)); boot_hit=array.array("d",[0.0])*(nissue*len(boot_targets)); boot_tmp=[array.array("d",[0.0])*len(boot_targets) for _ in range(3)]
    lib = compile_engine(ROOT)
    dptr=[ptr(x,ctypes.c_double) for x in metrics]; tptr=[ptr(x,ctypes.c_double) for x in tmp]; diagptr=[ptr(x,ctypes.c_double) for x in diag]; mptr=[ptr(x,ctypes.c_int) for x in miss]
    lib.bj167_process_source.argtypes=[ctypes.POINTER(ctypes.c_double),ctypes.c_int,ctypes.c_char_p,ctypes.c_double,ctypes.POINTER(ctypes.c_int),ctypes.c_int]+[ctypes.POINTER(ctypes.c_int)]*5+[ctypes.c_int]+[ctypes.POINTER(ctypes.c_double)]*8
    lib.bj167_add_delete.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_double]+[ctypes.POINTER(ctypes.c_double)]*8
    lib.bj167_set_issue_buffers.argtypes=[ctypes.POINTER(ctypes.c_double)]*3+[ctypes.POINTER(ctypes.c_ubyte),ctypes.POINTER(ctypes.c_int)]+[ctypes.POINTER(ctypes.c_double)]*5+[ctypes.POINTER(ctypes.c_int)]*2+[ctypes.POINTER(ctypes.c_double)]*2+[ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int),ctypes.c_int]+[ctypes.POINTER(ctypes.c_double)]*6
    lib.bj167_begin_issue.argtypes=[ctypes.c_int]
    lib.bj167_set_issue_buffers(tptr[0],tptr[1],tptr[2],ptr(mark,ctypes.c_ubyte),ptr(touched,ctypes.c_int),diagptr[0],diagptr[1],diagptr[2],diagptr[3],diagptr[4],mptr[0],mptr[1],diagptr[5],diagptr[6],ptr(largest_issue_index,ctypes.c_int),ptr(target_map,ctypes.c_int),len(boot_targets),ptr(boot_tmp[0],ctypes.c_double),ptr(boot_tmp[1],ctypes.c_double),ptr(boot_tmp[2],ctypes.c_double),ptr(boot_net,ctypes.c_double),ptr(boot_stake,ctypes.c_double),ptr(boot_hit,ctypes.c_double))
    selectors_ids = {s["issue_instance"]: s for s in []}
    source_ptrs = {s: ctypes.POINTER(ctypes.c_double) for s in SOURCES}
    # Keep the ctypes backing arrays alive for the complete native replay.
    # Pointers alone are unsafe: the former comprehension created temporary
    # arrays that could be collected while C++ still held their addresses.
    map_arrays = {src: {k: array.array("i", v) for k,v in maps[src].items()} for src in SOURCES}
    map_ptrs = {src: {k: ptr(map_arrays[src][k],ctypes.c_int) for k in map_arrays[src]} for src in SOURCES}
    for ii,issue in enumerate(issue_order):
        lib.bj167_begin_issue(ii)
        for s in by_issue[issue]:
            occ=array.array("i",s["eligible_selectors"]);
            if not occ: continue
            occp=ptr(occ,ctypes.c_int); role_by_source={src: array.array("d",[v for role in s["roles"] for v in role["source"][src]]) for src in SOURCES}
            for src_i,src in enumerate(SOURCES):
                rp=ptr(role_by_source[src],ctypes.c_double)
                sm=map_ptrs[src]
                lib.bj167_process_source(rp, s["truth"], "|".join(s["mids"]).encode(), s["payout"], occp,len(occ),sm["wr"],sm["wor"],sm["residual"],sm["capped"],sm["top"],maps["struct"]["full"] if src_i==0 else -1,*dptr)
            pleg,pcode,qleg,qcode=derive_delete(s["roles"])
            for si in s["eligible_selectors"]:
                lib.bj167_add_delete(si,maps["struct"]["p"],s["truth"],pleg,pcode,s["payout"],*dptr)
                lib.bj167_add_delete(si,maps["struct"]["q"],s["truth"],qleg,qcode,s["payout"],*dptr)
        lib.bj167_end_issue()
        if (ii+1)%10==0: print(f"settled issues {ii+1}/{len(issue_order)}",flush=True)
    # Canonical support cache is an auditable factorization map, not a filter.
    with gzip.GzipFile(filename=str(out/"canonical_support_cache.csv.gz"), mode="wb", mtime=0) as gf, __import__("io").TextIOWrapper(gf, newline="") as f:
        w=csv.writer(f); w.writerow(["support_key","issue_instance","selected_match_ids","truth_sequence","payout_yuan","selector_count","selector_ids","eligible_selector_ids","p_deleted_leg","p_deleted_code","q_deleted_leg","q_deleted_code","settlement_status","missing_match_ids"])
        for key,s in sorted(supports.items()):
            pl,pc,ql,qc=derive_delete(s["roles"]); w.writerow(["|".join(key),s["issue_instance"],"|".join(s["mids"]),"".join(str(x) for x in s["truth_codes"]),money(s["payout"]),len(s["selectors"]),";".join(selectors[x]["selector_id"] for x in s["selectors"]),";".join(selectors[x]["selector_id"] for x in s["eligible_selectors"]),pl,pc,ql,qc,"SETTLED" if s["available"] else "OUTCOME_UNAVAILABLE",";".join(s["missing_match_ids"])])
    for si,sel in enumerate(selectors):
        p=out/f"cell_metrics-{si:03d}.csv.gz"
        with gzip.GzipFile(filename=str(p),mode="wb",mtime=0) as gf, __import__("io").TextIOWrapper(gf,newline="") as f:
            fields=["selector_id","family","gate_id","top_k","lowp_source","lowp_threshold","ranker","issue_count","available_issue_count","unavailable_issue_count","no_bet_issue_count","identity_count","available_identity_count","unavailable_identity_count","no_bet_identity_count","weight_source","mechanism","cap","M","seed","seed_role","executed_ticket_count","stake_yuan","unique_ticket_count","duplicate_ticket_count","hit_ticket_count","coverage_hits","gross_pre_tax_yuan","tax_yuan","pre_tax_net_yuan","tax_adjusted_net_yuan","no_tax_roi","tax_adjusted_roi","matched_full_no_tax_roi","matched_full_lift","capital_utilization_vs_full","coverage_hit_rate","ticket_hit_rate","unique_ticket_coverage","duplicate_ticket_ratio","gross_issue_hhi","gross_top_issue_share","drawdown_no_tax_yuan","longest_miss_streak","largest_signed_issue_no_tax_yuan","largest_signed_issue_index","largest_signed_issue_year","largest_signed_issue_fold","largest_signed_issue_loyo","global_cell","bootstrap_target_index","computation_mode"]
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader(); full_at=si*NCELL+maps["struct"]["full"];
            fs=metrics[1][full_at]; fg=metrics[2][full_at]
            for ci,r in enumerate(cell_meta):
                at=si*NCELL+ci; stake=metrics[1][at]; gross=metrics[2][at]; tax=metrics[3][at]; net=gross-stake; tnet=gross-tax-stake; fullroi=(fg-fs)/fs if fs else None; roi=net/stake if stake else None
                hhi=diag[0][at]/(gross*gross) if gross else 0; top=diag[1][at]/gross if gross else 0; full_lift=roi-fullroi if roi is not None and fullroi is not None else None
                li=int(largest_issue_index[at]); lm=issue_meta.get(issue_order[li], {}) if li >= 0 and li < len(issue_order) else {}
                w.writerow({"selector_id":sel["selector_id"],"family":sel["family"],"gate_id":sel["gate_id"],"top_k":sel["top_k"],"lowp_source":sel["lowp_source"],"lowp_threshold":sel["lowp_threshold"],"ranker":sel["ranker"],"issue_count":selector_issue_total[si],"available_issue_count":len(selector_available_issues[si]),"unavailable_issue_count":len(selector_unavailable_issues[si]),"no_bet_issue_count":len(selector_no_bet_issues[si]),"identity_count":f"{selector_identity_total[si]:.0f}","available_identity_count":selector_available_identity[si],"unavailable_identity_count":selector_unavailable_identity[si],"no_bet_identity_count":selector_no_bet_identity[si],"weight_source":r["weight_source"],"mechanism":r["mechanism"],"cap":r["cap"],"M":r["M"],"seed":r["seed"],"seed_role":r["seed_role"],"executed_ticket_count":f"{stake/2:.0f}","stake_yuan":money(stake),"unique_ticket_count":f"{metrics[4][at]:.0f}","duplicate_ticket_count":f"{metrics[5][at]:.0f}","hit_ticket_count":f"{metrics[6][at]:.0f}","coverage_hits":f"{metrics[7][at]:.0f}","gross_pre_tax_yuan":money(gross),"tax_yuan":money(tax),"pre_tax_net_yuan":money(net),"tax_adjusted_net_yuan":money(tnet),"no_tax_roi":f"{roi:.12f}" if roi is not None else "","tax_adjusted_roi":ratio(tnet,stake),"matched_full_no_tax_roi":f"{fullroi:.12f}" if fullroi is not None else "","matched_full_lift":f"{full_lift:.12f}" if full_lift is not None else "","capital_utilization_vs_full":f"{stake/fs:.12f}" if fs else "","coverage_hit_rate":f"{metrics[7][at]/metrics[0][at]:.12f}" if metrics[0][at] else "","ticket_hit_rate":f"{metrics[6][at]/(stake/2):.12f}" if stake else "","unique_ticket_coverage":f"{metrics[4][at]/(stake/2):.12f}" if stake else "","duplicate_ticket_ratio":f"{metrics[5][at]/(stake/2):.12f}" if stake else "","gross_issue_hhi":f"{hhi:.12f}","gross_top_issue_share":f"{top:.12f}","drawdown_no_tax_yuan":money(diag[4][at]),"longest_miss_streak":miss[1][at],"largest_signed_issue_no_tax_yuan":money(diag[5][at]) if li >= 0 else "","largest_signed_issue_index":li if li >= 0 else "","largest_signed_issue_year":lm.get("year", ""),"largest_signed_issue_fold":lm.get("fold", ""),"largest_signed_issue_loyo":lm.get("loyo", ""),"global_cell":at,"bootstrap_target_index":target_map[at],"computation_mode":"EXACT_TICKET_REPLAY_SHARED_MAX_M_PREFIX"})
    # Real issue-cluster bootstrap for the declared targets.  Every
    # confirmatory replicate draws one issue-index vector and applies it to
    # candidate *and* matched FULL together; this is a paired lift bootstrap,
    # not two independent confidence intervals.  The 100-seed incumbent is
    # aggregated from the same per-issue seed rows before resampling.
    direct_count=len(boot_targets)
    def issue_arrays(spec):
        if spec.get("aggregate_direct_indices") is not None:
            inds=spec["aggregate_direct_indices"]
            return ([sum(boot_net[ii*direct_count+j] for j in inds) for ii in range(nissue)],
                    [sum(boot_stake[ii*direct_count+j] for j in inds) for ii in range(nissue)])
        j=spec["direct_index"]
        return ([boot_net[ii*direct_count+j] for ii in range(nissue)], [boot_stake[ii*direct_count+j] for ii in range(nissue)])
    # One deterministic issue-resample matrix is shared by every target.  This
    # makes all candidate/FULL comparisons paired on identical issue indices;
    # advancing one RNG independently per target was a subtle but material
    # source of incomparable confidence intervals.
    full_target_by_selector = {}
    for i, spec in enumerate(target_specs):
        if spec["role"] == "MATCHED_FULL_CONFIRMATORY":
            full_target_by_selector[spec["selector_index"]] = i
    max_replicates=max(x["replicates"] for x in target_specs)
    draw_matrix, draw_matrix_sha256 = write_common_draw_matrix(out/"bootstrap_draw_matrix.json", nissue, max_replicates)
    with (out/"issue_cluster_bootstrap.csv").open("w",newline="") as f:
        w=csv.writer(f); w.writerow(["target","global_cell","role","replicates","candidate_point_roi","candidate_ci95_low","candidate_ci95_high","candidate_positive_fraction","full_point_roi","full_ci95_low","full_ci95_high","full_positive_fraction","paired_lift_point","paired_lift_ci95_low","paired_lift_ci95_high","paired_lift_positive_fraction","bootstrap_unit","paired_full_target"])
        for t, spec in enumerate(target_specs):
            nets, stakes = issue_arrays(spec); point_st=sum(stakes); point=sum(nets)/point_st if point_st else None
            R=spec["replicates"]; candidate_vals=[]; full_vals=[]; lift_vals=[]
            paired = spec["role"] != "MATCHED_FULL_CONFIRMATORY"
            full_idx=full_target_by_selector.get(spec["selector_index"])
            if paired and full_idx is None:
                raise RuntimeError(f"no selector-matched FULL target for {spec['label']}")
            matched_full_spec=target_specs[full_idx] if full_idx is not None else None
            matched_full_nets, matched_full_stakes = issue_arrays(matched_full_spec) if matched_full_spec else (None,None)
            for rep in range(R):
                start=rep*nissue; ix=draw_matrix[start:start+nissue]
                cst=sum(stakes[i] for i in ix)
                cn=sum(nets[i] for i in ix)
                candidate_vals.append(cn/cst if cst else None)
                if paired:
                    fst=sum(matched_full_stakes[i] for i in ix); fn=sum(matched_full_nets[i] for i in ix)
                    full_vals.append(fn/fst if fst else None); lift_vals.append((cn/cst - fn/fst) if cst and fst else None)
            def quant(vals, q):
                valid=sorted(v for v in vals if v is not None)
                if not valid: return ""
                return f"{valid[min(len(valid)-1,max(0,int(q*len(valid))))]:.12f}"
            def positive(vals):
                valid=[v for v in vals if v is not None]
                return f"{sum(v>0 for v in valid)/len(valid):.12f}" if valid else ""
            cp=f"{point:.12f}" if point is not None else ""
            if paired:
                full_point_stake=sum(matched_full_stakes); full_point_net=sum(matched_full_nets)
                fp=full_point_net/full_point_stake if full_point_stake else None; lp=point-fp if point is not None and fp is not None else None
                row=[spec["label"],spec["global_cell"],spec["role"],R,cp,quant(candidate_vals,.025),quant(candidate_vals,.975),positive(candidate_vals),f"{fp:.12f}" if fp is not None else "",quant(full_vals,.025),quant(full_vals,.975),positive(full_vals),f"{lp:.12f}" if lp is not None else "",quant(lift_vals,.025),quant(lift_vals,.975),positive(lift_vals),"issue_instance",matched_full_spec["label"]]
            else:
                row=[spec["label"],spec["global_cell"],spec["role"],R,cp,quant(candidate_vals,.025),quant(candidate_vals,.975),positive(candidate_vals),"","","","","","","","","issue_instance",""]
            w.writerow(row)
    with (out/"bootstrap_target_registry.csv").open("w",newline="") as f:
        w=csv.writer(f); w.writerow(["target_index","global_cell","target","role","replicates","paired_full_target"])
        for i,spec in enumerate(target_specs):
            full_idx=full_target_by_selector.get(spec["selector_index"])
            w.writerow([i,spec["global_cell"] if spec["global_cell"] >= 0 else "",spec["label"],spec["role"],spec["replicates"],target_specs[full_idx]["label"] if full_idx is not None and spec["role"] != "MATCHED_FULL_CONFIRMATORY" else ""])
    # 100-seed ensemble summaries are the scientific unit.  Allocation cells
    # are ordered by source/mechanism/M/seed in Gate A, so each stochastic
    # group is reduced online (one group of 100 rows at a time) rather than
    # retaining the 12.2M-row surface in memory.
    prefixes=(3,10,25,50,100)
    def summarize(vals):
        vals=[float(v) for v in vals if v is not None]
        if not vals: return ("",)*9
        vals.sort(); nval=len(vals); mean=sum(vals)/nval; med=statistics.median(vals)
        sd=statistics.stdev(vals) if nval>1 else 0.0
        q=lambda p: vals[min(nval-1,max(0,int(p*nval)))]
        return (f"{mean:.12f}",f"{med:.12f}",f"{q(.05):.12f}",f"{q(.25):.12f}",f"{q(.75):.12f}",f"{q(.95):.12f}",f"{sd:.12f}",f"{sd/math.sqrt(nval):.12f}",f"{sum(v>0 for v in vals)/nval:.12f}")
    prefix_fields=["selector_id","weight_source","mechanism","cap","M","seed_prefix","valid_seed_count","candidate_mean_roi","candidate_median_roi","candidate_p05_roi","candidate_p25_roi","candidate_p75_roi","candidate_p95_roi","candidate_sd_roi","candidate_mcse_roi","candidate_positive_roi_fraction","lift_mean_roi","lift_median_roi","lift_p05_roi","lift_p25_roi","lift_p75_roi","lift_p95_roi","lift_sd_roi","lift_mcse_roi","positive_lift_fraction","matched_full_no_tax_roi","summary_definition"]
    prefix_path=out/"seed_prefix_summaries.csv.gz"
    with gzip.GzipFile(filename=str(prefix_path),mode="wb",mtime=0) as gf, __import__("io").TextIOWrapper(gf,newline="") as outtxt:
        w=csv.DictWriter(outtxt,fieldnames=prefix_fields); w.writeheader()
        for fp in sorted(out.glob("cell_metrics-*.csv.gz")):
            current_key=None; group=[]
            def flush_group():
                if current_key is None: return
                if len(group) != 100: raise RuntimeError(f"seed group incomplete {current_key}: {len(group)}")
                selector,ws,me,cap,m=current_key
                for pref in prefixes:
                    rows=sorted(group,key=lambda x:x["seed"] )[:pref]
                    rois=[float(x["no_tax_roi"]) if x["no_tax_roi"] else None for x in rows]
                    lifts=[float(x["matched_full_lift"]) if x["matched_full_lift"] else None for x in rows]
                    matched=next((x["matched_full_no_tax_roi"] for x in rows if x["matched_full_no_tax_roi"]),"")
                    cs=summarize(rois); ls=summarize(lifts)
                    w.writerow({"selector_id":selector,"weight_source":ws,"mechanism":me,"cap":cap,"M":m,"seed_prefix":pref,"valid_seed_count":sum(x is not None for x in rois),"candidate_mean_roi":cs[0],"candidate_median_roi":cs[1],"candidate_p05_roi":cs[2],"candidate_p25_roi":cs[3],"candidate_p75_roi":cs[4],"candidate_p95_roi":cs[5],"candidate_sd_roi":cs[6],"candidate_mcse_roi":cs[7],"candidate_positive_roi_fraction":cs[8],"lift_mean_roi":ls[0],"lift_median_roi":ls[1],"lift_p05_roi":ls[2],"lift_p25_roi":ls[3],"lift_p75_roi":ls[4],"lift_p95_roi":ls[5],"lift_sd_roi":ls[6],"lift_mcse_roi":ls[7],"positive_lift_fraction":ls[8],"matched_full_no_tax_roi":matched,"summary_definition":"seed prefix of shared maximum-M realizations; zero-stake seeds excluded from ROI statistics"})
            with gzip.open(fp,"rt",newline="") as f:
                for row in csv.DictReader(f):
                    if row["mechanism"] not in {"WR_DUPLICATE_STAKE","WOR_DISTINCT"}: continue
                    key=(row["selector_id"],row["weight_source"],row["mechanism"],row["cap"],row["M"])
                    if current_key is None: current_key=key
                    if key != current_key:
                        flush_group(); group=[]; current_key=key
                    group.append(row)
            flush_group()
    # Scientific aggregation unit for the primary/raw surfaces.  Stochastic
    # cells are pooled across all 100 seeds (one row per selector × allocation
    # family), while deterministic arms are retained once.  Individual seed
    # rows remain available only in cell_metrics as diagnostics; no lucky seed
    # can enter the primary Pareto search.
    ensemble_fields=["selector_id","weight_source","mechanism","cap","M","seed","seed_count","seed_scope","stake_yuan","gross_pre_tax_yuan","tax_yuan","pre_tax_net_yuan","tax_adjusted_net_yuan","no_tax_roi","tax_adjusted_roi","matched_full_no_tax_roi","matched_full_lift","capital_utilization_vs_full","coverage_hit_rate","ticket_hit_rate","unique_ticket_coverage","duplicate_ticket_ratio","seed_gross_weighted_mean_issue_hhi","seed_gross_weighted_mean_top_issue_share","seed_mean_drawdown_no_tax_yuan","seed_max_drawdown_no_tax_yuan","longest_miss_streak","largest_signed_issue_no_tax_yuan","largest_signed_issue_index","global_cell","aggregation_definition","comparable_incumbent_roi","comparable_incumbent_manifest","challenger_minus_comparable_incumbent","champion_common_support_disposition","comparison_inapplicability_reason"]
    ensemble_path=out/"ensemble_metrics.csv.gz"
    with gzip.GzipFile(filename=str(ensemble_path),mode="wb",mtime=0) as gf, __import__("io").TextIOWrapper(gf,newline="") as etxt:
        ew=csv.DictWriter(etxt,fieldnames=ensemble_fields); ew.writeheader()
        for fp in sorted(out.glob("cell_metrics-*.csv.gz")):
            rows=list(csv.DictReader(gzip.open(fp,"rt",newline="")))
            matched_full_stake=float(next(x["stake_yuan"] for x in rows if x["mechanism"]=="FULL_ENUMERATED"))
            by_key=defaultdict(list)
            for row in rows:
                by_key[(row["selector_id"],row["weight_source"],row["mechanism"],row["cap"],row["M"])].append(row)
            for (selector,ws,me,cap,m), group in sorted(by_key.items()):
                common = selector == "S1_NO_GATE_K4"
                ew.writerow(aggregate_ensemble_group(group, matched_full_stake, COMMON_SUPPORT_INCUMBENT_ROI if common else None, COMMON_SUPPORT_INCUMBENT_MANIFEST if common else ""))
    with gzip.open(ensemble_path,"rt",newline="") as ef:
        ensemble_rows=list(csv.DictReader(ef))
    def filtered_chart(name, fields, predicate):
        path=out/name
        with gzip.GzipFile(filename=str(path),mode="wb",mtime=0) as gf, __import__("io").TextIOWrapper(gf,newline="") as tf:
            w=csv.DictWriter(tf,fieldnames=fields); w.writeheader()
            for row in ensemble_rows:
                if predicate(row): w.writerow({k:row.get(k,"") for k in fields})
        return path
    filtered_chart("chart_source_selector_full_surface.csv.gz", ["selector_id","mechanism","M","seed_scope","stake_yuan","no_tax_roi","tax_adjusted_roi","matched_full_lift","capital_utilization_vs_full","seed_mean_drawdown_no_tax_yuan","seed_gross_weighted_mean_issue_hhi"], lambda r:r["mechanism"]=="FULL_ENUMERATED")
    filtered_chart("chart_source_allocation_lift_m64.csv.gz", ["selector_id","weight_source","mechanism","cap","M","seed","seed_scope","no_tax_roi","matched_full_lift","comparable_incumbent_roi","challenger_minus_comparable_incumbent","stake_yuan","seed_mean_drawdown_no_tax_yuan","seed_gross_weighted_mean_issue_hhi"], lambda r:r["M"]=="64")
    filtered_chart("chart_source_full_dense_m_curve.csv.gz", ["selector_id","weight_source","mechanism","cap","M","seed_scope","no_tax_roi","matched_full_lift","stake_yuan"], lambda r:r["seed_scope"]=="ENSEMBLE_100")
    filtered_chart("chart_source_heatmap_absolute_lift.csv.gz", ["selector_id","weight_source","mechanism","cap","M","seed_scope","no_tax_roi","matched_full_lift"], lambda r:r["seed_scope"] in {"ENSEMBLE_100","DETERMINISTIC"})
    filtered_chart("chart_source_capital_risk_tax_hit.csv.gz", ["selector_id","weight_source","mechanism","cap","M","seed_scope","stake_yuan","tax_yuan","tax_adjusted_roi","coverage_hit_rate","ticket_hit_rate","seed_mean_drawdown_no_tax_yuan","seed_gross_weighted_mean_issue_hhi"], lambda r:r["seed_scope"] in {"ENSEMBLE_100","DETERMINISTIC"})
    # Year/fold/LOYO diagnostics are built from the same exact issue arrays,
    # not from a second approximation or a post-selection resample.
    with (out/"stability_year_fold_loyo.csv").open("w",newline="") as sf:
        sw=csv.writer(sf); sw.writerow(["target","selector_id","mechanism","M","seed_scope","slice_type","slice_label","year","fold","loyo","first_kickoff_ts_order","stake_yuan","pre_tax_net_yuan","no_tax_roi","scope"])
        for spec in target_specs:
            if spec["role"]=="SEED_PANEL_SCREEN": continue
            nets,stakes=issue_arrays(spec)
            years=sorted({m["year"] for m in issue_meta.values()}); folds=sorted({m["fold"] for m in issue_meta.values()})
            selector_id=selectors[spec["selector_index"]]["selector_id"]
            mech="MATCHED_FULL" if spec["role"]=="MATCHED_FULL_CONFIRMATORY" else spec["label"].split("/")[2]
            mval="2187" if spec["role"]=="MATCHED_FULL_CONFIRMATORY" else ""
            scope="BOUNDED_TARGET_REGISTRY"
            seed_scope="DETERMINISTIC" if spec["role"]=="MATCHED_FULL_CONFIRMATORY" else ("ENSEMBLE_100" if spec.get("aggregate_direct_indices") is not None else "TARGET")
            def emit(kind,label,ix,year="",fold="",loyo=""):
                st=sum(stakes[i] for i in ix); nt=sum(nets[i] for i in ix)
                sw.writerow([spec["label"],selector_id,mech,mval,seed_scope,kind,label,year,fold,loyo,"first_kickoff_ts ASC; issue_instance ASC tie-break",money(st),f"{nt:.6f}",f"{nt/st:.12f}" if st else "",scope])
            for year in years:
                ix=[i for i in range(nissue) if issue_meta[issue_order[i]]["year"]==year]; emit("YEAR",year,ix,year=year,fold=f"OOS_{year}",loyo=f"LOYO_{year}")
                ix=[i for i in range(nissue) if issue_meta[issue_order[i]]["year"]!=year]; emit("LOYO",f"EXCLUDE_{year}",ix,year="",fold="",loyo=f"LOYO_{year}")
            for fold in folds:
                ix=[i for i in range(nissue) if issue_meta[issue_order[i]]["fold"]==fold]; emit("FOLD",fold,ix,year=fold.replace("OOS_",""),fold=fold)
    # Seed convergence is the exact prefix table; stability is a distinct
    # bounded YEAR/FOLD/LOYO table and must never be mislabeled as convergence.
    shutil.copyfile(prefix_path, out/"chart_source_seed_convergence.csv.gz")
    # Baseline bridge with the declared schema.  Legacy rows are explicitly
    # marked diagnostic, while all current rows use this run's cohort and
    # common-support denominator.  The #159 transfer number is checked from
    # its accepted n=2 complete-issue row rather than copied unchecked.
    # The incumbent denominator is the eligible S1_NO_GATE_K4 issue/identity
    # set only.  Hash canonical identity keys (not every one of the 36,830
    # supports, and not rows from other selectors) so the bridge is auditable
    # against the accepted v2r3 common-support cohort.
    common_support_si = selector_idx["S1_NO_GATE_K4"]
    common_support_tokens = common_support_identity_tokens(supports, common_support_si)
    if len(common_support_tokens) != selector_available_identity[common_support_si]:
        raise RuntimeError("S1 common-support identity denominator drift")
    common_support_hash=hashlib.sha256("\n".join(common_support_tokens).encode()).hexdigest()
    baseline_fields=["baseline_id","source_issue_package","source_manifest","source_gate_a_manifest","source_gate_b_manifest","outcome_input_manifest","generated_package_identity","reference_outcome_package","cohort_denominator","common_support_hash","selector","weight_vector","mechanism","M","seed_aggregation","stake_rule","pre_tax_roi","matched_full_lift","seed_mcse","positive_seed_fraction","bootstrap_lower","bootstrap_upper","ex_largest_issue_roi","ex_largest_year_roi","evidence_grade","incumbent_or_challenger","added_lever","decision_reason","outcome_boundary"]
    bootstrap_rows={}
    with (out/"issue_cluster_bootstrap.csv").open(newline="") as bf:
        for br in csv.DictReader(bf): bootstrap_rows[br["target"]]=br
    ensemble_rows=[]
    with gzip.open(ensemble_path,"rt",newline="") as ef: ensemble_rows=list(csv.DictReader(ef))
    incumbent=next((r for r in ensemble_rows if r["selector_id"]=="S1_NO_GATE_K4" and r["weight_source"]=="Q_WEIGHT" and r["mechanism"]=="WOR_DISTINCT" and r["M"]=="64" and r["seed_scope"]=="ENSEMBLE_100"),None)
    if incumbent is None: raise RuntimeError("missing S1 Q/WOR M64 100-seed ensemble baseline")
    assert_s1_incumbent_anchors(incumbent)
    full_roi=float(incumbent["matched_full_no_tax_roi"])
    inc_spec=next(x for x in target_specs if x["role"]=="CONFIRMATORY_INCUMBENT_100_SEED")
    inc_nets,inc_stakes=issue_arrays(inc_spec); positive_idx=[i for i,s in enumerate(inc_stakes) if s>0]
    inc_total_net=sum(inc_nets); inc_total_stake=sum(inc_stakes); ex_i=max(positive_idx,key=lambda i:inc_nets[i])
    ex_issue_roi=(inc_total_net-inc_nets[ex_i])/(inc_total_stake-inc_stakes[ex_i]) if inc_total_stake-inc_stakes[ex_i] else 0.0
    year_totals=defaultdict(lambda:[0.0,0.0])
    for i,(v,s) in enumerate(zip(inc_nets,inc_stakes)):
        year_totals[issue_meta[issue_order[i]]["year"]][0] += v; year_totals[issue_meta[issue_order[i]]["year"]][1] += s
    ex_year=max(year_totals, key=lambda y: year_totals[y][0]) if year_totals else ""
    year_stake=sum(s for i,s in enumerate(inc_stakes) if issue_meta[issue_order[i]]["year"]!=ex_year); year_net=sum(v for i,v in enumerate(inc_nets) if issue_meta[issue_order[i]]["year"]!=ex_year)
    ex_year_roi=year_net/year_stake if year_stake else 0.0
    inc_boot=bootstrap_rows[inc_spec["label"]]
    def base_row(**kw):
        x={k:"" for k in baseline_fields}; x.update(kw); return x
    with (out/"baseline_registry.csv").open("w",newline="") as bf:
        bw=csv.DictWriter(bf,fieldnames=baseline_fields); bw.writeheader()
        bw.writerow(base_row(baseline_id="B167_V3R1_COMMON_SUPPORT_ENSEMBLE_100",source_issue_package="#167 Gate-B v2r3 common-support incumbent",source_manifest=COMMON_SUPPORT_INCUMBENT_MANIFEST,source_gate_a_manifest=EXPECTED_GA_MANIFEST,source_gate_b_manifest=COMMON_SUPPORT_INCUMBENT_MANIFEST,reference_outcome_package="#95 v2r8",cohort_denominator=f"#167-v2r3 common-support 100-seed complete-issue denominator; current v3r1 selector×issue fail-closed; hash is issue_instance|portfolio_id over eligible S1 identities",common_support_hash=common_support_hash,selector="S1_NO_GATE_K4",weight_vector="Q_WEIGHT",mechanism="WOR_DISTINCT",M="64",seed_aggregation="ENSEMBLE_100",stake_rule="¥2 per realized WR/WOR ticket; per-ticket tax",pre_tax_roi=incumbent["no_tax_roi"],matched_full_lift=COMMON_SUPPORT_INCUMBENT_LIFT,seed_mcse=next((r["candidate_mcse_roi"] for r in csv.DictReader(gzip.open(prefix_path,"rt",newline="")) if r["selector_id"]=="S1_NO_GATE_K4" and r["weight_source"]=="Q_WEIGHT" and r["mechanism"]=="WOR_DISTINCT" and r["M"]=="64" and r["seed_prefix"]=="100"),""),positive_seed_fraction=next((r["candidate_positive_roi_fraction"] for r in csv.DictReader(gzip.open(prefix_path,"rt",newline="")) if r["selector_id"]=="S1_NO_GATE_K4" and r["weight_source"]=="Q_WEIGHT" and r["mechanism"]=="WOR_DISTINCT" and r["M"]=="64" and r["seed_prefix"]=="100"),""),bootstrap_lower=inc_boot["candidate_ci95_low"],bootstrap_upper=inc_boot["candidate_ci95_high"],ex_largest_issue_roi=f"{ex_issue_roi:.12f}",ex_largest_year_roi=f"{ex_year_roi:.12f}",evidence_grade="DISCOVERY",incumbent_or_challenger="INCUMBENT_BRIDGE",added_lever="Q_WEIGHT + WOR_DISTINCT + M64",decision_reason="accepted #167-v2r3 common-support incumbent; current v3r1 reproduction equals accepted absolute ROI; retained +0.024903592566 matched-FULL lift; no promotion without held-out/forward validation",outcome_boundary="#95 v2r8 trusted outcomes"))
        # Accepted #137/#151 three-seed numeric anchor, retained as a bridge.
        for seed, roi, lift in (("137001",0.163755668115,0.321452386816),("137002",0.117735771069,0.275432489770),("137003",0.026680342104,0.184377060805)):
            bw.writerow(base_row(baseline_id="B137_151_THREE_SEED",source_issue_package="#137/#151 Gate-B accepted anchor",source_manifest=BJ151_GATE_B_MANIFEST,source_gate_a_manifest=BJ151_GATE_A_MANIFEST,source_gate_b_manifest=BJ151_GATE_B_MANIFEST,reference_outcome_package="#95 v2r8",cohort_denominator="accepted three-seed complete-issue cohort",common_support_hash="accepted-anchor",selector="S1_NO_GATE_K4",weight_vector="Q_WEIGHT",mechanism="WOR_DISTINCT",M="64",seed_aggregation=seed,stake_rule="¥2 per realized ticket",pre_tax_roi=f"{roi:.12f}",matched_full_lift=f"{lift:.12f}",evidence_grade="DISCOVERY",incumbent_or_challenger="CHALLENGER",added_lever="WOR_DISTINCT",decision_reason="historical transfer only; Gate-A and Gate-B manifests are explicit; not a promotion baseline",outcome_boundary="#95 v2r8 trusted outcomes"))
        bw.writerow(base_row(baseline_id="B127_LEGACY",source_issue_package="#127 historical reference",source_manifest="a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da",reference_outcome_package="#95 v2r8",cohort_denominator="legacy reported denominator",common_support_hash="SEGMENT_SCOPE_ONLY",selector="ESP300_GM305_LOWP20",weight_vector="NA",mechanism="FULL",M="NA",seed_aggregation="NA",stake_rule="legacy",pre_tax_roi="-0.083500000000",evidence_grade="LEGACY_REFERENCE",incumbent_or_challenger="LEGACY",decision_reason="historical bridge; not recomputed in this run",outcome_boundary="legacy source"))
        summary159=json.loads((ROOT/"results"/"bj159_gate_b_outcome_settlement_v2r1"/"analysis_summary.json").read_text())
        r159=next(r for r in summary159["m64_seed_stability"] if int(r["n"])==7)
        if abs(float(r159["seed_no_tax_roi"]["mean"])+0.222262319469)>1e-12: raise RuntimeError("#159 N7/M64 numeric bridge drift")
        bw.writerow(base_row(baseline_id="B159_N7_M64_TRANSFER",source_issue_package="#159 Gate-B v2r1",source_manifest=BJ159_GATE_B_MANIFEST,source_gate_a_manifest=BJ159_GATE_A_MANIFEST,source_gate_b_manifest=BJ159_GATE_B_MANIFEST,reference_outcome_package="#95 v2r8",cohort_denominator="N7 M64; complete-issue denominator; three seed rows",common_support_hash="#159-accepted-support",selector="selected-WOR",weight_vector="NA",mechanism="WOR_DISTINCT",M="64",seed_aggregation="N7",stake_rule="#159 declared stake",pre_tax_roi=f"{float(r159['seed_no_tax_roi']['mean']):.12f}",ex_largest_issue_roi="",ex_largest_year_roi="",evidence_grade="DISCOVERY",incumbent_or_challenger="TRANSFER",decision_reason="N7/M64 contract bridge; denominator and numeric verified; Gate-A and Gate-B manifests are explicit",outcome_boundary="#159 accepted outcome bundle"))
        for si, sid in enumerate(selectors):
            # Deterministic FULL control is explicitly emitted once per selector.
            rr=next(r for r in ensemble_rows if r["selector_id"]==sid["selector_id"] and r["mechanism"]=="FULL_ENUMERATED")
            matched_denominator, selector_support_hash = matched_full_denominator_metadata(
                supports, si, selector_issue_total, selector_available_issues,
                selector_unavailable_issues, selector_no_bet_issues,
                selector_identity_total, selector_available_identity,
                selector_unavailable_identity, selector_no_bet_identity,
            )
            bw.writerow(base_row(baseline_id="MATCHED_FULL",source_issue_package="#167 Gate-B v3r1 exact generated control",source_manifest=EXPECTED_GA_MANIFEST,source_gate_a_manifest=EXPECTED_GA_MANIFEST,source_gate_b_manifest="",outcome_input_manifest=EXPECTED_OUTCOME_MANIFEST,generated_package_identity="GENERATED_AT_FINALIZATION",reference_outcome_package="#95 v2r8",cohort_denominator=matched_denominator,common_support_hash=selector_support_hash,selector=sid["selector_id"],weight_vector="NA",mechanism="FULL_ENUMERATED",M="2187",seed_aggregation="DETERMINISTIC",stake_rule="¥2 per full ticket",pre_tax_roi=rr["no_tax_roi"],matched_full_lift="0.000000000000",evidence_grade="DISCOVERY",incumbent_or_challenger="MATCHED_FULL",decision_reason="selector-specific fail-closed matched-FULL denominator control; final package identity generated at finalization",outcome_boundary="#95 v2r8 trusted outcomes"))
    # Pareto surfaces.  The full 492×24,723 surface is written as shards, so
    # never materialise its ~12.2M rows in Python.  A compact metric stream is
    # externally sorted in the package scratch area and scanned once; only
    # the true skyline is retained.  The robust front is deliberately *not*
    # copied from the raw front: it is restricted to the declared bootstrap
    # target family and uses bootstrap lower-bound, ex-largest-issue ROI,
    # drawdown and concentration coordinates.
    pareto_tmp = out / ".pareto_metrics.tsv"
    pareto_sorted = out / ".pareto_metrics.sorted.tsv"
    with pareto_tmp.open("w") as sf:
        with gzip.open(ensemble_path,"rt",newline="") as f:
            for r in csv.DictReader(f):
                if not r["no_tax_roi"] or not r["matched_full_lift"] or float(r["stake_yuan"]) == 0:
                    continue
                sf.write("\t".join((r["no_tax_roi"], r["matched_full_lift"], r["seed_mean_drawdown_no_tax_yuan"], r["seed_gross_weighted_mean_issue_hhi"], r["selector_id"], r["weight_source"], r["mechanism"], r["cap"], r["M"], r["seed"], r["global_cell"], r["seed_scope"])) + "\n")
    sort_env = dict(os.environ, TMPDIR=str(out / ".sorttmp"))
    (out / ".sorttmp").mkdir(exist_ok=True)
    with pareto_sorted.open("w") as sf:
        subprocess.run(["sort","-t","\t","-k1,1gr","-k2,2gr","-k3,3n","-k4,4n",str(pareto_tmp)], stdout=sf, check=True, env=sort_env)
    def dominates(a,b):
        return (a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a[3] <= b[3] and (a[0] > b[0] or a[1] > b[1] or a[2] < b[2] or a[3] < b[3]))
    skyline=[]
    with pareto_sorted.open() as f:
        for line in f:
            q=line.rstrip("\n").split("\t")
            x=(float(q[0]),float(q[1]),float(q[2]),float(q[3]),*q[4:])
            if any(dominates(y,x) for y in skyline): continue
            skyline=[y for y in skyline if not dominates(x,y)]
            skyline.append(x)
    with (out/"raw_pareto_front.csv").open("w",newline="") as f:
        w=csv.writer(f); w.writerow(["selector_id","weight_source","mechanism","cap","M","seed","seed_scope","no_tax_roi","matched_full_lift","seed_mean_drawdown_no_tax_yuan","seed_gross_weighted_mean_issue_hhi","global_cell","front_definition"])
        for x in skyline: w.writerow([x[4],x[5],x[6],x[7],x[8],x[9],x[11],f"{x[0]:.12f}",f"{x[1]:.12f}",f"{x[2]:.6f}",f"{x[3]:.12f}",x[10],"100-seed ensemble + deterministic arms; exact external-sort skyline"])
    boot_low={}
    with (out/"issue_cluster_bootstrap.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            if r["global_cell"] and r["global_cell"] != "-1" and r["candidate_ci95_low"]:
                boot_low[int(r["global_cell"])] = (float(r["candidate_ci95_low"]), r["role"], r["target"])
    robust_candidates=[]
    for fp in sorted(out.glob("cell_metrics-*.csv.gz")):
        with gzip.open(fp,"rt",newline="") as f:
            for r in csv.DictReader(f):
                ti=int(r["bootstrap_target_index"])
                if ti < 0: continue
                spec=target_specs[ti]
                # Primary robust front is bounded to ensemble rows and
                # deterministic controls; individual seed rows are ledger
                # diagnostics only.
                if spec["role"] == "SEED_PANEL_SCREEN": continue
                gc=int(r["global_cell"]); low, role, label = boot_low[gc]
                nets=[boot_net[ii*len(boot_targets)+ti] for ii in range(nissue)]
                stakes=[boot_stake[ii*len(boot_targets)+ti] for ii in range(nissue)]
                total_net=sum(nets); total_stake=sum(stakes); k=max(range(nissue), key=lambda i:nets[i]) if nets else 0
                ex_stake=total_stake-stakes[k]; ex_roi=(total_net-nets[k])/ex_stake if ex_stake else 0.0
                year_totals=defaultdict(lambda:[0.0,0.0])
                for i,(v,s) in enumerate(zip(nets,stakes)): year_totals[issue_meta[issue_order[i]]["year"]][0] += v; year_totals[issue_meta[issue_order[i]]["year"]][1] += s
                largest_year=max(year_totals,key=lambda y:year_totals[y][0]) if year_totals else ""
                ys=sum(v for i,v in enumerate(nets) if issue_meta[issue_order[i]]["year"]!=largest_year); yst=sum(v for i,v in enumerate(stakes) if issue_meta[issue_order[i]]["year"]!=largest_year)
                robust_candidates.append((low,ex_roi,ys/yst if yst else 0.0,float(r["drawdown_no_tax_yuan"]),float(r["gross_issue_hhi"]),r["selector_id"],r["weight_source"],r["mechanism"],r["cap"],r["M"],r["seed"],gc,role,label,largest_year))
    # Add the confirmatory 100-seed aggregate explicitly: it has no individual
    # cell index by design, but it is a real pooled ticket row with its own
    # paired bootstrap and matched FULL selector.
    agg_boot=bootstrap_rows[inc_spec["label"]]
    robust_candidates.append((float(agg_boot["candidate_ci95_low"]),ex_issue_roi,ex_year_roi,float(incumbent["seed_mean_drawdown_no_tax_yuan"]),float(incumbent["seed_gross_weighted_mean_issue_hhi"]),incumbent["selector_id"],incumbent["weight_source"],incumbent["mechanism"],incumbent["cap"],incumbent["M"],incumbent["seed"],-1,inc_spec["role"],inc_spec["label"],ex_year))
    def robust_dominates(a,b):
        # Robust front has three higher-better coordinates (bootstrap lower
        # bound, ex-largest-issue ROI, ex-largest-year ROI) and two
        # lower-better coordinates (drawdown, HHI).
        ge=(a[0]>=b[0] and a[1]>=b[1] and a[2]>=b[2] and a[3]<=b[3] and a[4]<=b[4])
        strict=(a[0]>b[0] or a[1]>b[1] or a[2]>b[2] or a[3]<b[3] or a[4]<b[4])
        return ge and strict
    robust=[]
    for x in sorted(robust_candidates,key=lambda q:(-q[0],-q[1],-q[2],q[3],q[4])):
        if any(robust_dominates(y,x) for y in robust): continue
        robust=[y for y in robust if not robust_dominates(x,y)]
        robust.append(x)
    with (out/"robust_pareto_front.csv").open("w",newline="") as f:
        w=csv.writer(f); w.writerow(["selector_id","weight_source","mechanism","cap","M","seed","bootstrap_ci95_low","ex_largest_issue_no_tax_roi","ex_largest_year_no_tax_roi","ex_largest_year","drawdown_no_tax_yuan","gross_issue_hhi","global_cell","target_role","front_definition"])
        for x in robust: w.writerow([x[5],x[6],x[7],x[8],x[9],x[10],f"{x[0]:.12f}",f"{x[1]:.12f}",f"{x[2]:.12f}",x[14],f"{x[3]:.6f}",f"{x[4]:.12f}",x[11],x[12],"100-seed aggregate/deterministic targets; bootstrap lower bound + ex-largest issue/year ROI + drawdown + concentration"])
    for p in (pareto_tmp,pareto_sorted):
        try: p.unlink()
        except FileNotFoundError: pass
    shutil.rmtree(out/".sorttmp", ignore_errors=True)
    with (out/"selector_policy_census.csv").open("w",newline="") as f:
        w=csv.writer(f); w.writerow(["selector_id","issue_instance","status","selected_identity_count"])
        for (si,issue), st in sorted(policy_status.items()):
            w.writerow([selectors[si]["selector_id"],issue,st,policy_identity_count[(si,issue)]])
    missing_matches=sorted({m for s in supports.values() for m in s["missing_match_ids"]})
    with (out/"missing_outcome_matches.csv").open("w",newline="") as f:
        w=csv.writer(f); w.writerow(["match_id","support_count","policy_selector_count"])
        for m in missing_matches:
            ss=[s for s in supports.values() if m in s["missing_match_ids"]]
            sels={si for s in ss for si in s["selectors"]}
            w.writerow([m,len(ss),len(sels)])
    policy_counts=defaultdict(int)
    for st in policy_status.values(): policy_counts[st]+=1
    unavailable_selector_ids=sorted({si for (si,_),st in policy_status.items() if st == "UNAVAILABLE_CANONICAL_OUTCOME"})
    tested_surface_cells=len(ensemble_rows); ensemble_rows_n=sum(r["seed_scope"]=="ENSEMBLE_100" for r in ensemble_rows); deterministic_rows_n=sum(r["seed_scope"]=="DETERMINISTIC" for r in ensemble_rows)
    (out/"multiple_search_adjustment.json").write_text(json.dumps({"nominal_alpha":0.05,"tested_surface_cells":tested_surface_cells,"ensemble_rows":ensemble_rows_n,"deterministic_rows":deterministic_rows_n,"seed_ledger_rows":NSEL*NCELL,"stochastic_ensemble_families":len(SOURCES)*2*len(M_GRID),"bonferroni_alpha_surface":0.05/tested_surface_cells,"sidak_alpha_surface":1-(1-0.05)**(1/tested_surface_cells),"primary_confirmatory_family":"S1_NO_GATE_K4/Q_WEIGHT/WOR_DISTINCT/M64/ENSEMBLE_100 paired with selector-matched FULL","screening_vs_confirmation":"primary/raw surfaces use 100-seed ensembles plus deterministic arms once; individual seed ledger is diagnostic only","multiple_search_rule":"no historical aggregate is promoted on nominal ROI alone; held-out/forward validation remains required"},indent=2)+"\n")
    (out/"settlement_card.json").write_text(json.dumps({"issue":167,"contract":"GATE_B_EXACT_TICKET_REPLAY_V3R1","gate_a_manifest":EXPECTED_GA_MANIFEST,"gate_a_content_identity":EXPECTED_GA_CONTENT,"outcome_manifest_sha256":EXPECTED_OUTCOME_MANIFEST,"outcome_payload_sha256":sha(OUTCOMES),"bridge_manifests":{"bj167_gate_b_v2r3":COMMON_SUPPORT_INCUMBENT_MANIFEST,"bj151_gate_a":BJ151_GATE_A_MANIFEST,"bj151_gate_b":BJ151_GATE_B_MANIFEST,"bj159_gate_a":BJ159_GATE_A_MANIFEST,"bj159_gate_b":BJ159_GATE_B_MANIFEST},"selector_count":NSEL,"cell_count":NCELL,"identity_count":identity_count,"canonical_support_count":len(supports),"missing_support_count":sum(not s["available"] for s in supports.values()),"missing_match_count":len(missing_matches),"policy_status_counts":dict(policy_counts),"unavailable_selector_count":len(unavailable_selector_ids),"seed_panel":list(SEEDS),"seed_prefixes":[3,10,25,50,100],"M_grid":list(M_GRID),"caps":list(CAPS),"tax_rule":"20% per independent winning ¥2 ticket gross >= ¥10000; no pooling","primary_metric":"pre-tax no_tax_roi","factorization":"canonical support/vector realization joined back to all selector memberships","outcome_boundary":"#95 v2r8 only; no SQLite fallback; selector×issue fail-closed if any selected identity is missing","matched_full_denominator":"identical SETTLED selector×issue policies","bootstrap":"one common deterministic issue_instance draw matrix; selector-matched FULL pairs; confirmatory 20,000 for declared Q/WOR M64 100-seed aggregate; descriptive targets retain paired draws","bootstrap_draw_matrix_sha256":draw_matrix_sha256,"common_support_hash":common_support_hash,"common_support_hash_definition":"sha256 of sorted issue_instance|portfolio_id tokens for eligible S1_NO_GATE_K4 identities only","primary_surface":"ensemble_metrics.csv.gz; 100-seed stochastic aggregates + deterministic arms once","chart_sources":["selector_full_surface","allocation_lift_fixed_M64","full_dense_M_ensemble_curves","absolute_lift_heatmaps","capital_risk_tax_hit_frontiers","raw_robust_aggregate_pareto","seed_convergence","baseline_bridge"],"promotion_authorized":False,"chronology_key":"first_kickoff_ts, issue_instance"},indent=2)+"\n")
    (out/"README.md").write_text("# #167 Gate B exact ticket replay v3r1\n\nThis package settles the accepted v3r1 492-selector × 24,723-cell surface. Real WR/WOR seeds 137001..137100 use one shared maximum-M realization per canonical support/vector/mechanism; M rows are prefixes. Capped repeats use {1,2,4,8}. P/Q are actual deleted role/code tickets checked against canonical outcomes. Tax is per winning ¥2 ticket with no pooling. The #95 v2r8 outcome bundle is the only outcome source; SQLite is not queried. A selector×issue policy is fail-closed when any selected identity lacks a canonical outcome: all identities in that policy receive zero settled stake/gross and are counted as UNAVAILABLE_CANONICAL_OUTCOME. Pre-tax ROI is primary; the result is descriptive and not purchase authority. Chronology is first_kickoff_ts with issue_instance as deterministic tie-break.\n")
    # Exact chart inputs are explicit payloads, not plots reconstructed by PI
    # from the 12.2M-cell ledger.
    shutil.copyfile(prefix_path, out/"chart_source_seed_prefix.csv.gz")
    shutil.copyfile(out/"selector_policy_census.csv", out/"chart_source_policy_status.csv")
    shutil.copyfile(out/"issue_cluster_bootstrap.csv", out/"chart_source_bootstrap.csv")
    shutil.copyfile(ensemble_path, out/"chart_source_ensemble_metrics.csv.gz")
    shutil.copyfile(out/"baseline_registry.csv", out/"chart_source_baseline_bridge.csv")
    write_chart_source_pareto(out/"chart_source_pareto.csv", out/"raw_pareto_front.csv", out/"robust_pareto_front.csv")
    (out/"source_binding.json").write_text(json.dumps({"issue":167,"contract":"GATE_B_EXACT_TICKET_REPLAY_V3R1","sqlite_used":False,"gate_a":{"package":"bj167_gate_a_strategy_atlas_v3r1","SHA256SUMS.json":EXPECTED_GA_MANIFEST,"CONTENT_IDENTITY.json":EXPECTED_GA_CONTENT},"outcome":{"package":"bj95_gate_b_outcome_settlement_v2r8","SHA256SUMS.json":EXPECTED_OUTCOME_MANIFEST,"canonical_outcome_join.csv":EXPECTED_OUTCOME_PAYLOAD,"rows":len(outcomes)},"accepted_gate_a_bridges":{"bj151":BJ151_GATE_A_MANIFEST,"bj159":BJ159_GATE_A_MANIFEST},"accepted_gate_b_bridges":{"bj167_v2r3_common_support":COMMON_SUPPORT_INCUMBENT_MANIFEST,"bj151":BJ151_GATE_B_MANIFEST,"bj159":BJ159_GATE_B_MANIFEST},"missing_outcome_matches":missing_matches,"policy_denominator":"selector×issue; any missing selected identity closes the policy","source_files":["#167 Gate-A v3r1 selector/role/allocation shards","#95 v2r8 canonical_outcome_join.csv","#167 v2r3 common-support incumbent","#151 Gate-A/Gate-B settlement","#159 Gate-A/Gate-B settlement"]},sort_keys=True,indent=2)+"\n")
    write_file_census(out)
    # source_binding and file_census are now present, so the production
    # identity helper hashes the complete staged payload exactly once.
    finalize_package_identity(out, "bj167-gate-b-exact-v3r1", {"gate_a_manifest_sha256":EXPECTED_GA_MANIFEST,"gate_a_content_identity_sha256":EXPECTED_GA_CONTENT,"outcome_manifest_sha256":EXPECTED_OUTCOME_MANIFEST,"outcome_payload_sha256":EXPECTED_OUTCOME_PAYLOAD,"sqlite_used":False,"policy_denominator":"selector×issue fail-closed"})
    # The manifest and every payload are now complete and self-consistent in
    # staging.  Only this final rename exposes the immutable package; a late
    # exception above leaves the previous target untouched.
    atomic_publish(stage_out, final_out)
    print(f"WROTE {final_out}",flush=True)

if __name__ == "__main__": main()
