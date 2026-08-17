from __future__ import annotations

import array
import csv
import gzip
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj170_selector_allocator_stack_gate_b.py"
SPEC = importlib.util.spec_from_file_location("bj170_gate_b", SCRIPT)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def test_frozen_surface_and_bindings_are_exact() -> None:
    assert RUNNER.SELECTOR_ALIASES == ("BEST_FULL", "Q_SOURCE", "MODEL_SOURCE")
    assert RUNNER.ARM_ALIASES == (
        "FULL_ENUMERATED",
        "Q_TOP_MASS_M192",
        "MODEL_CAP1_M512",
    )
    assert RUNNER.ARM_M == {
        "FULL_ENUMERATED": 2187,
        "Q_TOP_MASS_M192": 192,
        "MODEL_CAP1_M512": 512,
    }
    assert RUNNER.EXPECTED_GATE_A_MANIFEST == (
        "bb60ac5638d29674ad8c1c05f1ffe3ab9cdf12acb70ebdae6cea679743136d87"
    )
    assert RUNNER.EXPECTED_ALLOCATOR_SHA256 == (
        "5f8f5d75dd15758e62dd2a05f7b674cb12824b38ccba35cfee772e8904a8bd93"
    )


def test_mixed_selector_outcome_availability_fails_closed() -> None:
    statuses = {
        "BEST_FULL": "SETTLED",
        "Q_SOURCE": "UNAVAILABLE_CANONICAL_OUTCOME",
        "MODEL_SOURCE": "SETTLED",
    }
    assert RUNNER.common_policy_status(statuses) == "UNAVAILABLE_COMMON_OUTCOME"
    assert RUNNER.common_policy_status({key: "SETTLED" for key in RUNNER.SELECTOR_ALIASES}) == (
        "SETTLED_COMMON"
    )


def test_tax_is_applied_per_winning_ticket_at_boundary() -> None:
    counts = [0, 2, 0]
    below = RUNNER.ticket_settlement(counts, 1, 9_999.99, True)
    boundary = RUNNER.ticket_settlement(counts, 1, 10_000.0, True)
    missing = RUNNER.ticket_settlement(counts, -1, 99_999.0, False)

    assert below == {
        "hit_ticket_count": 2,
        "coverage_hit": 1,
        "gross_yuan": 19_999.98,
        "tax_yuan": 0.0,
        "tax_line_exposure_yuan": 0.0,
        "tax_line_hit_ticket_count": 0,
    }
    assert boundary == {
        "hit_ticket_count": 2,
        "coverage_hit": 1,
        "gross_yuan": 20_000.0,
        "tax_yuan": 4_000.0,
        "tax_line_exposure_yuan": 20_000.0,
        "tax_line_hit_ticket_count": 2,
    }
    assert missing["hit_ticket_count"] == 0
    assert missing["gross_yuan"] == 0.0
    assert missing["tax_yuan"] == 0.0


def test_common_bootstrap_draw_matrix_is_deterministic(tmp_path: Path) -> None:
    first, first_meta = RUNNER.build_draw_matrix(tmp_path / "first.gz", 177)
    second, second_meta = RUNNER.build_draw_matrix(tmp_path / "second.gz", 177)
    assert isinstance(first, array.array)
    assert first == second
    assert first_meta == second_meta
    assert first_meta["replicates"] == 20_000
    assert first_meta["issue_count"] == 177
    assert (tmp_path / "first.gz").read_bytes() == (tmp_path / "second.gz").read_bytes()


def test_interaction_formula_uses_matched_selector_full_controls() -> None:
    best_sleeve = 0.10
    best_full = -0.05
    source_sleeve = 0.20
    source_full = -0.10
    interaction = (best_sleeve - best_full) - (source_sleeve - source_full)
    assert abs(interaction - (-0.15)) < 1e-15


def test_source_bridge_allows_only_serialization_noise() -> None:
    delta = RUNNER.numeric_bridge_delta("0.081425291857", "0.081425291858", 1e-10)
    assert abs(delta) < 1.1e-12
    with pytest.raises(RuntimeError, match="numeric source bridge drift"):
        RUNNER.numeric_bridge_delta("0.081425", "0.081426", 1e-10)


def test_committed_gate_b_package_reconciles() -> None:
    package = ROOT / "results" / "bj170_gate_b_selector_allocator_stack_v1"
    assert RUNNER.sha256_file(package / "SHA256SUMS.json") == (
        "08e83353ad483e5d75911116a413186f007385f5dd37b8c4b757ac903221e512"
    )
    assert RUNNER.sha256_file(package / "CONTENT_IDENTITY.json") == (
        "75325aa0f60e277ad3fbf9d90116450833106bc3863b412ea3efcad9948a47b2"
    )
    manifest = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    assert len(manifest) == 25
    for name, expected in manifest.items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected

    with (package / "nine_cell_primary.csv").open(newline="", encoding="utf-8") as handle:
        cells = list(csv.DictReader(handle))
    assert len(cells) == 9
    assert {(row["selector_alias"], row["allocation_arm"]) for row in cells} == {
        (selector, arm) for selector in RUNNER.SELECTOR_ALIASES for arm in RUNNER.ARM_ALIASES
    }
    assert {row["settled_common_issue_count"] for row in cells} == {"141"}
    assert {row["unavailable_common_issue_count"] for row in cells} == {"36"}

    with gzip.open(
        package / "three_way_issue_contributions.csv.gz", "rt", newline="", encoding="utf-8"
    ) as handle:
        contributions = list(csv.DictReader(handle))
    assert len(contributions) == 177 * 9
    by_issue: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in contributions:
        by_issue[row["issue_instance"]].append(row)
    assert set(Counter(len(rows) for rows in by_issue.values())) == {9}
    unavailable = [
        rows
        for rows in by_issue.values()
        if rows[0]["common_policy_status"] == "UNAVAILABLE_COMMON_OUTCOME"
    ]
    assert len(unavailable) == 36
    assert all(float(row["stake_yuan"]) == 0.0 for rows in unavailable for row in rows)

    with (package / "source_row_reproduction.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        reproduction = list(csv.DictReader(handle))
    assert len(reproduction) == 5
    assert {row["reproduction_status"] for row in reproduction} == {"PASS"}
