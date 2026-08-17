#!/usr/bin/env python3
"""Clean-run and atomically persist the executed #252 evidence notebook."""
from __future__ import annotations
import sys
from pathlib import Path

import nbclient
import nbformat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from source_schema import publication  # noqa: E402

notebook_path = ROOT / "notebooks/research/issue-252/bj252_temporal_semantics.ipynb"
notebook = nbformat.read(notebook_path, as_version=4)
nbclient.NotebookClient(notebook, timeout=1800, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}).execute()
publication.atomic_write_text(notebook_path, nbformat.writes(notebook))
print(f"EXECUTED {notebook_path}")
