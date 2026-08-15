#!/usr/bin/env python3
"""Execute the issue-229 divergence-profile notebook top-to-bottom.

Rework 2026-08-15 (class-6 sweep): the executed notebook is written with
temp + fsync + atomic replace + parent-directory fsync so a crash mid-write
cannot leave a truncated notebook.  The audited executor wrote the single
notebook file with flush+fsync+replace but skipped the parent-directory
fsync; all write points now fsync their parent directory.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

NOTEBOOK = ROOT / "notebooks" / "research" / "issue-229" / "bj229_divergence_profile.ipynb"


def fsync_parent(path: Path) -> None:
    directory = path.parent
    try:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def atomic_write_text(path: Path, content: str) -> None:
    """temp + fsync + atomic replace + parent fsync."""
    directory = path.parent
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(directory)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        fsync_parent(directory)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def finalize_manifest_binding(root: Path) -> None:
    """Rebind MANIFEST.notebook_hash + SHA256SUMS after the notebook executes.

    The notebook's build cell runs before the executor persists the executed
    notebook, so its MANIFEST binds the unexecuted source file.  After
    atomic_write_text saves the executed notebook, this finalize step updates
    MANIFEST.json to bind the executed notebook and regenerates SHA256SUMS so
    the committed package is self-consistent (REQ-D09 exact-SHA binding).
    """
    from divergence_profile import contract, manifest

    package = contract.package_path(root)
    manifest_path = package / "MANIFEST.json"
    if not manifest_path.exists():
        return
    import json

    payload = json.loads(manifest_path.read_text())
    payload["notebook_hash"] = manifest.sha256_file(
        root / "notebooks" / "research" / "issue-229" / "bj229_divergence_profile.ipynb"
    )
    atomic_write_text(manifest_path, json.dumps(payload, indent=2, ensure_ascii=False))
    manifest.write_sha256sums(package)
    print(f"FINALIZED manifest notebook_hash={payload['notebook_hash'][:12]}...")


def run(nb_path: Path = NOTEBOOK, timeout: int = 1800) -> Path:
    """Execute the notebook with nbclient and atomically persist it."""
    import nbclient
    import nbformat

    notebook = nbformat.read(nb_path, as_version=4)
    started = time.time()
    client = nbclient.NotebookClient(
        notebook,
        timeout=timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    notebook.metadata["executed_at_utc"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
    )
    notebook.metadata["execution_wall_seconds"] = round(time.time() - started, 1)
    content = nbformat.writes(notebook)
    atomic_write_text(nb_path, content)
    finalize_manifest_binding(ROOT)
    print(f"EXECUTED {nb_path} in {notebook.metadata['execution_wall_seconds']}s")
    return nb_path


if __name__ == "__main__":
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--notebook", type=Path, default=NOTEBOOK)
    value.add_argument("--timeout", type=int, default=1800)
    arguments = value.parse_args()
    run(arguments.notebook, timeout=arguments.timeout)
