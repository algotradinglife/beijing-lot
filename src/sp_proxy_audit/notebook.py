"""Create and execute the decision notebook for Issue #318."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def build_notebook(repo_root: Path, path: Path) -> None:
    repo_root = repo_root.resolve()
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook(
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3"},
        }
    )
    notebook.cells = [
        nbformat.v4.new_markdown_cell(
            "# Issue #318: historical Beijing SP and proxy admissibility\n\n"
            "Executed completeness, provenance, overlap, distortion, and decision review. "
            "No outcome or ROI data is read."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\n"
            "import json\n"
            "import pandas as pd\n"
            "from IPython.display import Image, display\n"
            "ROOT = Path.cwd()\n"
            "PACKAGE = ROOT / 'results/sp_proxy_audit'\n"
            "decision = json.loads((PACKAGE / 'decision.json').read_text())\n"
            "inventory = pd.read_csv(PACKAGE / 'source_inventory.csv')\n"
            "coverage = pd.read_csv(PACKAGE / 'coverage_by_issue.csv')\n"
            "overlap = pd.read_csv(PACKAGE / 'overlap_metrics.csv')\n"
            "exclusions = pd.read_parquet(PACKAGE / 'exclusion_ledger.parquet')\n"
            "decision"
        ),
        nbformat.v4.new_markdown_cell("## Source completeness and provenance"),
        nbformat.v4.new_code_cell(
            "display(inventory[['source_id','relative_path','availability','sha256','bytes']])\n"
            "assert inventory['availability'].eq('PRESENT').all()"
        ),
        nbformat.v4.new_markdown_cell("## Grade and N7-capacity coverage"),
        nbformat.v4.new_code_cell(
            "coverage_summary = (coverage.groupby(['partition','source_id','source_grade','snapshot_kind'], "
            "dropna=False).agg(issues=('issue_code','nunique'), vectors=('vector_count','sum'), "
            "cells=('cell_count','sum'), feasible_n7_issues=('feasible_n7','sum')).reset_index())\n"
            "display(coverage_summary)\n"
            "display(Image(filename=str(PACKAGE / 'coverage_by_partition.png')))"
        ),
        nbformat.v4.new_markdown_cell("## Strict/proxy overlap and distortion"),
        nbformat.v4.new_code_cell(
            "display(overlap)\n"
            "for name in ['price_error_by_horizon.png','top2_top7_agreement.png','q_distortion.png']:\n"
            "    display(Image(filename=str(PACKAGE / name)))"
        ),
        nbformat.v4.new_markdown_cell("## Exclusion reconstruction"),
        nbformat.v4.new_code_cell("display(exclusions)"),
        nbformat.v4.new_markdown_cell("## Frozen terminal decision"),
        nbformat.v4.new_code_cell(
            "summary = {\n"
            "    'terminal_disposition': decision['terminal_disposition'],\n"
            "    'observed_metrics': decision['observed_metrics'],\n"
            "    'failed_thresholds': decision['failed_thresholds'],\n"
            "    'recommendation': decision['recommendation'],\n"
            "}\n"
            "summary"
        ),
    ]
    for index, cell in enumerate(notebook.cells):
        cell["id"] = f"bj318-cell-{index:02d}"
    client = NotebookClient(
        notebook,
        timeout=600,
        kernel_name="python3",
        record_timing=False,
        resources={"metadata": {"path": str(repo_root)}},
    )
    client.execute()
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        nbformat.write(notebook, temporary_path)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
