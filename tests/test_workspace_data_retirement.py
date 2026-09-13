import hashlib
import json
import os
import subprocess
import sys

import pytest


@pytest.fixture
def retirement(tmp_path):
    workspace = tmp_path / "workspace"
    source = workspace / "data/raw/fundamentals_411/sample"
    source.mkdir(parents=True)
    (source / "record.json").write_bytes(b"original")
    (source / "keep.json").write_bytes(b"retained")
    (source / "symbolic").symlink_to("keep.json")
    os.link(source / "keep.json", source / "hardlink")
    root = tmp_path / "persistent"
    (root / "registry").mkdir(parents=True)
    archive = root / "sample.tar.zst"
    subprocess.run(["tar", "--zstd", "-cf", str(archive), "-C", str(source.parent), source.name], check=True)
    catalog = root / "registry/catalog.json"
    catalog.write_text(json.dumps({"entries": [{"source": str(source), "archive": archive.name,
                                               "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}]}))
    command = [sys.executable, "scripts/retire_archived_workspace_data.py", "--workspace", str(workspace),
               "--data-root", str(root), "--mountpoint", "/", "--catalog", "registry/catalog.json"]
    return source, root, archive, catalog, command


def test_verified_removal_is_resumable_and_preserves_archive(retirement):
    source, root, archive, catalog, command = retirement
    before = archive.read_bytes()
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not source.exists() and archive.read_bytes() == before
    assert json.loads(catalog.read_text())["entries"][0]["source_removed"] is True
    assert subprocess.run(command, capture_output=True).returncode == 0


@pytest.mark.parametrize("change", ["extra", "bytes", "archive"])
def test_changed_data_is_never_removed(retirement, change):
    source, root, archive, catalog, command = retirement
    if change == "extra":
        (source / "new.json").write_text("new data")
    elif change == "bytes":
        (source / "record.json").write_bytes(b"modified")
    else:
        archive.write_bytes(archive.read_bytes() + b"corruption")
    result = subprocess.run(command, capture_output=True)
    assert result.returncode != 0
    assert source.exists() and (source / "record.json").exists()


@pytest.mark.parametrize("mutation", [None, "extra", "bytes", "symlink"])
def test_partial_directory_removal_resumes_without_accepting_changed_survivors(retirement, mutation):
    source, root, archive, catalog, command = retirement
    row = json.loads(catalog.read_text())["entries"][0]
    (root / "registry/source-retirement.json").write_text(json.dumps({"entries": {str(source): {
        "state": "VERIFIED_READY_FOR_REMOVAL", "archive_sha256": row["archive_sha256"]}}}))
    (source / "record.json").unlink()
    if mutation == "extra":
        (source / "new.json").write_text("not archived")
    elif mutation == "bytes":
        (source / "keep.json").write_bytes(b"changed")
    elif mutation == "symlink":
        (source / "symbolic").unlink()
        (source / "symbolic").symlink_to("elsewhere")
    result = subprocess.run(command, capture_output=True, text=True)
    if mutation is None:
        assert result.returncode == 0, result.stderr
        assert not source.exists()
    else:
        assert result.returncode != 0
        assert source.exists()


@pytest.mark.parametrize("relative,allowed", [("data/derived/nowscore_only", True), ("data/raw/settlement_supplements", True), ("data/unrelated", False)])
def test_settlement_roots_are_explicit_and_other_roots_rejected(retirement, relative, allowed):
    source, root, archive, catalog, command = retirement
    workspace = source.parents[3]
    moved = workspace / relative / source.name
    moved.parent.mkdir(parents=True)
    source.rename(moved)
    value = json.loads(catalog.read_text())
    value["entries"][0]["source"] = str(moved)
    catalog.write_text(json.dumps(value))
    result = subprocess.run(command, capture_output=True, text=True)
    assert (result.returncode == 0) == allowed, result.stderr
    assert moved.exists() != allowed
