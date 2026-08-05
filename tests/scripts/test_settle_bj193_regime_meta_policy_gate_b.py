from __future__ import annotations

import importlib.util
import ctypes
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


C = load("bj193_core_test", ROOT / "scripts" / "bj193_gate_b_core.py")
R = load(
    "bj193_runner_test",
    ROOT / "scripts" / "settle_bj193_regime_meta_policy_gate_b.py",
)
V2 = load("bj193_chain_v2_test", ROOT / "scripts" / "bj193_chain_gate_b_v2.py")


def test_path_receipts_use_deterministic_union_schema(tmp_path):
    store = SimpleNamespace(
        action_rows=[{"interface_action_key": "STATIC"}],
        issues=[
            {
                "issue": "1",
                "issue_instance": "1@TEST_2021",
                "feature_cutoff_ts": "2021-01-01T00:00:00Z",
            }
        ],
    )

    def make_path(stage, model_receipt, screen_receipt):
        return V2.StagePath(
            stage=stage,
            choices=np.asarray([0], dtype=np.int32),
            model_by_issue=["MODEL"],
            fallback_by_issue=np.asarray([False]),
            model_receipts=[model_receipt],
            screen_receipts=[screen_receipt],
        )

    paths = {
        "stage1": (
            make_path(
                "STAGE_1_SELECTION",
                {"outer_fold": "A", "selected_family": "PRIOR_ONLY_FIXED"},
                {"outer_fold": "A", "screen_phase": "OUTER_TRAIN"},
            ),
            store,
        ),
        "stage2": (
            make_path(
                "STAGE_2_DIRECTION",
                {
                    "outer_fold": "B",
                    "selected_family": "SHALLOW_TREE",
                    "inner_train_issue_count": 20,
                    "inner_validation_issue_count": 5,
                },
                {
                    "outer_fold": "B",
                    "screen_phase": "INNER_TRAIN",
                    "eligible_action_count": 3,
                },
            ),
            store,
        ),
        "stage3": (
            make_path(
                "STAGE_3_BET",
                {
                    "outer_fold": "C",
                    "selected_family": "NEAREST_HISTORICAL_REGIME",
                    "inner_screen_action_count": 3,
                    "validation_pre_tax_roi": 0.125,
                },
                {"outer_fold": "C", "screen_phase": "INNER_VALIDATION"},
            ),
            store,
        ),
    }
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    R._write_path_receipts(first, paths)
    R._write_path_receipts(second, paths)

    model_rows = R.read_csv(first / "stage_model_receipts.csv")
    assert list(model_rows[0]) == [
        "path_name",
        "inner_screen_action_count",
        "inner_train_issue_count",
        "inner_validation_issue_count",
        "outer_fold",
        "selected_family",
        "validation_pre_tax_roi",
    ]
    assert model_rows[0]["inner_train_issue_count"] == ""
    assert model_rows[2]["validation_pre_tax_roi"] == "0.125"
    screen_rows = R.read_csv(first / "stage_screen_receipts.csv.gz")
    assert list(screen_rows[0]) == [
        "path_name",
        "eligible_action_count",
        "outer_fold",
        "screen_phase",
    ]
    assert screen_rows[0]["eligible_action_count"] == ""
    assert screen_rows[1]["eligible_action_count"] == "3"
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()
    assert R.receipt_fields(list(reversed(model_rows))) == list(model_rows[0])


def test_selector_screen_uses_roi_support_stake_and_lexical_ties():
    selector = ["B", "A", "C", "D"]
    stake = np.full((4, 20), 2.0)
    net = np.zeros_like(stake)
    net[2] = 1.0
    stake[3, 19] = 0.0
    chosen = C.selector_rank(net, stake, selector, list(range(20)), 4)
    assert chosen == [2, 1, 0, 3]
    # Below 20 active rows is fail-closed even if the observed ROI is huge.
    net[3] = 1_000.0
    assert C.selector_rank(net, stake, selector, list(range(20)), 1) == [2]


def test_seed_economics_are_mean_not_summed_exposure():
    values = np.array([8000.0, 100.0])
    assert np.array_equal(
        C.normalize_seed_aggregated(values, "ENSEMBLE_100"),
        np.array([80.0, 1.0]),
    )


def test_prior_prediction_is_aggregate_net_over_stake_not_mean_issue_roi():
    utility = np.asarray([[1.0], [-1.0]] * 10)
    stake = np.asarray([[100.0], [1.0]] * 10)
    active = np.ones_like(utility, dtype=bool)
    predicted = C.prior_predictions(
        utility, active, query_count=1, train_weight=stake
    )
    expected = (10 * 100.0 - 10 * 1.0) / (10 * 100.0 + 10 * 1.0)
    assert abs(float(predicted[0, 0]) - expected) < 1e-15
    values = np.array([8000.0, 100.0])
    assert np.array_equal(
        C.normalize_seed_aggregated(values, "DETERMINISTIC"), values
    )


def test_train_only_transform_does_not_refit_on_query_extreme():
    train = np.arange(40, dtype=float).reshape(20, 2)
    query = np.array([[1_000_000.0, np.nan]])
    transform = C.FeatureTransform.fit(train)
    transformed = transform.apply(query)
    assert transformed.shape == (1, 4)
    assert transformed[0, 1] <= (
        transform.high[1] - transform.means[1]
    ) / transform.scales[1] + 1e-12
    assert transformed[0, 3] == 1.0


def test_numeric_projection_interleaves_each_missing_indicator():
    train = np.asarray([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]])
    transformed = C.FeatureTransform.fit(train).apply(
        np.asarray([[np.nan, 20.0]])
    )
    assert transformed.shape == (1, 4)
    assert transformed[0, 0] == 0.0
    assert transformed[0, 1] == 1.0
    assert transformed[0, 3] == 0.0


def test_model_families_are_deterministic_and_min_support_is_enforced():
    x = np.column_stack([np.linspace(-1, 1, 30), np.arange(30) % 3])
    y = np.column_stack([x[:, 0] * 0.5, np.ones(30)])
    active = np.ones_like(y, dtype=bool)
    active[19:, 1] = False
    groups = {"POOL_VALUE": [0], "UNCERTAINTY_DIVERGENCE": [1]}
    cases = [
        ("PRIOR_ONLY_FIXED", {}),
        ("BINNED_REGIME_RULE", {"quantile_bins": 3, "min_leaf": 10}),
        ("SHALLOW_TREE", {"max_depth": 2, "min_leaf": 10}),
        (
            "MONOTONE_REGULARIZED_SCORE",
            {"monotone_feature_group": "POOL_VALUE", "l2": 0.1},
        ),
        ("NEAREST_HISTORICAL_REGIME", {"k": 5, "weighting": "UNIFORM"}),
    ]
    for family, parameters in cases:
        one = C.predict_model(family, parameters, x, x[:3], y, active, groups)
        two = C.predict_model(family, parameters, x, x[:3], y, active, groups)
        assert np.array_equal(one, two, equal_nan=True)
        assert np.isfinite(one[:, 0]).all()
        assert np.isnan(one[:, 1]).all()


def test_monotone_score_projects_frozen_positive_and_negative_signs():
    # Outcome utility is intentionally anti-correlated with POOL_VALUE and
    # positively correlated with UNCERTAINTY.  The frozen estimator must not
    # express either forbidden direction.
    pool = np.linspace(-2.0, 2.0, 40)
    uncertainty = np.linspace(2.0, -2.0, 40)
    nuisance = np.sin(np.arange(40, dtype=float))
    x = np.column_stack([pool, uncertainty, nuisance])
    y = (-3.0 * pool + 4.0 * uncertainty + nuisance)[:, None]
    active = np.ones_like(y, dtype=bool)
    prediction = C.ridge_score_predictions(
        x,
        np.asarray([[2.0, -2.0, 0.0], [-2.0, 2.0, 0.0]]),
        y,
        active,
        positive_indices=[0],
        negative_indices=[1],
        l2=0.01,
    )
    # Both prohibited slopes are projected to zero; only the unconstrained
    # nuisance/intercept can remain, so swapping the two constrained fields
    # cannot change the prediction.
    assert abs(float(prediction[0, 0] - prediction[1, 0])) < 1e-10


def test_monotone_score_keeps_allowed_directions():
    pool = np.linspace(-2.0, 2.0, 40)
    uncertainty = np.linspace(2.0, -2.0, 40)
    x = np.column_stack([pool, uncertainty])
    y = (2.0 * pool - 3.0 * uncertainty)[:, None]
    active = np.ones_like(y, dtype=bool)
    prediction = C.ridge_score_predictions(
        x,
        np.asarray([[2.0, -2.0], [-2.0, 2.0]]),
        y,
        active,
        positive_indices=[0],
        negative_indices=[1],
        l2=0.01,
    )
    assert prediction[0, 0] > prediction[1, 0]


def test_monotone_grid_identity_label_does_not_disable_joint_constraints():
    train_x = np.asarray(
        [[-1.0, -1.0], [0.0, 0.0], [1.0, 1.0]] * 10,
        dtype=np.float64,
    )
    query_x = np.asarray([[2.0, 2.0]], dtype=np.float64)
    train_y = (train_x[:, 0] - train_x[:, 1])[:, None]
    active = np.ones_like(train_y, dtype=bool)
    groups = {"POOL_VALUE": [0], "UNCERTAINTY_DIVERGENCE": [1]}
    for label in ("POOL_VALUE", "UNCERTAINTY_DIVERGENCE"):
        predicted = C.predict_model(
            "MONOTONE_REGULARIZED_SCORE",
            {"l2": 0.1, "monotone_feature_group": label},
            train_x,
            query_x,
            train_y,
            active,
            groups,
        )
        assert predicted.shape == (1, 1)
        assert np.isfinite(predicted[0, 0])


def test_canonical_status_fails_closed_across_split_instances():
    census = [
        {
            "selector_id": "S",
            "issue": "23011",
            "issue_instance": "23011@A",
            "selected_identity_count": "1",
        },
        {
            "selector_id": "S",
            "issue": "23011",
            "issue_instance": "23011@B",
            "selected_identity_count": "1",
        },
        {
            "selector_id": "S",
            "issue": "20031",
            "issue_instance": "20031@A",
            "selected_identity_count": "0",
        },
    ]
    statuses = {
        (0, "23011@A"): "SETTLED",
        (0, "23011@B"): "UNAVAILABLE_CANONICAL_OUTCOME",
        (0, "20031@A"): "NO_BET_FROZEN",
    }
    actual = R.atlas_canonical_status(census, statuses, {"S": 0})
    assert actual[(0, "23011")] == "UNAVAILABLE"
    assert actual[(0, "20031")] == "NO_BET"


def test_holding_calendar_and_active_sequences_are_distinct():
    rows = [
        {"net": -2.0, "stake": 2.0, "gross": 0.0},
        {"net": 0.0, "stake": 0.0, "gross": 0.0},
        {"net": -2.0, "stake": 2.0, "gross": 0.0},
        {"net": 8.0, "stake": 2.0, "gross": 10.0},
    ]
    metrics = C.holding_metrics(rows, reference_capital=100.0)
    assert metrics["max_negative_pnl_streak_calendar"] == 1
    assert metrics["max_negative_pnl_streak_active"] == 2
    assert metrics["max_miss_streak_calendar"] == 1
    assert metrics["max_miss_streak_active"] == 2
    assert metrics["roi"] == 2 / 3


def test_native_wrapper_compiles_without_changing_frozen_allocator(tmp_path):
    before = R.sha(R.FROZEN_ALLOCATOR)
    library, binary = R.compile_replay(tmp_path)
    assert library is not None
    assert binary.exists()
    assert R.sha(R.FROZEN_ALLOCATOR) == before == R.EXPECTED_ALLOCATOR_SHA256


def test_native_production_path_captures_issue_and_exact_seed_pool(tmp_path):
    lib, _binary = R.compile_replay(tmp_path)
    total = R.SCIENCE_CELLS
    tmp = [np.zeros(total) for _ in range(6)]
    totals = [np.zeros(total) for _ in range(7)]
    mark = np.zeros(total, dtype=np.uint8)
    touched = np.zeros(total, dtype=np.int32)
    cumulative = np.zeros(total)
    peak = np.zeros(total)
    drawdown = np.zeros(total)
    miss = np.zeros(total, dtype=np.int32)
    longest = np.zeros(total, dtype=np.int32)
    year_net = np.zeros((total, 1))
    year_stake = np.zeros((total, 1))
    fold_net = np.zeros((total, 1))
    fold_stake = np.zeros((total, 1))
    largest = np.full(total, -np.inf)
    largest_stake = np.zeros(total)
    largest_issue = np.full(total, -1, dtype=np.int32)
    full_net = np.zeros((1, 1))
    full_stake = np.zeros((1, 1))
    issue = [np.zeros((total, 1)) for _ in range(6)]
    seed_net = np.zeros((1, 6, 2, 20, 100, 1))
    seed_stake = np.zeros_like(seed_net)
    lib.bj167_scientific_set_buffers(
        *(R.np_ptr(value) for value in tmp),
        R.np_ptr(mark, ctypes.c_ubyte), R.np_ptr(touched, ctypes.c_int),
        *(R.np_ptr(value) for value in totals),
        R.np_ptr(cumulative), R.np_ptr(peak), R.np_ptr(drawdown),
        R.np_ptr(miss, ctypes.c_int), R.np_ptr(longest, ctypes.c_int),
        R.np_ptr(year_net), R.np_ptr(year_stake),
        R.np_ptr(fold_net), R.np_ptr(fold_stake),
        R.np_ptr(largest), R.np_ptr(largest_stake),
        R.np_ptr(largest_issue, ctypes.c_int),
        R.np_ptr(full_net), R.np_ptr(full_stake), 1, 1, 1,
    )
    lib.bj193_set_seed_fold_buffers(
        R.np_ptr(seed_net), R.np_ptr(seed_stake), 1, 1
    )
    lib.bj193_set_action_issue_buffers(*(R.np_ptr(value) for value in issue))
    role = np.asarray(
        [
            0.51, 0.29, 0.20, 0.42, 0.31, 0.27, 0.48, 0.33, 0.19,
            0.38, 0.35, 0.27, 0.46, 0.28, 0.26, 0.41, 0.32, 0.27,
            0.44, 0.30, 0.26,
        ],
        dtype=float,
    )
    occurrence = np.asarray([0], dtype=np.int32)
    lib.bj193_begin_issue(0, 0, 0)
    lib.bj193_process_source(
        R.np_ptr(role), 0, b"fixture", 100.0,
        R.np_ptr(occurrence, ctypes.c_int), 1, 0,
    )
    lib.bj167_scientific_add_structural(0, 0, 0, 2, 1, 2, 100.0)
    lib.bj193_end_issue()
    assert issue[0][0, 0] == seed_net[0, 0, 0, 0, :, 0].sum()
    assert issue[1][0, 0] == seed_stake[0, 0, 0, 0, :, 0].sum()
    # The frozen M2187 WOR profile equals 100 identical FULL exposures.
    assert issue[1][39, 0] / 100 == issue[1][960, 0]
    assert issue[2][39, 0] / 100 == issue[2][960, 0]


def test_v2_gate_a_layers_and_stage1_static_store_are_bound():
    payload = R.verify_gate_a()
    assert len([name for name in payload if name.startswith("v2::")]) == 35
    assert len([name for name in payload if name.startswith("v2.1::")]) == 16
    store = V2.build_stage1_store()
    assert store.status.shape == (2469, 344)
    assert int(np.count_nonzero(store.status == V2.STATUS_ACTIVE)) == 513_697
    assert int(np.count_nonzero(store.status == V2.STATUS_UNAVAILABLE)) == 43_169
    assert len(store.supports) == 556_866
    assert V2.stage1_store_identity(store) == (
        "ad04f4777f3fd223e60ba043135d6b0b8d74d22eb41e275a9bdc58dc8965413f"
    )


def test_stage2_adapter_is_conditional_on_exact_stage1_support():
    store = V2.build_stage1_store()
    fallback = next(
        index for index, row in enumerate(store.action_rows)
        if row["upstream_issue"] == "134"
        and row["source_identity"] == "MARKET_BEST_FULL"
    )
    path = V2.StagePath(
        "STAGE_1_SELECTION",
        np.full(len(store.issues), fallback, dtype=np.int32),
        ["STATIC"] * len(store.issues),
        np.ones(len(store.issues), dtype=bool), [], [],
    )
    decisions = V2.build_stage1_decisions(store, path)
    decision = next(value for value in decisions if value.supports)
    estimators = V2._load_needed_estimators([decision])
    adapter_sha = V2.hashlib.sha256(
        (V2.GATE_A_V2 / "conditional_chain_adapter.py").read_bytes()
    ).hexdigest()
    actions = V2.load_stage_catalog(2)
    allow = next(
        row for row in actions
        if row["scientific_role"] == "STATIC_ALLOW_ALL_OUTCOME_CODES_CONTROL"
    )
    allow_rows = V2._apply_stage2_action(
        allow, decision, estimators, adapter_sha
    )
    assert [row.support.ordered_match_ids for row in allow_rows] == [
        row.ordered_match_ids for row in decision.supports
    ]
    assert all(row.output["ticket_support_size"] == 2187 for row in allow_rows)
    active = None
    for action in actions:
        rows = V2._apply_stage2_action(action, decision, estimators, adapter_sha)
        if rows and all(row.output["status"] == "ACTIVE" for row in rows):
            if action["scientific_role"] != "STATIC_ALLOW_ALL_OUTCOME_CODES_CONTROL":
                active = rows
                break
    assert active is not None
    assert all(row.output["ticket_support_size"] == 1458 for row in active)
    assert all(
        row.output["ordered_match_ids"] == list(row.support.ordered_match_ids)
        for row in active
    )


def test_mixed_feature_encoder_uses_train_only_lexical_unknown_last():
    projections = [
        {"projection_field": "x", "source_field": "x", "source_scope": "COMMON_X_I", "dtype": "FLOAT64"},
        {"projection_field": "flag", "source_field": "flag", "source_scope": "STAGE1", "dtype": "BOOLEAN"},
        {"projection_field": "kind", "source_field": "kind", "source_scope": "STAGE1", "dtype": "CATEGORY"},
    ]
    rows = [
        {"x": 1.0, "flag": True, "kind": "B"},
        {"x": 2.0, "flag": False, "kind": "A"},
        {"x": None, "flag": None, "kind": "UNSEEN"},
    ]
    encoder = V2.MixedFeatureEncoder.fit(projections, rows, [0, 1])
    encoded = encoder.apply(rows, [2])
    # x,value+missing; flag,value+missing; A,B,__UNKNOWN__.
    assert encoded.shape == (1, 7)
    assert encoded[0, 1] == 1.0
    assert encoded[0, 3] == 1.0
    assert np.array_equal(encoded[0, 4:], [0.0, 0.0, 1.0])


def test_stage3_native_profiles_exact_action_signatures_and_seed_mean(monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    rows = V2.load_stage_catalog(3)
    wanted = {
        ("WR_DUPLICATE_STAKE", "16", "NA"),
        ("WOR_DISTINCT", "16", "NA"),
        ("RESIDUAL_SYSTEMATIC", "64", "NA"),
        ("CAPPED_REPEAT", "64", "2"),
        ("DETERMINISTIC_TOP_MASS", "64", "NA"),
        ("FULL_ENUMERATED", "2187", "NA"),
        ("P_MIN_GLOBAL_DELETE", "NA", "NA"),
        ("Q_MIN_GLOBAL_DELETE", "NA", "NA"),
    }
    actions = []
    for row in rows:
        parameters = json.loads(row["parameters_json"])
        key = (parameters["mechanism"], parameters["M"], parameters["cap"])
        if key in wanted and parameters["weight_source"] in {"Q_WEIGHT", "NA"}:
            actions.append(row)
            wanted.remove(key)
    assert not wanted and len(actions) == 8
    engine = V2.load_module(
        "bj193_allocator_test", V2.GATE_A_V2 / "bj145_allocation_engine.py"
    )
    weights = np.asarray(engine.golden_weights(), dtype=np.float64)
    matrix = np.ascontiguousarray(
        np.tile(weights, (len(V2.STAGE3_WEIGHT_SOURCES), 1))
    )
    source, mechanism, requested_m, caps, signatures, encoded = (
        V2._stage3_native_action_arrays(actions, "26080", "a" * 64, "b" * 64)
    )
    status = np.zeros(len(actions), dtype=np.uint8)
    output = {
        name: np.zeros(len(actions), dtype=np.float64)
        for name in ("gross", "stake", "tax", "net", "hit")
    }
    native = V2._compile_stage3_native()
    native.bj193_chain_profile_actions(
        V2._np_pointer(matrix, ctypes.c_double),
        len(V2.STAGE3_WEIGHT_SOURCES), V2.FULL_TICKETS, 0, 100.0,
        V2._np_pointer(source, ctypes.c_int),
        V2._np_pointer(mechanism, ctypes.c_int),
        V2._np_pointer(requested_m, ctypes.c_int),
        V2._np_pointer(caps, ctypes.c_int), encoded, len(actions),
        1, 972, 0, 1458,
        V2._np_pointer(status, ctypes.c_ubyte),
        *(V2._np_pointer(output[name], ctypes.c_double) for name in (
            "gross", "stake", "tax", "net", "hit"
        )),
    )
    assert np.all(status == V2.STATUS_ACTIVE)
    for index, row in enumerate(actions):
        parameters = json.loads(row["parameters_json"])
        mechanism_name = parameters["mechanism"]
        if mechanism_name == "P_MIN_GLOBAL_DELETE":
            assert output["hit"][index] == 1.0
            assert output["stake"][index] == 1944.0
            assert output["gross"][index] == 100.0
            continue
        if mechanism_name == "Q_MIN_GLOBAL_DELETE":
            assert output["hit"][index] == 0.0
            assert output["stake"][index] == 2916.0
            assert output["gross"][index] == 0.0
            continue
        if mechanism_name == "FULL_ENUMERATED":
            expected_counts = [tuple(1 for _ in weights)]
        else:
            seeds = (
                [str(value) for value in range(137001, 137101)]
                if mechanism_name in {"WR_DUPLICATE_STAKE", "WOR_DISTINCT"}
                else ["NA"]
            )
            expected_counts = [
                engine.allocate(
                    mechanism_name, weights, int(parameters["M"]), seed=seed,
                    identity_signature=signatures[index].decode(),
                    cap=None if parameters["cap"] == "NA" else int(parameters["cap"]),
                )
                for seed in seeds
            ]
        expected_hit = sum(values[0] for values in expected_counts) / len(expected_counts)
        expected_stake = 2 * sum(sum(values) for values in expected_counts) / len(expected_counts)
        assert abs(output["hit"][index] - expected_hit) < 1e-12
        assert abs(output["stake"][index] - expected_stake) < 1e-12
        assert abs(output["gross"][index] - 100.0 * expected_hit) < 1e-10
        assert output["tax"][index] == 0.0


def test_stage3_native_seed_diagnostic_reconciles_frozen_action_mean(
    monkeypatch,
):
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    action = next(
        row
        for row in V2.load_stage_catalog(3)
        if json.loads(row["parameters_json"])["mechanism"]
        == "WR_DUPLICATE_STAKE"
        and json.loads(row["parameters_json"])["weight_source"] == "Q_WEIGHT"
        and json.loads(row["parameters_json"])["M"] == "16"
    )
    engine = V2.load_module(
        "bj193_seed_diag_allocator_test",
        V2.GATE_A_V2 / "bj145_allocation_engine.py",
    )
    weights = np.asarray(engine.golden_weights(), dtype=np.float64)
    matrix = np.ascontiguousarray(
        np.tile(weights, (len(V2.STAGE3_WEIGHT_SOURCES), 1))
    )
    source, mechanism, requested_m, caps, signatures, encoded = (
        V2._stage3_native_action_arrays([action], "26080", "a" * 64, "b" * 64)
    )
    aggregate = {
        name: np.zeros(1, dtype=np.float64)
        for name in ("gross", "stake", "tax", "net", "hit")
    }
    status = np.zeros(1, dtype=np.uint8)
    native = V2._compile_stage3_native()
    native.bj193_chain_profile_actions(
        V2._np_pointer(matrix, ctypes.c_double),
        len(V2.STAGE3_WEIGHT_SOURCES),
        V2.FULL_TICKETS,
        0,
        100.0,
        V2._np_pointer(source, ctypes.c_int),
        V2._np_pointer(mechanism, ctypes.c_int),
        V2._np_pointer(requested_m, ctypes.c_int),
        V2._np_pointer(caps, ctypes.c_int),
        encoded,
        1,
        0,
        0,
        0,
        0,
        V2._np_pointer(status, ctypes.c_ubyte),
        *(
            V2._np_pointer(aggregate[name], ctypes.c_double)
            for name in ("gross", "stake", "tax", "net", "hit")
        ),
    )
    seed = {
        name: np.zeros(100, dtype=np.float64)
        for name in ("gross", "stake", "tax", "net", "hit")
    }
    native.bj193_chain_profile_seed_action(
        V2._np_pointer(matrix[int(source[0])], ctypes.c_double),
        V2.FULL_TICKETS,
        0,
        100.0,
        int(mechanism[0]),
        int(requested_m[0]),
        signatures[0],
        *(
            V2._np_pointer(seed[name], ctypes.c_double)
            for name in ("gross", "stake", "tax", "net", "hit")
        ),
    )
    assert status[0] == V2.STATUS_ACTIVE
    for name in seed:
        assert abs(float(seed[name].mean()) - aggregate[name][0]) < 1e-12
    assert np.all(seed["stake"] == 32.0)


def test_structural_delete_fails_closed_without_all_seven_role_rows():
    support = V2.Support(
        "26080", "OOS_2026", "2026", "identity",
        tuple(str(value) for value in range(1, 8)), "portfolio",
    )
    assert V2._original_structural_delete_truth(support, {}, 0) is None


def test_v21_structural_composition_preserves_same_and_distinct_ticket_counts():
    golden = json.loads(
        (
            V2.GATE_A_V21 / "structural_delete_golden_vectors.json"
        ).read_text()
    )
    anchor = golden["native_137_anchor"]
    support = V2.Support(
        str(anchor["issue"]),
        str(anchor["fold"]),
        "2019",
        "v21-structural-fixture",
        tuple(str(value) for value in anchor["ordered_match_ids"]),
        str(anchor["portfolio_id"]),
    )
    stage1 = V2.Stage1Decision(
        0,
        0,
        (support,),
        {"output_sha256": "1" * 64},
    )
    actions = [
        row
        for row in V2.load_stage_catalog(3)
        if json.loads(row["parameters_json"])["mechanism"]
        in {"P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE"}
    ]
    registry = V2._load_structural_delete_registry([stage1])
    p_replay = anchor["p_replay"]
    p_leg = int(p_replay["delete_leg_index_zero_based"])
    p_code = int(p_replay["delete_code_index_zero_based"])

    def profile(removed_leg: int, removed_code: int):
        per_match = []
        for index, match_id in enumerate(support.ordered_match_ids):
            weights = ["0.400000000000", "0.350000000000", "0.250000000000"]
            if index == removed_leg:
                weights[removed_code] = "0"
            per_match.append(
                {
                    "match_id": match_id,
                    "direction_weight_3_1_0": weights,
                }
            )
        direction = V2.DirectionSupport(
            support,
            {"status": "ACTIVE", "per_match": per_match},
        )
        stage2 = V2.Stage2Decision(
            0,
            0,
            (direction,),
            {"output_sha256": "2" * 64},
        )
        return V2._compose_structural_stage3_profiles(
            actions, direction, stage1, stage2, registry, 0
        )

    same = profile(p_leg, p_code)
    assert same[1] == 1458
    assert same[4]["P_MIN_GLOBAL_DELETE"]["reason_code"] == (
        "STRUCTURAL_DELETE_ALREADY_ABSENT"
    )
    distinct = profile((p_leg + 1) % 7, (p_code + 1) % 3)
    assert distinct[1] == 972
    assert distinct[4]["P_MIN_GLOBAL_DELETE"]["reason_code"] == (
        "STRUCTURAL_DELETE_ADDITIONAL_ZERO_MASK"
    )
    assert distinct[4]["P_MIN_GLOBAL_DELETE"][
        "stage3_replay_signature_sha256"
    ] == V2._direction_adapter().stage3_replay_signature(
        issue=support.issue,
        stage1_output_sha256="1" * 64,
        stage2_output_sha256="2" * 64,
        derived_stage3_action_sha256=json.loads(
            next(
                row["parameters_json"]
                for row in actions
                if json.loads(row["parameters_json"])["mechanism"]
                == "P_MIN_GLOBAL_DELETE"
            )
        )["derived_bet_action_sha256"],
    )


def test_v21_effective_compatibility_replaces_only_structural_action_class():
    effective = V2._stage3_effective_class_keys()
    compatibility = V2._stage3_compatibility()
    actions = V2.load_stage_catalog(3)
    changed = []
    for action in actions:
        parameters = json.loads(action["parameters_json"])
        original = parameters["compatibility_class_key"]
        replacement = effective[action["interface_action_key"]]
        if replacement != original:
            changed.append((parameters["mechanism"], replacement))
    assert {mechanism for mechanism, _key in changed} == {
        "P_MIN_GLOBAL_DELETE",
        "Q_MIN_GLOBAL_DELETE",
    }
    assert len({key for _mechanism, key in changed}) == 1
    structural_key = changed[0][1]
    rows = [
        row
        for (stage1_key, class_key), row in compatibility.items()
        if class_key == structural_key
    ]
    assert len(rows) == 2469
    assert {
        row["compatibility_status"]
        for row in rows
        if row["stage1_upstream_issue"] in {"127", "134"}
    } == {"COMPATIBLE"}
    assert "COMPATIBLE" not in {
        row["compatibility_status"]
        for row in rows
        if row["stage1_upstream_issue"] == "190"
    }


def test_policy_rows_common_support_and_oracle_use_frozen_causal_screen():
    action_rows = [
        {
            "interface_action_key": "A_STATIC",
            "upstream_issue": "134",
            "source_identity": "MARKET_BEST_FULL",
        },
        {
            "interface_action_key": "B_CHALLENGER",
            "upstream_issue": "127",
            "source_identity": "B",
        },
    ]
    issues = [
        {
            "issue": "1",
            "year": "2021",
            "outer_fold": "TEST_2021",
            "issue_instance": "1@TEST_2021",
        },
        {
            "issue": "2",
            "year": "2021",
            "outer_fold": "TEST_2021",
            "issue_instance": "2@TEST_2021",
        },
    ]
    status = np.asarray(
        [
            [V2.STATUS_ACTIVE, V2.STATUS_ACTIVE],
            [V2.STATUS_ACTIVE, V2.STATUS_NO_BET],
        ],
        dtype=np.uint8,
    )
    stake = np.asarray([[100.0, 100.0], [50.0, 0.0]])
    net = np.asarray([[10.0, -10.0], [10.0, 0.0]])
    gross = stake + net
    zeros = np.zeros_like(stake)
    store = V2.StageStore(
        action_rows=action_rows,
        issues=issues,
        supports={},
        status=status,
        stake=stake,
        gross=gross,
        tax=zeros.copy(),
        net=net,
        hit=zeros.copy(),
    )
    static = V2.static_stage1_path(store)
    assert static.choices.tolist() == [0, 0]
    causal = V2.StagePath(
        stage="STAGE_1_SELECTION",
        choices=np.asarray([0, 1], dtype=np.int32),
        model_by_issue=["MODEL", "MODEL"],
        fallback_by_issue=np.zeros(2, dtype=bool),
        model_receipts=[],
        screen_receipts=[
            {
                "outer_fold": "TEST_2021",
                "screen_phase": "OUTER_TRAIN",
                "action_identity": "A_STATIC",
            },
            {
                "outer_fold": "TEST_2021",
                "screen_phase": "OUTER_TRAIN",
                "action_identity": "B_CHALLENGER",
            },
        ],
    )
    oracle = V2.oracle_path_on_causal_screen(store, causal)
    assert oracle.choices.tolist() == [1, 0]
    static_rows = V2.issue_policy_rows("STATIC", store, static)
    causal_rows = V2.issue_policy_rows("CAUSAL", store, causal)
    assert causal_rows[1]["status"] == "NO_BET"
    assert causal_rows[1]["stake_yuan"] == 0.0
    assert V2.strict_common_issue_indices(
        {"STATIC": static_rows, "CAUSAL": causal_rows}
    ) == [0]


def test_prior_only_paths_use_outer_train_without_validation_selection(
    monkeypatch,
):
    action_rows = [
        {
            "interface_action_key": "STATIC",
            "upstream_issue": "134",
            "source_identity": "MARKET_BEST_FULL",
        }
    ]
    issues = [
        {
            "issue": "1",
            "year": "2020",
            "outer_fold": "TRAIN",
            "issue_instance": "1@TRAIN",
            "feature_cutoff_ts": "2020-01-01T00:00:00Z",
        },
        {
            "issue": "2",
            "year": "2021",
            "outer_fold": "TEST_2021",
            "issue_instance": "2@TEST_2021",
            "feature_cutoff_ts": "2021-01-01T00:00:00Z",
        },
    ]
    one = np.ones((1, 2), dtype=float)
    stage1 = V2.StageStore(
        action_rows=action_rows,
        issues=issues,
        supports={},
        status=np.full((1, 2), V2.STATUS_ACTIVE, dtype=np.uint8),
        stake=one.copy(),
        gross=one.copy(),
        tax=np.zeros_like(one),
        net=np.zeros_like(one),
        hit=np.zeros_like(one),
    )
    conditional = V2.ConditionalStore(
        **stage1.__dict__,
        conditional_supports={},
        fallback_index=0,
        comparator_net=np.zeros(2),
        comparator_stake=np.ones(2),
        utility=np.zeros((1, 2)),
        utility_active=np.ones((1, 2), dtype=bool),
        target_mode="ABSOLUTE_UTILITY",
    )
    monkeypatch.setattr(V2, "_stage1_raw_features", lambda _issues: ([{}] * 2, {}))
    monkeypatch.setattr(V2, "_action_screen", lambda *_args: [0])
    monkeypatch.setattr(
        V2,
        "_stage_predictions",
        lambda *_args: (np.zeros((1, 1)), np.zeros((1, 1))),
    )
    monkeypatch.setattr(
        V2,
        "_choose_stage_actions",
        lambda _store, _actions, query, *_args: ([0] * len(query), [True] * len(query)),
    )
    monkeypatch.setattr(V2, "_conditional_screen", lambda *_args: [0])
    monkeypatch.setattr(
        V2,
        "_conditional_predictions",
        lambda *_args: (np.zeros((1, 1)), np.zeros((1, 1))),
    )
    monkeypatch.setattr(
        V2,
        "_conditional_choice",
        lambda _store, _actions, query, *_args: ([0] * len(query), [True] * len(query)),
    )
    monkeypatch.setattr(
        V2,
        "_validation_key",
        lambda *_args: (_ for _ in ()).throw(AssertionError("validation used")),
    )
    monkeypatch.setattr(
        V2,
        "_conditional_validation_key",
        lambda *_args: (_ for _ in ()).throw(AssertionError("validation used")),
    )
    stage1_path = V2.build_prior_only_stage1_path(stage1)
    stage2_path = V2._build_prior_only_conditional_path(
        conditional, "STAGE_2_DIRECTION", [{}, {}]
    )
    stage3_path = V2._build_prior_only_conditional_path(
        conditional, "STAGE_3_BET", [{}, {}]
    )
    for path in (stage1_path, stage2_path, stage3_path):
        assert path.model_receipts[0]["selected_family"] == "PRIOR_ONLY_FIXED"
        assert path.model_receipts[0]["comparator"] == "PRIOR_ONLY_BEST_FIXED"
        assert {row["screen_phase"] for row in path.screen_receipts} == {
            "OUTER_TRAIN"
        }


def test_chain_checkpoint_fixture_is_atomic_deterministic_and_four_arm(
    monkeypatch, tmp_path
):
    chain = R.V2
    action_rows = [
        {
            "interface_action_key": "STATIC",
            "upstream_issue": "134",
            "source_identity": "MARKET_BEST_FULL",
            "parameters_json": json.dumps({"replicate_count": 1}),
        }
    ]
    issues = [
        {
            "issue": str(index + 1),
            "year": "2021",
            "outer_fold": "TEST_2021",
            "issue_instance": f"{index + 1}@TEST_2021",
            "feature_cutoff_ts": f"2021-01-0{index + 1}T00:00:00Z",
        }
        for index in range(2)
    ]
    status = np.asarray(
        [[chain.STATUS_ACTIVE, chain.STATUS_NO_BET]], dtype=np.uint8
    )
    stake = np.asarray([[100.0, 0.0]])
    gross = np.asarray([[120.0, 0.0]])
    tax = np.zeros_like(stake)
    net = gross - stake
    hit = np.asarray([[1.0, 0.0]])
    stage1 = chain.StageStore(
        action_rows=action_rows,
        issues=issues,
        supports={},
        status=status,
        stake=stake,
        gross=gross,
        tax=tax,
        net=net,
        hit=hit,
    )
    conditional = chain.ConditionalStore(
        action_rows=action_rows,
        issues=issues,
        supports={},
        status=status,
        stake=stake,
        gross=gross,
        tax=tax,
        net=net,
        hit=hit,
        conditional_supports={},
        fallback_index=0,
        comparator_net=net[0].copy(),
        comparator_stake=stake[0].copy(),
        utility=np.asarray([[0.2, np.nan]]),
        utility_active=np.asarray([[True, False]]),
        target_mode="ABSOLUTE_UTILITY",
    )
    static_stage1 = chain.static_stage1_path(stage1)
    static_conditional = chain.static_conditional_path(
        conditional, "STAGE_2_DIRECTION"
    )
    static_bet = chain.static_conditional_path(conditional, "STAGE_3_BET")
    monkeypatch.setattr(R, "verify_gate_a", lambda: {"payload": "hash"})
    monkeypatch.setattr(R, "verify_gate_b_sources", lambda: {"source": "hash"})
    monkeypatch.setattr(R, "execution_snapshot", lambda: {"head": "fixture"})
    monkeypatch.setattr(chain, "build_stage1_store", lambda: stage1)
    monkeypatch.setattr(
        chain, "build_honest_stage1_path", lambda _store: static_stage1
    )
    monkeypatch.setattr(
        chain, "build_prior_only_stage1_path", lambda _store: static_stage1
    )
    monkeypatch.setattr(
        chain,
        "build_stage2_store",
        lambda _store, _path: (conditional, [object(), object()]),
    )
    monkeypatch.setattr(
        chain,
        "build_stage2_decisions",
        lambda _store, _path, _decisions: [object(), object()],
    )
    monkeypatch.setattr(
        chain,
        "build_honest_stage2_path",
        lambda _store, _decisions: static_conditional,
    )
    monkeypatch.setattr(
        chain,
        "build_prior_only_stage2_path",
        lambda _store, _decisions: static_conditional,
    )
    monkeypatch.setattr(
        chain,
        "build_stage3_store",
        lambda _store, _stage1, _stage2: conditional,
    )
    monkeypatch.setattr(
        chain,
        "build_honest_stage3_path",
        lambda _store, _stage1, _stage2: static_bet,
    )
    monkeypatch.setattr(
        chain,
        "build_prior_only_stage3_path",
        lambda _store, _stage1, _stage2: static_bet,
    )
    monkeypatch.setattr(
        chain, "selected_stage3_seed_rows", lambda *_args: []
    )
    first = tmp_path / "checkpoint-a"
    second = tmp_path / "checkpoint-b"
    R.build_chain_checkpoint(first)
    R.build_chain_checkpoint(second)
    assert first.is_dir() and second.is_dir()
    first_files = {
        str(path.relative_to(first)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        str(path.relative_to(second)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files
    flows = R.read_csv(first / "issue_policy_flows.csv.gz")
    assert {row["policy_id"] for row in flows} == {
        "ALL_STATIC",
        "DYNAMIC_SELECTION_ONLY",
        "DYNAMIC_SELECTION_DIRECTION",
        "PRIOR_ONLY_BEST_FIXED",
        "FULL_DYNAMIC_CHAIN",
        "LEAKY_ORACLE_CEILING",
    }
    common = json.loads((first / "strict_common_support.json").read_text())
    assert common["issue_ids"] == ["1"]
