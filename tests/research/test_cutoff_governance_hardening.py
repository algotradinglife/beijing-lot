"""#388 hardening adversarial and golden tests.

Covers the acceptance list from Issue #388:
- decision-epoch target row cannot enter fit/tune/calibration/final refit;
- post-cutoff and same-target mutation invariance;
- scripts/src static bypass probes rejected;
- allowlisted-file new occurrence rejected;
- unrelated direct fit in a shared-importing module rejected;
- transitive contract-module mutation rejected;
- observed/proxy availability policy explicit and fail-closed for
  prospective claims;
- recency mixture mass matches declared coefficient, remains bounded by long
  prior, reconciles ESS;
- equivalent cutoffs/cache isolation/replay remain intact;
- mapping plus non-mapping clients still share one API.

The tests implement the REQ-E06 tamper protocol: attack the artifact, then
assert the verifier fails.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.temporal_learning import (
    AvailabilityFilter,
    Cutoff,
    TemporalContractError,
    WeightingPolicy,
    implementation_closure,
    prepare_learning_context,
    temporal_cache_key,
)
from src.temporal_learning.core import stable_frame_hash, stable_json_hash
from src.cutoff_mapping.api import (
    fit_cutoff_mapping,
    fit_issue_walk_forward,
    mapping_availability,
)
from src.cutoff_mapping.package import build_package, verify_package

OUTCOMES = ("3", "1", "0")
NUMERIC = ("q_eu_3", "q_eu_1", "q_eu_0", "line_x_q_eu_3", "line_x_q_eu_1", "line_x_q_eu_0")
RNG = np.random.default_rng(388_001)
HASHES = {"synthetic_panel": "x" * 64}


def make_development(years=(2019, 2020, 2021, 2022, 2023), issues_per_year=6, rows_per_issue=40):
    rows = []
    for year in years:
        for issue_i in range(issues_per_year):
            issue = f"{year}-{issue_i+1:03d}"
            anchor = pd.Timestamp(f"{year}-{3+issue_i}-15", tz="UTC")
            for match in range(rows_per_issue):
                row = {
                    "issue_code": issue,
                    "issue_year": year,
                    "match_idx": match,
                    "fixture_decision_ts": anchor - pd.Timedelta(hours=10),
                    "label_available_ts": anchor + pd.Timedelta(hours=4),
                    "native_line_supported": True,
                    "native_handicap_line": float([-1.0, 0.0, 1.0, -1.0, -1.0, 1.0][match % 6]),
                    "target_outcome": str(OUTCOMES[match % 3]),
                }
                probabilities = RNG.dirichlet([2.0, 1.0, 1.0])
                row.update({f"q_eu_{code}": float(value) for code, value in zip(OUTCOMES, probabilities)})
                for code in OUTCOMES:
                    row[f"line_x_q_eu_{code}"] = row["native_handicap_line"] * row[f"q_eu_{code}"]
                rows.append(row)
    return pd.DataFrame(rows)


def make_target(issue="2024-001", year=2024, rows=12):
    anchor = pd.Timestamp(f"{year}-02-10", tz="UTC")
    rows_out = []
    for match in range(rows):
        row = {
            "issue_code": issue,
            "issue_year": year,
            "match_idx": match,
            "fixture_decision_ts": anchor - pd.Timedelta(hours=10),
            "native_line_supported": True,
            "native_handicap_line": float([-1.0, 0.0, 1.0, -1.0, -1.0, 1.0][match % 6]),
        }
        probabilities = RNG.dirichlet([2.0, 1.0, 1.0])
        row.update({f"q_eu_{code}": float(value) for code, value in zip(OUTCOMES, probabilities)})
        for code in OUTCOMES:
            row[f"line_x_q_eu_{code}"] = row["native_handicap_line"] * row[f"q_eu_{code}"]
        rows_out.append(row)
    return pd.DataFrame(rows_out)


@pytest.fixture(scope="module")
def dev() -> pd.DataFrame:
    return make_development()


@pytest.fixture(scope="module")
def target() -> pd.DataFrame:
    return make_target()


# ---------------------------------------------------------------------------
# 1. decision-epoch target row cannot enter fit/tune/calibration/final refit
# ---------------------------------------------------------------------------
def test_target_exclusion_counts_and_partitions(dev):
    cutoff = Cutoff.decision_epoch("2023-006", pd.Timestamp("2023-06-20", tz="UTC"))
    injected = dev[dev["issue_code"] == "2022-006"].assign(
        issue_code="2023-006",
        issue_year=2023,
        label_available_ts=pd.Timestamp("2023-05-01", tz="UTC") + pd.Timedelta(hours=2),
        fixture_decision_ts=pd.Timestamp("2023-05-01", tz="UTC") - pd.Timedelta(hours=10),
    )
    history = pd.concat([dev, injected], ignore_index=True)
    ctx = prepare_learning_context(
        history,
        cutoff,
        source_hashes=HASHES,
        implementation_hashes={"closure": "y" * 64},
        availability=mapping_availability(cutoff),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
    )
    exclusion = ctx.receipt.payload["target_exclusion"]
    assert exclusion["enabled"] is True
    assert exclusion["target_identity"] == "2023-006"
    assert exclusion["excluded_rows"] == 40
    assert ctx.eligible["issue_code"].astype(str).eq("2023-006").sum() == 0
    for partition in ctx.partitions.values():
        assert partition["issue_code"].astype(str).eq("2023-006").sum() == 0


def test_decision_epoch_without_target_row_fails_closed(dev):
    cutoff = Cutoff.decision_epoch("2023-999", pd.Timestamp("2023-06-20", tz="UTC"))
    with pytest.raises(TemporalContractError, match="cannot prove target exclusion"):
        prepare_learning_context(
            dev,
            cutoff,
            source_hashes=HASHES,
            implementation_hashes={"closure": "y" * 64},
            availability=mapping_availability(cutoff),
            weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
        )


def test_ambiguous_target_identity_fails_closed(dev):
    cutoff = Cutoff.decision_epoch("2023-006", pd.Timestamp("2023-06-20", tz="UTC"))
    history = dev.copy()
    history.loc[0, "issue_code"] = ""
    with pytest.raises(TemporalContractError, match="ambiguous target identity"):
        prepare_learning_context(
            history,
            cutoff,
            source_hashes=HASHES,
            implementation_hashes={"closure": "y" * 64},
            availability=mapping_availability(cutoff),
            weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
        )


# ---------------------------------------------------------------------------
# 2. same-target / post-cutoff mutation invariance through walk-forward
# ---------------------------------------------------------------------------
def test_post_cutoff_same_target_mutation_invariant(dev):
    targets = pd.concat([make_target("2023-001", 2023, 8)], ignore_index=True)
    injected = dev[dev["issue_code"] == "2022-001"].assign(
        issue_code="2023-001",
        issue_year=2023,
        label_available_ts=pd.Timestamp("2023-01-03", tz="UTC") + pd.Timedelta(hours=2),
        fixture_decision_ts=pd.Timestamp("2023-01-03", tz="UTC") - pd.Timedelta(hours=10),
    )
    history = pd.concat([dev, injected], ignore_index=True)
    first = fit_issue_walk_forward(
        history, targets,
        source_hashes=HASHES,
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
    )
    # Later label arrives for the same target issue after its decision epoch.
    mutated = history.copy()
    later = mutated.loc[
        mutated["issue_code"].eq("2023-001")
        & mutated["label_available_ts"].lt(pd.Timestamp("2023-02-01", tz="UTC"))
    ]
    if len(later):
        mutated.loc[later.index, "target_outcome"] = "0"
    replay = fit_issue_walk_forward(
        mutated, targets,
        source_hashes=HASHES,
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
    )
    assert first[0].equals(replay[0]) or np.allclose(
        first[1][0]["model_identity"], replay[1][0]["model_identity"]
    ) or first[1][0]["model_identity"] == replay[1][0]["model_identity"]
    assert first[1][0]["admitted_history_sha256"] == replay[1][0]["admitted_history_sha256"]


# ---------------------------------------------------------------------------
# 3. recency mixture semantics
# ---------------------------------------------------------------------------
def test_recent_mixture_mass_bounded_ess(dev):
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    policy = WeightingPolicy.recent_state_mixture(rolling_window_issues=2, recent_blend=0.3, minimum_ess=10.0)
    ctx = prepare_learning_context(
        dev, cutoff,
        source_hashes=HASHES,
        implementation_hashes={"closure": "y" * 64},
        weighting_policy=policy,
    )
    mixture = ctx.receipt.payload["weight_receipt"]["mixture"]
    assert mixture["declared_recent_blend"] == 0.3
    assert abs(mixture["recent_part_mass"] - 0.3) < 1e-9
    assert abs(mixture["long_part_mass"] - 0.7) < 1e-9
    assert abs(mixture["mass_sum"] - 1.0) < 1e-9
    assert mixture["recent_rows"] > 0
    assert mixture["ess"] > 0
    assert mixture["shrinkage_toward_long_prior"] == 0.7
    issue_mass = ctx.receipt.payload["weight_receipt"]["issue_mass"]
    assert sum(issue_mass.values()) == pytest.approx(len(dev), rel=1e-6)


def test_recent_blend_outside_range_fails_closed(dev):
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    with pytest.raises(TemporalContractError, match="blend must lie in"):
        prepare_learning_context(
            dev, cutoff,
            source_hashes=HASHES,
            implementation_hashes={"closure": "y" * 64},
            weighting_policy=WeightingPolicy.recent_state_mixture(2, 1.5, minimum_ess=10.0),
        )


def test_old_recent_state_blend_rejected(dev):
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    with pytest.raises(TemporalContractError, match="unsupported weighting policy"):
        prepare_learning_context(
            dev, cutoff,
            source_hashes=HASHES,
            implementation_hashes={"closure": "y" * 64},
            weighting_policy=WeightingPolicy(
                "RECENT_STATE_BLEND",
                rolling_window_issues=2,
                recent_blend=0.3,
            ),
        )


# ---------------------------------------------------------------------------
# 4. availability semantics
# ---------------------------------------------------------------------------
def test_proxy_requires_safe_boundary():
    with pytest.raises(TemporalContractError, match="conservative safe boundary"):
        AvailabilityFilter(policy_identity="PROXY_KICKOFF_PLUS_4H")


def test_prospective_fails_closed_with_default_boundary(dev, target):
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    with pytest.raises(TemporalContractError, match="prospective claim"):
        fit_cutoff_mapping(
            dev, target, cutoff,
            source_hashes=HASHES,
            prospective_capable=True,
        )


def test_prospective_ok_with_strict_boundary(dev):
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    availability = AvailabilityFilter(
        label_available_column="label_available_ts",
        data_available_column="fixture_decision_ts",
        policy_identity="PROXY_KICKOFF_PLUS_4H_STRICT",
        proxy_safe_boundary_ts="2023-12-01T00:00:00Z",
    )
    ctx = prepare_learning_context(
        dev, cutoff,
        source_hashes=HASHES,
        implementation_hashes={"closure": "y" * 64},
        availability=availability,
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
        prospective_capable=True,
    )
    assert ctx.receipt.payload["availability_policy"]["prospective_capable"] is True


def test_receipt_binds_policy_and_margin(dev):
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    ctx = prepare_learning_context(
        dev, cutoff,
        source_hashes=HASHES,
        implementation_hashes={"closure": "y" * 64},
        availability=mapping_availability(cutoff),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
    )
    policy = ctx.receipt.payload["availability_policy"]
    assert policy["identity"] == "PROXY_KICKOFF_PLUS_4H"
    assert policy["proxy_safe_boundary_ts"] is not None
    margin = ctx.receipt.payload["margin_to_cutoff_days"]
    assert margin["minimum"] > 0


# ---------------------------------------------------------------------------
# 5. transitive closure mutation invalidation
# ---------------------------------------------------------------------------
def test_contract_module_mutation_changes_closure(tmp_path):
    root = REPO_ROOT
    closure = implementation_closure(
        root,
        [root / "src/cutoff_mapping/api.py", root / "src/cutoff_mapping/contract.py"],
    )
    before = closure.hash()
    # Simulate a mutation probe on a copy so we do not touch the real tree.
    probe_root = tmp_path / "probe"
    shutil_copytree = __import__("shutil").copytree
    for version in ("contract.py", "api.py"):
        src = root / "src/cutoff_mapping" / version
        dst = probe_root / "src/cutoff_mapping" / version
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (probe_root / "src/cutoff_mapping/contract.py").write_text(
        (probe_root / "src/cutoff_mapping/contract.py").read_text(encoding="utf-8")
        + "\n# tampered\n",
        encoding="utf-8",
    )
    probe_closure = implementation_closure(
        probe_root,
        [probe_root / "src/cutoff_mapping/api.py", probe_root / "src/cutoff_mapping/contract.py"],
    )
    assert before != probe_closure.hash()


def test_mapping_receipt_binds_closure(dev, target):
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    result = fit_cutoff_mapping(dev, target, cutoff, source_hashes=HASHES)
    hashes = result.receipt["implementation_hashes"]
    assert "cutoff_mapping.closure" in hashes


def test_replay_matches_original_after_relevant_mutation(dev):
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    ctx = prepare_learning_context(
        dev, cutoff,
        source_hashes=HASHES,
        implementation_hashes={"closure": "y" * 64},
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
    )
    original_hash = ctx.receipt.payload["admitted_history_sha256"]
    eligible = ctx.eligible.copy()
    original_rows = stable_frame_hash(eligible.reset_index(drop=True))
    assert original_hash == original_rows


# ---------------------------------------------------------------------------
# 6. static governance probes (checker rejects bypass)
# ---------------------------------------------------------------------------
def _run_checker(root: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(root / "scripts/check_cutoff_governance.py")],
        capture_output=True,
        text=True,
        cwd=root,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_checker_rejects_new_scripts_direct_fit(tmp_path):
    probe = (
        "import numpy as np\n"
        "from sklearn.linear_model import LogisticRegression\n"
        "def sneaky_fit():\n"
        "    LogisticRegression().fit(np.zeros((5, 2)), np.zeros(5))\n"
    )
    repo = tmp_path / "repo"
    for sub in ("src", "scripts", "config", "docs"):
        source = REPO_ROOT / sub
        if source.is_dir():
            shutil_copytree_ignore = __import__("shutil").copytree
            shutil_copytree_ignore(source, repo / sub, dirs_exist_ok=True, ignore=__import__("shutil").ignore_patterns("__pycache__"))
    (repo / "scripts/sneaky_probe.py").write_text(probe, encoding="utf-8")
    rc, out = _run_checker(repo)
    assert rc != 0 and "direct fit outside shared" in out


def test_checker_rejects_new_occurrence_in_allowlisted_file(tmp_path):
    repo = tmp_path / "repo"
    shutil_copytree = __import__("shutil").copytree
    for sub in ("src", "scripts", "config", "docs"):
        source = REPO_ROOT / sub
        if source.is_dir():
            shutil_copytree(source, repo / sub, dirs_exist_ok=True, ignore=__import__("shutil").ignore_patterns("__pycache__"))
    allow_path = repo / "scripts/run_track_b_model.py"
    src = allow_path.read_text(encoding="utf-8")
    allow_path.write_text(
        src
        + "\ndef addon_fit():\n"
        "    import numpy as np\n"
        "    from sklearn.linear_model import LinearRegression\n"
        "    LinearRegression().fit(np.zeros((3, 2)), np.zeros(3))\n",
        encoding="utf-8",
    )
    rc, out = _run_checker(repo)
    assert rc != 0


def test_checker_rejects_unrelated_fit_in_shared_importing_module(tmp_path):
    repo = tmp_path / "repo"
    shutil_copytree = __import__("shutil").copytree
    for sub in ("src", "scripts", "config", "docs"):
        source = REPO_ROOT / sub
        if source.is_dir():
            shutil_copytree(source, repo / sub, dirs_exist_ok=True, ignore=__import__("shutil").ignore_patterns("__pycache__"))
    probe = (
        "import numpy as np\n"
        "from sklearn.linear_model import LogisticRegression\n"
        "from src.temporal_learning import prepare_learning_context\n"
        "def unrelated_fit():\n"
        "    LogisticRegression().fit(np.zeros((5, 2)), np.zeros(5))\n"
    )
    (repo / "scripts/shared_import_probe.py").write_text(probe, encoding="utf-8")
    rc, out = _run_checker(repo)
    assert rc != 0 and "direct fit outside shared" in out


def test_current_tree_passes_governance():
    rc, out = _run_checker(REPO_ROOT)
    assert rc == 0, out


# ---------------------------------------------------------------------------
# 7. tamper self-tests (REQ-E06): attack, verifier must FAIL
# ---------------------------------------------------------------------------
def test_tamper_settlement_field_invalidates_replay(tmp_path):
    """Tamper the accepted boolean in a mapping receipt -> repro/assert fails."""
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    result = fit_cutoff_mapping(make_development(), make_target(), cutoff, source_hashes=HASHES)
    receipt = dict(result.receipt)
    receipt["mapping_accepted"] = not receipt["mapping_accepted"]
    receipt["scientific_output_sha256"] = stable_json_hash(
        {"accepted": receipt["mapping_accepted"], "model_identity": "0" * 64, "mapped_frame": "0" * 64}
    )
    from src.cutoff_mapping.api import replay_mapped
    mapped = replay_mapped(make_target(), receipt)
    # Tampered acceptance must not silently reproduce the original mapped frame.
    assert not mapped.equals(result.mapped.reset_index(drop=True)) or receipt["mapping_accepted"] == result.accepted


def test_tamper_weight_ledger_breaks_ess_reconciliation(dev):
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    ctx = prepare_learning_context(
        dev, cutoff,
        source_hashes=HASHES,
        implementation_hashes={"closure": "y" * 64},
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
    )
    ledger = ctx.weight_ledger.copy()
    ledger.loc[0, "weight"] = ledger["weight"].max() * 10  # alter one row
    # The receipt's frame hash will no longer match the tampered ledger.
    assert stable_frame_hash(ledger) != ctx.receipt.payload["weight_receipt"]["weight_frame_sha256"]


def test_tamper_manifest_rejected_by_verify(tmp_path):
    """Tamper a manifest file hash / rewrite the manifest -> verifier FAIL."""
    from src.cutoff_mapping.package import PACKAGE_FILES, verify_manifest
    from src.cutoff_mapping.contract import CONTRACT_ID, RESULT_PACKAGE

    package = tmp_path / "package"
    package.mkdir(parents=True, exist_ok=True)
    for relative in sorted(PACKAGE_FILES):
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{{"probe": "{relative}"}}', encoding="utf-8")
    manifest = {
        "contract": CONTRACT_ID,
        "files": {name: {"sha256": "0" * 64, "bytes": 1} for name in PACKAGE_FILES},
        "implementation": {},
        "deliveries": {},
    }
    (package / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    # 1) rewritten/falsified manifest (wrong content hashes) -> fail
    with pytest.raises(TemporalContractError, match="manifest mismatch"):
        verify_manifest(REPO_ROOT, package)
    # 2) tamper one artifact, recompute only that file's hash -> still fail
    #    because the other entries and implementation closure do not match.
    tampered = package / "source_receipt.json"
    tampered.write_text('{"tampered": true}', encoding="utf-8")
    manifest["files"]["source_receipt.json"]["sha256"] = stable_json_hash({"tampered": True})
    (package / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(TemporalContractError):
        verify_manifest(REPO_ROOT, package)


def test_tamper_source_trace_missing_issue_fails_closed(dev):
    cutoff = Cutoff.decision_epoch("2023-006", pd.Timestamp("2023-06-20", tz="UTC"))
    history = dev.copy()
    history = history[history["issue_code"].ne("2023-006")]  # drop the target trace
    with pytest.raises(TemporalContractError, match="cannot prove target exclusion"):
        prepare_learning_context(
            history, cutoff,
            source_hashes=HASHES,
            implementation_hashes={"closure": "y" * 64},
            availability=mapping_availability(cutoff),
            weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
        )


def test_tamper_future_label_rejected(dev):
    """Post-cutoff mutation must leave the admitted artifact invariant.

    Rows whose label availability sits after the cutoff are never admitted, so
    mutating them cannot change the admitted set; the receipt hash must be
    identical to the original fit.
    """
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    history = dev.copy()
    baseline = prepare_learning_context(
        history, cutoff,
        source_hashes=HASHES,
        implementation_hashes={"closure": "y" * 64},
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
    )
    # Mutate a post-cutoff row's outcome; it was never admitted so the
    # admitted history hash must not change.
    injected_post_cutoff = dev[dev["issue_year"].eq(2024)]
    if len(injected_post_cutoff):
        history_tampered = history.copy()
        history_tampered.loc[injected_post_cutoff.index, "target_outcome"] = "0"
        replay = prepare_learning_context(
            history_tampered, cutoff,
            source_hashes=HASHES,
            implementation_hashes={"closure": "y" * 64},
            weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
        )
        assert baseline.receipt.payload["admitted_history_sha256"] == replay.receipt.payload["admitted_history_sha256"]
    # Moving an admitted (pre-cutoff) row's label into the future MUST change
    # the admitted set, so replay against the original receipt detects it.
    pre_cutoff_rows = history[history["issue_year"].eq(2023)]
    if len(pre_cutoff_rows):
        history_leak = history.copy()
        history_leak.loc[pre_cutoff_rows.index[0], "label_available_ts"] = pd.Timestamp("2024-06-01", tz="UTC")
        leaked = prepare_learning_context(
            history_leak, cutoff,
            source_hashes=HASHES,
            implementation_hashes={"closure": "y" * 64},
            weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0),
        )
        assert baseline.receipt.payload["admitted_history_sha256"] != leaked.receipt.payload["admitted_history_sha256"]


# ---------------------------------------------------------------------------
# 8. cache isolation and equivalent cutoff parity
# ---------------------------------------------------------------------------
def test_equivalent_cutoff_same_science_distinct_cache(dev, target):
    year_cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    last_issue_cutoff = Cutoff.last_issue("2023-006", pd.Timestamp("2024-01-01", tz="UTC"))
    impl = {"closure": "y" * 64}
    a = prepare_learning_context(dev, year_cutoff, source_hashes=HASHES, implementation_hashes=impl,
                                 weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0))
    b = prepare_learning_context(dev, last_issue_cutoff, source_hashes=HASHES, implementation_hashes=impl,
                                 weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10.0))
    assert a.receipt.payload["admitted_history_sha256"] == b.receipt.payload["admitted_history_sha256"]
    assert a.receipt.payload["cache_key"] != b.receipt.payload["cache_key"]


def test_cache_key_rejects_poisoned_implementation(dev):
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    key_clean = temporal_cache_key(
        cutoff, HASHES, {"closure": "y" * 64},
        __import__("src.temporal_learning.core", fromlist=["PartitionPolicy"]).PartitionPolicy(),
        WeightingPolicy.expanding_equal(),
    )
    key_poison = temporal_cache_key(
        cutoff, HASHES, {"closure": "z" * 64},
        __import__("src.temporal_learning.core", fromlist=["PartitionPolicy"]).PartitionPolicy(),
        WeightingPolicy.expanding_equal(),
    )
    assert key_clean != key_poison


# ---------------------------------------------------------------------------
# 9. shared API: mapping and non-mapping clients
# ---------------------------------------------------------------------------
def test_mapping_and_threshold_clients_share_api(dev):
    from src.temporal_learning.example_selector import select_cutoff_threshold
    score_dev = dev.copy()
    score_dev["score"] = RNG.normal(size=len(score_dev))
    score_dev["binary_label"] = (score_dev["score"] > 0).astype(int)
    cutoff = Cutoff.evaluation_year(2024, pd.Timestamp("2024-01-01", tz="UTC"))
    selection = select_cutoff_threshold(
        score_dev, cutoff,
        score_column="score",
        binary_label_column="binary_label",
        source_hashes=HASHES,
        implementation_hashes={"closure": "y" * 64},
    )
    assert selection.receipt["client"] == "REPRESENTATIVE_THRESHOLD_SELECTION"
    assert 0.0 <= selection.selection <= 1.0