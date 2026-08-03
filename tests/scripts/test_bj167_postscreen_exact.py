"""Production-path checks for the bounded #167 post-screening evidence pass."""
from __future__ import annotations

import array, csv, gzip, importlib.util, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / ".scratch" / "bj167_postscreen_fixture"
spec = importlib.util.spec_from_file_location("bj167_postscreen", ROOT / "scripts" / "settle_bj167_atlas_postscreen_exact.py")
POST = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(POST)
science_spec = importlib.util.spec_from_file_location("bj167_science", ROOT / "scripts" / "settle_bj167_scientific_stability_exact.py")
SCIENCE = importlib.util.module_from_spec(science_spec); assert science_spec.loader is not None; science_spec.loader.exec_module(SCIENCE)


def test_candidate_freeze_union_and_shared_paired_bootstrap():
    if FIXTURE.exists(): shutil.rmtree(FIXTURE)
    screen = FIXTURE / "screen"; out = FIXTURE / "out"; screen.mkdir(parents=True); out.mkdir()
    fields = ["selector_id", "weight_source", "mechanism", "cap", "M", "seed", "seed_scope", "global_cell", "no_tax_roi", "stake_yuan", "matched_full_lift"]
    rows = [
        dict(selector_id="S0", weight_source="Q_WEIGHT", mechanism="WOR_DISTINCT", cap="NA", M="64", seed="ENSEMBLE_100", seed_scope="ENSEMBLE_100", global_cell="", no_tax_roi="0.166666666667", stake_yuan="100", matched_full_lift=""),
        dict(selector_id="S0", weight_source="Q_WEIGHT", mechanism="CAPPED_REPEAT", cap="1", M="64", seed="NA", seed_scope="DETERMINISTIC", global_cell="9", no_tax_roi="0.166666666667", stake_yuan="100", matched_full_lift=""),
    ]
    with gzip.open(screen / "ensemble_metrics.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    with (screen / "raw_pareto_front.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerow(rows[1])
    (screen / "SHA256SUMS.json").write_text("{}\n")
    frozen = POST.candidate_rows(screen)
    assert len(frozen) == 2
    assert "RAW_PARETO" in frozen[0]["candidate_inclusion"]
    assert all("ABSOLUTE_POSITIVE" in r["candidate_inclusion"] for r in frozen)
    for i, r in enumerate(frozen): r["candidate_index"] = i
    n = 3
    values = {name: [array.array("d", value), array.array("d", value)] for name, value in {
        "net": [2.0, -1.0, 0.0], "stake": [2.0, 2.0, 2.0], "gross": [4.0, 1.0, 2.0], "tax": [0.0, 0.0, 0.0], "hit": [1.0, 1.0, 1.0], "tax_line_hit": [0.0, 0.0, 0.0],
        "full_net": [0.0, -3.0, -1.0], "full_stake": [4.0, 4.0, 4.0], "full_gross": [4.0, 1.0, 3.0], "full_tax": [0.0, 0.0, 0.0],
    }.items()}
    # The two candidates intentionally share this small fixture's ledger;
    # the assertion below confirms every target uses the same stored issue
    # resample matrix rather than advancing a per-target RNG.
    issue_order = ["I1", "I2", "I3"]
    issue_meta = {x: {"year": "2024" if x != "I3" else "2025", "fold": "OOS_2024", "first_kickoff_ts": x} for x in issue_order}
    boot = POST.bootstrap_rows(frozen, values, issue_order, issue_meta, out, full_family_size=100)
    assert len(boot) == 2 and boot[0]["bootstrap_draw_matrix_sha256"] == boot[1]["bootstrap_draw_matrix_sha256"]
    assert boot[0]["candidate_ci95_low"] is not None and boot[0]["paired_lift_two_sided_p"] is not None
    assert json.loads((out / "paired_bootstrap_draw_matrix.json").read_text())["replicate_count"] == 20_000
    # Exercise the actual production output helpers: blanking/retention and
    # robust-front inputs come from their real implementation, not a copied
    # miniature calculation in this test.
    POST.write_stability(frozen, values, issue_order, issue_meta, out)
    POST.write_outputs(frozen, boot, values, issue_order, issue_meta, out)
    tax_chart = list(csv.DictReader((out / "chart_source_tax_line_exposure_retention.csv").open(newline="")))
    assert len(tax_chart) == 2 and tax_chart[0]["gross_return_retention_vs_matched_full"] == "0.875000000000"
    assert float(boot[0]["candidate_bonferroni_adjusted_p"]) >= float(boot[0]["candidate_two_sided_p"])
    assert (out / "candidate_paired_bootstrap_20000.csv").exists() and (out / "bh_descriptive_significance.csv").exists()
    shutil.rmtree(FIXTURE)


def test_production_role_vector_q_delete_and_native_profile():
    """Use a real Gate-A role shape, not a uniform synthetic tie vector."""
    role_file = sorted(POST.R.GA.glob("selector_role_vectors-*.csv.gz"))[0]
    with gzip.open(role_file, "rt", newline="") as f:
        raw = [next(csv.DictReader(f))]
    # Re-open because DictReader cannot be recreated after consuming the first
    # construction without a header; retain seven roles of one identity.
    with gzip.open(role_file, "rt", newline="") as f:
        reader = csv.DictReader(f); first = next(reader); key = (first["selector_id"], first["issue_instance"], first["portfolio_id"])
        source_rows = [first]
        while len(source_rows) < 7:
            nxt = next(reader)
            assert (nxt["selector_id"], nxt["issue_instance"], nxt["portfolio_id"]) == key
            source_rows.append(nxt)
    roles = [POST.R.role_values(r) for r in source_rows]
    _pl, _pc, ql, qc = POST.R.derive_delete(roles)
    expected = min(((i, c) for i in range(7) for c in range(3)), key=lambda x: (roles[x[0]]["source"]["Q_WEIGHT"][x[1]], x[0], x[1]))
    assert (ql, qc) == expected
    lib = POST.configure_native(); buffers = POST.profile_buffers()
    vec = array.array("d", [v for role in roles for v in role["source"]["Q_WEIGHT"]])
    lib.bj167_profile_allocation(POST.R.ptr(vec, __import__("ctypes").c_double), 0, b"production-role-fixture", *(POST.R.ptr(x, __import__("ctypes").c_int) for x in buffers))
    candidate = {"mechanism": "WOR_DISTINCT", "weight_source": "Q_WEIGHT", "M": "64", "cap": "NA", "seed_scope": "ENSEMBLE_100"}
    hit, unique, duplicate, _ = POST.metric_for(candidate, roles, 0, {"Q_WEIGHT": buffers})
    assert unique + duplicate == 100 * 64 and hit >= 0
    # Gate-A's M=2187 contract: WOR has the same FULL ticket result for each
    # real seed (hence the 100x aggregate), while top-mass is exactly FULL.
    wor = POST.metric_for(dict(candidate, M="2187"), roles, 0, {"Q_WEIGHT": buffers})
    top = POST.metric_for({"mechanism": "DETERMINISTIC_TOP_MASS", "weight_source": "Q_WEIGHT", "M": "2187", "cap": "NA", "seed_scope": "DETERMINISTIC"}, roles, 0, {"Q_WEIGHT": buffers})
    full = POST.metric_for({"mechanism": "FULL_ENUMERATED", "weight_source": "NA", "M": "2187", "cap": "NA", "seed_scope": "DETERMINISTIC"}, roles, 0, {})
    assert tuple(v // 100 for v in wor[:3]) == full[:3] and top[:3] == full[:3]


def test_all_scientific_layout_includes_deterministic_and_m2187_contract_cells():
    cells = SCIENCE.science_cells()
    assert len(cells) == 963
    for source in POST.R.SOURCES:
        assert (source, "WOR_DISTINCT", "NA", "2187", "ENSEMBLE_100") in cells
        assert (source, "DETERMINISTIC_TOP_MASS", "NA", "2187", "DETERMINISTIC") in cells
        assert (source, "CAPPED_REPEAT", "8", "16", "DETERMINISTIC") in cells
    assert cells[-3:] == [("NA", "FULL_ENUMERATED", "NA", "2187", "DETERMINISTIC"), ("NA", "P_MIN_GLOBAL_DELETE", "NA", "1458", "DETERMINISTIC"), ("NA", "Q_MIN_GLOBAL_DELETE", "NA", "1458", "DETERMINISTIC")]


def test_scientific_native_companion_m2187_reconciles_production_role_shape():
    role_file = sorted(POST.R.GA.glob("selector_role_vectors-*.csv.gz"))[0]
    with gzip.open(role_file, "rt", newline="") as f:
        reader = csv.DictReader(f); first = next(reader); key = (first["selector_id"], first["issue_instance"], first["portfolio_id"]); raw = [first]
        while len(raw) < 7:
            row = next(reader); assert (row["selector_id"], row["issue_instance"], row["portfolio_id"]) == key; raw.append(row)
    roles = [POST.R.role_values(r) for r in raw]; n = 963
    ds = lambda: array.array("d", [0.0]) * n
    tmp = [ds() for _ in range(5)]; totals = [ds() for _ in range(7)]
    mark = array.array("B", [0]) * n; touched = array.array("i", [0]) * n
    year_net = ds(); year_stake = ds(); fold_net = ds(); fold_stake = ds(); largest = array.array("d", [-float("inf")]) * n; largest_stake = ds(); largest_issue = array.array("i", [-1]) * n
    full_issue_net = array.array("d", [0.0]); full_issue_stake = array.array("d", [0.0])
    lib = SCIENCE.configure(); pd = __import__("ctypes").c_double; pi = __import__("ctypes").c_int
    lib.bj167_scientific_set_buffers(*(POST.R.ptr(x, pd) for x in tmp), POST.R.ptr(mark, __import__("ctypes").c_ubyte), POST.R.ptr(touched, pi), *(POST.R.ptr(x, pd) for x in totals), POST.R.ptr(year_net, pd), POST.R.ptr(year_stake, pd), POST.R.ptr(fold_net, pd), POST.R.ptr(fold_stake, pd), POST.R.ptr(largest, pd), POST.R.ptr(largest_stake, pd), POST.R.ptr(largest_issue, pi), POST.R.ptr(full_issue_net, pd), POST.R.ptr(full_issue_stake, pd), 1, 1, 1)
    occ = array.array("i", [0]); source = array.array("d", [v for role in roles for v in role["source"]["Q_WEIGHT"]])
    lib.bj167_scientific_begin_issue(0, 0, 0)
    lib.bj167_scientific_process_source(POST.R.ptr(source, pd), 0, b"production-science-fixture", 2.0, POST.R.ptr(occ, pi), 1, 0)
    pl, pc, ql, qc = POST.R.derive_delete(roles); lib.bj167_scientific_add_structural(0, 0, pl, pc, ql, qc, 2.0); lib.bj167_scientific_end_issue()
    full = 960; wor = 20 + 19; top = 140 + 19
    assert totals[0][wor] / 100 == totals[0][full] and totals[1][wor] / 100 == totals[1][full]
    assert totals[0][top] == totals[0][full] and totals[1][top] == totals[1][full]
