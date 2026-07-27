from __future__ import annotations

import csv
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/project_bj_n7_safe_input.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("project_bj_n7_safe_input", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _mixed_row(issue: str = "9001", match_idx: str = "1") -> dict[str, str]:
    return {
        "issue": issue, "match_idx": match_idx, "match_id": f"{issue}_{int(match_idx):03d}",
        "home": "H", "away": "A", "kickoff_ts": "2026-01-01T00:00:00Z",
        "decision_cutoff_ts": "2025-12-31T20:00:00Z", "snapshot_ts": "2025-12-31T19:00:00Z",
        "snapshot_age_hours_at_cutoff": "1", "selected_codes": "3+1",
        "quoted_sp_3": "3.1", "quoted_sp_1": "3.2", "quoted_sp_0": "3.3",
        "effective_sp_3": "3", "effective_sp_1": "3", "effective_sp_0": "3",
        "official_result_code": "DO_NOT_ASSERT", "coverage_hit": "DO_NOT_ASSERT",
    }


def _write_mixed(path: Path, mod, rows: list[dict[str, str]], header=None) -> str:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header or mod.SOURCE_HEADER, lineterminator="\n", extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_project_is_byte_identical_and_does_not_emit_forbidden_values(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load_module()
    source = tmp_path / "mixed.csv"
    expected = _write_mixed(source, mod, [_mixed_row("9002", "2"), _mixed_row("9001", "1")])
    one, two = tmp_path / "one.csv", tmp_path / "two.csv"
    mod.project(source, one, expected_sha256=expected)
    mod.project(source, two, expected_sha256=expected)
    assert one.read_bytes() == two.read_bytes()
    assert "DO_NOT_ASSERT" not in one.read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""


def test_header_mismatch_and_duplicate_identity_fail_closed(tmp_path: Path) -> None:
    mod = _load_module()
    source = tmp_path / "mixed.csv"
    expected = _write_mixed(source, mod, [_mixed_row()], header=mod.SOURCE_HEADER[:-1])
    with pytest.raises(mod.ProjectionError, match="header mismatch"):
        mod.project(source, tmp_path / "out.csv", expected_sha256=expected)

    expected = _write_mixed(source, mod, [_mixed_row(), _mixed_row()])
    with pytest.raises(mod.ProjectionError, match="duplicate"):
        mod.project(source, tmp_path / "out.csv", expected_sha256=expected)


@pytest.mark.parametrize("raw", ["NaN", "inf", "-inf"])
def test_project_rejects_non_finite_sp(tmp_path: Path, raw: str) -> None:
    mod = _load_module()
    source = tmp_path / "mixed.csv"
    row = _mixed_row()
    row["quoted_sp_3"] = raw
    expected = _write_mixed(source, mod, [row])
    with pytest.raises(mod.ProjectionError, match="quoted SP"):
        mod.project(source, tmp_path / "out.csv", expected_sha256=expected)


def test_project_refuses_source_and_existing_destination(tmp_path: Path) -> None:
    mod = _load_module()
    source = tmp_path / "mixed.csv"
    expected = _write_mixed(source, mod, [_mixed_row()])
    with pytest.raises(mod.ProjectionError, match="equals authorized source"):
        mod.project(source, source, expected_sha256=expected)

    destination = tmp_path / "existing.csv"
    destination.write_text("do not overwrite\n", encoding="utf-8")
    with pytest.raises(mod.ProjectionError, match="already exists"):
        mod.project(source, destination, expected_sha256=expected)
    assert destination.read_text(encoding="utf-8") == "do not overwrite\n"
