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
    slices = list(csv.DictReader((out / "stability_year_fold_loyo.csv").open(newline="")))
    # Every emitted slice carries both sides of the selector-matched control
    # and the exact difference, rather than candidate-only ROI.
    assert all({"candidate_no_tax_roi", "matched_full_no_tax_roi", "paired_lift"} <= set(r) for r in slices)
    year_2024 = next(r for r in slices if r["candidate_index"] == "0" and r["split_type"] == "YEAR" and r["split"] == "2024")
    assert year_2024["candidate_no_tax_roi"] == "0.250000000000" and year_2024["matched_full_no_tax_roi"] == "-0.375000000000" and year_2024["paired_lift"] == "0.625000000000"
    explicit = [{"p": .01}, {"p": .02}]
    POST.bh(explicit, "p", "fixture", full_family_size=20)
    assert explicit[0]["fixture_bonferroni_adjusted_p"] == .2
    assert explicit[0]["fixture_bh_adjusted_p"] == .2
    assert (out / "candidate_paired_bootstrap_20000.csv").exists() and (out / "bh_descriptive_significance.csv").exists()
    # The candidate freeze is deliberately much smaller than the immutable
    # searched family.  Both denominators must survive into the persisted
    # significance artifact, rather than existing only during adjustment.
    significance = list(csv.DictReader((out / "bh_descriptive_significance.csv").open(newline="")))
    assert len(significance) == 4
    assert {r["candidate_freeze_count"] for r in significance} == {"2"}
    assert {r["full_search_family_count"] for r in significance} == {"100"}
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
    assert len(cells) == 963 and len(set(cells)) == 963
    for source in POST.R.SOURCES:
        assert (source, "WOR_DISTINCT", "NA", "2187", "ENSEMBLE_100") in cells
        assert (source, "DETERMINISTIC_TOP_MASS", "NA", "2187", "DETERMINISTIC") in cells
        assert (source, "CAPPED_REPEAT", "8", "16", "DETERMINISTIC") in cells
    assert cells[-3:] == [("NA", "FULL_ENUMERATED", "NA", "2187", "DETERMINISTIC"), ("NA", "P_MIN_GLOBAL_DELETE", "NA", "1458", "DETERMINISTIC"), ("NA", "Q_MIN_GLOBAL_DELETE", "NA", "1458", "DETERMINISTIC")]
    years, folds = {"2023": 2, "2024": 5}, {"F1": 1, "F2": 6}
    assert SCIENCE.retained_issue_count("YEAR", "2023", 7, years, folds) == 2
    assert SCIENCE.retained_issue_count("FOLD", "F1", 7, years, folds) == 1
    assert SCIENCE.retained_issue_count("LOYO", "2023", 7, years, folds) == 5


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
    cumulative = ds(); peak = ds(); drawdown = ds(); miss = array.array("i", [0]) * n; longest_miss = array.array("i", [0]) * n
    year_net = ds(); year_stake = ds(); fold_net = ds(); fold_stake = ds(); largest = array.array("d", [-float("inf")]) * n; largest_stake = ds(); largest_issue = array.array("i", [-1]) * n
    full_issue_net = array.array("d", [0.0]); full_issue_stake = array.array("d", [0.0])
    lib = SCIENCE.configure(); pd = __import__("ctypes").c_double; pi = __import__("ctypes").c_int
    lib.bj167_scientific_set_buffers(*(POST.R.ptr(x, pd) for x in tmp), POST.R.ptr(mark, __import__("ctypes").c_ubyte), POST.R.ptr(touched, pi), *(POST.R.ptr(x, pd) for x in totals), POST.R.ptr(cumulative, pd), POST.R.ptr(peak, pd), POST.R.ptr(drawdown, pd), POST.R.ptr(miss, pi), POST.R.ptr(longest_miss, pi), POST.R.ptr(year_net, pd), POST.R.ptr(year_stake, pd), POST.R.ptr(fold_net, pd), POST.R.ptr(fold_stake, pd), POST.R.ptr(largest, pd), POST.R.ptr(largest_stake, pd), POST.R.ptr(largest_issue, pi), POST.R.ptr(full_issue_net, pd), POST.R.ptr(full_issue_stake, pd), 1, 1, 1)
    occ = array.array("i", [0]); source = array.array("d", [v for role in roles for v in role["source"]["Q_WEIGHT"]])
    lib.bj167_scientific_begin_issue(0, 0, 0)
    lib.bj167_scientific_process_source(POST.R.ptr(source, pd), 0, b"production-science-fixture", 2.0, POST.R.ptr(occ, pi), 1, 0)
    # Nonzero source base must not alias the Q_WEIGHT/base-zero accumulator.
    lib.bj167_scientific_process_source(POST.R.ptr(source, pd), 0, b"production-science-fixture", 2.0, POST.R.ptr(occ, pi), 1, 160)
    pl, pc, ql, qc = POST.R.derive_delete(roles); lib.bj167_scientific_add_structural(0, 0, pl, pc, ql, qc, 2.0); lib.bj167_scientific_end_issue()
    full = 960; wor = 20 + 19; top = 140 + 19
    assert totals[0][wor] / 100 == totals[0][full] and totals[1][wor] / 100 == totals[1][full]
    assert totals[0][top] == totals[0][full] and totals[1][top] == totals[1][full]
    assert totals[1][160 + 20 + 19] == totals[1][wor]


def test_scientific_reconciliation_requires_complete_keyed_963_surface():
    root = ROOT / ".scratch" / "bj167_scientific_reconciliation_fixture"
    if root.exists(): shutil.rmtree(root)
    screen = root / "screen"; out = root / "out"; screen.mkdir(parents=True); out.mkdir()
    fields = ["selector_id", "weight_source", "mechanism", "cap", "M", "seed_scope", "stake_yuan", "gross_pre_tax_yuan", "no_tax_roi", "matched_full_no_tax_roi", "matched_full_lift"]
    with gzip.open(screen / "ensemble_metrics.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for src, mechanism, cap, m, scope in SCIENCE.science_cells():
            w.writerow({"selector_id": "S0", "weight_source": src, "mechanism": mechanism, "cap": cap, "M": m, "seed_scope": scope, "stake_yuan": "0.000000", "gross_pre_tax_yuan": "0.000000", "no_tax_roi": "", "matched_full_no_tax_roi": "", "matched_full_lift": ""})
    cells = SCIENCE.science_cells(); allv = [array.array("d", [0.0]) * len(cells) for _ in range(7)]
    SCIENCE.reconcile_scientific_screen(out, screen, [{"selector_id": "S0"}], cells, allv)
    with gzip.open(out / "scientific_screen_reconciliation.csv.gz", "rt", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 963 and all(r["reconciliation_status"] == "PASS" for r in rows)
    shutil.rmtree(root)


def test_scientific_reconciliation_100_seed_rounding_envelope_is_exactly_bounded():
    """The companion pools before writing; the screen rounds each seed first."""
    full_precision_seed_gross = [0.0000005001] * 100
    screen_serialized_gross = sum(float(f"{x:.6f}") for x in full_precision_seed_gross)
    pooled_gross = sum(full_precision_seed_gross)
    assert screen_serialized_gross != pooled_gross
    money_bound = SCIENCE.serialization_money_envelope("ENSEMBLE_100")
    assert abs(screen_serialized_gross - pooled_gross) <= money_bound
    stake = 1.0
    screen_roi = (screen_serialized_gross - stake) / stake
    pooled_roi = (pooled_gross - stake) / stake
    roi_bound = SCIENCE.serialization_roi_envelope(f"{screen_serialized_gross:.6f}", f"{stake:.6f}", "ENSEMBLE_100")
    assert abs(screen_roi - pooled_roi) <= roi_bound
    # A difference beyond the declared serialization envelope remains a hard
    # mismatch; this is not a generic tolerance relaxation.
    assert abs(screen_serialized_gross - (pooled_gross + 0.00011)) > money_bound


def test_full_atlas_chart_sources_cover_deterministic_dense_m_and_selector_controls():
    root = ROOT / ".scratch" / "bj167_chart_source_fixture"
    if root.exists(): shutil.rmtree(root)
    screen = root / "screen"; out = root / "out"; screen.mkdir(parents=True); out.mkdir()
    fields = ["selector_id", "weight_source", "mechanism", "cap", "M", "seed", "seed_count", "seed_scope", "stake_yuan", "gross_pre_tax_yuan", "tax_yuan", "no_tax_roi", "tax_adjusted_roi", "matched_full_lift", "coverage_hit_rate", "ticket_hit_rate", "capital_utilization_vs_full", "seed_mean_drawdown_no_tax_yuan", "seed_gross_weighted_mean_issue_hhi"]
    rows = [
        {"selector_id":"S0","weight_source":"NA","mechanism":"FULL_ENUMERATED","cap":"NA","M":"2187","seed":"NA","seed_count":"1","seed_scope":"DETERMINISTIC","stake_yuan":"100.000000","gross_pre_tax_yuan":"100.000000","tax_yuan":"0.000000","no_tax_roi":"0.000000000000","tax_adjusted_roi":"0.000000000000","matched_full_lift":"0.000000000000","coverage_hit_rate":"1.0","ticket_hit_rate":".1","capital_utilization_vs_full":"1.0","seed_mean_drawdown_no_tax_yuan":"0","seed_gross_weighted_mean_issue_hhi":".5"},
        {"selector_id":"S0","weight_source":"Q_WEIGHT","mechanism":"RESIDUAL_SYSTEMATIC","cap":"NA","M":"16","seed":"NA","seed_count":"1","seed_scope":"DETERMINISTIC","stake_yuan":"16.000000","gross_pre_tax_yuan":"50.000000","tax_yuan":"10.000000","no_tax_roi":"2.125000000000","tax_adjusted_roi":"1.500000000000","matched_full_lift":"2.125000000000","coverage_hit_rate":".8","ticket_hit_rate":".2","capital_utilization_vs_full":".16","seed_mean_drawdown_no_tax_yuan":"-2","seed_gross_weighted_mean_issue_hhi":".3"},
        {"selector_id":"S0","weight_source":"Q_WEIGHT","mechanism":"WOR_DISTINCT","cap":"NA","M":"16","seed":"ENSEMBLE_100","seed_count":"100","seed_scope":"ENSEMBLE_100","stake_yuan":"1600.000000","gross_pre_tax_yuan":"8000.000000","tax_yuan":"20.000000","no_tax_roi":"-.5","tax_adjusted_roi":"-.5125","matched_full_lift":"-.5","coverage_hit_rate":".7","ticket_hit_rate":".15","capital_utilization_vs_full":".16","seed_mean_drawdown_no_tax_yuan":"-4","seed_gross_weighted_mean_issue_hhi":".4"},
    ]
    with gzip.open(screen / "ensemble_metrics.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    selector = {"selector_id":"S0","family":"NO_GATE","gate_id":"G0","top_k":"4","lowp_source":"NONE","lowp_threshold":"","ranker":"Q"}
    census = [{"selector_id":"S0","issue_instance":"I1","status":"SETTLED"},{"selector_id":"S0","issue_instance":"I2","status":"NO_BET"},{"selector_id":"S0","issue_instance":"I3","status":"UNAVAILABLE_CANONICAL_OUTCOME"}]
    POST.write_full_atlas_chart_sources(screen, out, [selector], census)
    with gzip.open(out / "chart_source_full_dense_m_curve_v3r1.csv.gz", "rt", newline="") as f: dense = list(csv.DictReader(f))
    assert {r["mechanism"] for r in dense} == {"FULL_ENUMERATED", "RESIDUAL_SYSTEMATIC", "WOR_DISTINCT"}
    assert {"family", "gate_id", "top_k", "lowp_source", "ranker", "coverage_hit_rate", "ticket_hit_rate"} <= set(dense[0])
    with gzip.open(out / "chart_source_selector_full_surface_v3r1.csv.gz", "rt", newline="") as f: full = next(csv.DictReader(f))
    assert full["settled_policy_count"] == "1" and full["no_bet_policy_count"] == "1" and full["unavailable_policy_count"] == "1"
    with gzip.open(out / "chart_source_capital_risk_tax_hit_v3r1.csv.gz", "rt", newline="") as f: capital = list(csv.DictReader(f))
    residual = next(r for r in capital if r["mechanism"] == "RESIDUAL_SYSTEMATIC")
    assert residual["no_tax_roi"] == "2.125000000000" and residual["tax_line_exposure_yuan"] == "50.000000"
    assert residual["gross_return_retention_vs_matched_full"] == "0.500000000000"
    assert residual["taxable_ticket_metric_status"] == "NOT_RETAINED_IN_SCREEN_LEDGER"
    ensemble = next(r for r in capital if r["mechanism"] == "WOR_DISTINCT")
    assert ensemble["gross_retention_normalization_scale"] == "100"
    assert ensemble["normalized_stake_yuan"] == "16.000000"
    assert ensemble["normalized_gross_pre_tax_yuan"] == "80.000000"
    assert ensemble["gross_return_retention_vs_matched_full"] == "0.800000000000"
    # The pooled ¥20 tax represents 100 seed ledgers: raw tax-line exposure
    # is ¥100, but the renderable per-seed comparable exposure is ¥1.
    assert ensemble["tax_line_exposure_yuan"] == "100.000000"
    assert ensemble["normalized_tax_line_exposure_yuan"] == "1.000000"
    shutil.rmtree(root)


def test_execution_provenance_binds_screen_and_postscreen_identities():
    root = ROOT / ".scratch" / "bj167_execution_provenance_fixture"
    if root.exists(): shutil.rmtree(root)
    screen = root / "screen"; out = root / "out"; screen.mkdir(parents=True); out.mkdir()
    (screen / "SHA256SUMS.json").write_text("{}\n"); (screen / "CONTENT_IDENTITY.json").write_text("{}\n")
    snap = POST.execution_snapshot()
    POST.write_execution_provenance(out, screen, snap, snap)
    data = json.loads((out / "execution_provenance.json").read_text())
    assert data["screening_execution"]["git_head"] == POST.SCREENING_EXECUTION_HEAD
    assert data["screening_execution"]["runner_sha256"] == POST.SCREENING_RUNNER_SHA256
    assert data["postscreen_execution_start"] == data["postscreen_execution_end"] == snap
    shutil.rmtree(root)
