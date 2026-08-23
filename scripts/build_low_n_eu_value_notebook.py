#!/usr/bin/env python3
"""Build and execute Issue #358's outcome-free profiling notebook.

The repository's declared nbformat/nbclient dependencies are used by CI.  This
small builder deliberately emits standard nbformat-v4 JSON itself so a frozen
research package can be rebuilt in the minimal production environment too.
Each code cell is executed in one shared Python namespace before the notebook is
written; execution errors fail the build rather than being serialized as a
plausible-looking notebook.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.source_schema.publication import atomic_write_json


def _markdown(source: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def _code(source: str) -> dict[str, Any]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source}


def _execute(notebook: dict[str, Any], *, cwd: Path) -> None:
    namespace: dict[str, Any] = {"__name__": "__main__"}
    for count, cell in enumerate((item for item in notebook["cells"] if item["cell_type"] == "code"), start=1):
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                exec(compile(cell["source"], f"{cwd}/low_n_eu_value_profile.ipynb:cell-{count}", "exec"), namespace)
        except BaseException as exc:
            cell["execution_count"] = count
            cell["outputs"] = [{
                "output_type": "error",
                "ename": type(exc).__name__,
                "evalue": str(exc),
                "traceback": [],
            }]
            raise RuntimeError(f"notebook cell {count} failed") from exc
        cell["execution_count"] = count
        text = output.getvalue()
        cell["outputs"] = [] if not text else [{"output_type": "stream", "name": "stdout", "text": text}]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    package = (args.output or repo / "results/low_n_eu_value_proxy").resolve()
    target = repo / "notebooks/research/low-n-eu-value/low_n_eu_value_profile.ipynb"

    notebook: dict[str, Any] = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "cells": [
            _markdown(
                "# Issue #358 — European-average-odds value proxy\n\n"
                "Executed from the frozen #354 10h pre-outcome feature surface and a hash-bound "
                "European 1X2 source. The `10h` field is a retrospective relative horizon, not an "
                "exact observation timestamp or Beijing SP."
            ),
            _code(
                "from pathlib import Path\n"
                "import json\n"
                "import pandas as pd\n"
                "import pyarrow.parquet as pq\n\n"
                f"package = Path({str(package)!r})\n"
                "cells = pq.read_table(package / 'value_cells.parquet').to_pandas()\n"
                "quality = pd.read_csv(package / 'quality_by_fixture.csv')\n"
                "profile = pd.read_csv(package / 'year_profile.csv')\n"
                "recipe = pd.read_csv(package / 'n3_n5_full_cartesian_recipe.csv')\n"
                "receipt = json.loads((package / 'FREEZE_RECEIPT.json').read_text(encoding='utf-8'))\n"
                "coverage = {\n"
                "    'cells': int(len(cells)),\n"
                "    'fixtures': int(cells[['issue', 'match_idx']].drop_duplicates().shape[0]),\n"
                "    'issues': int(cells['issue'].nunique()),\n"
                "    'years': sorted(int(value) for value in cells['issue_year'].unique()),\n"
                "    'outcome_order': list(cells.groupby(['issue', 'match_idx'])['outcome_code'].agg(tuple).iloc[0]),\n"
                "}\n"
                "print(json.dumps(coverage, indent=2, sort_keys=True))"
            ),
            _code(
                "quality_summary = (\n"
                "    quality.groupby('quality_grade', sort=True)\n"
                "    .agg(fixtures=('match_idx', 'size'), mean_books=('contributing_bookmaker_count', 'mean'), invalid_rows=('invalid_bookmaker_rows', 'sum'))\n"
                "    .reset_index()\n"
                ")\n"
                "print(quality_summary.to_string(index=False))"
            ),
            _code("print(profile.to_string(index=False))"),
            _code("print(recipe.to_string(index=False))"),
            _code(
                "forbidden = {'result_code', 'winning_sp', 'settlement_sp', 'payout', 'realized_gross'}\n"
                "identities = {\n"
                "    'average_odds_overround_all_positive': bool(cells['average_odds_overround'].gt(0).all()),\n"
                "    'source_consensus_matches_354_raw': bool(cells['source_consensus_devig_probability'].gt(0).all()),\n"
                "    'calibrated_probability_positive': bool(cells['calibrated_probability_354'].gt(0).all()),\n"
                "    'no_settlement_columns': not bool(forbidden & set(cells.columns)),\n"
                "    'relative_horizon_only': sorted(cells['source_timestamp_semantics'].unique().tolist()),\n"
                "}\n"
                "assert all(value is True for key, value in identities.items() if key != 'relative_horizon_only')\n"
                "print(json.dumps(identities, indent=2, sort_keys=True))"
            ),
            _code("print(json.dumps(receipt, indent=2, sort_keys=True))"),
            _markdown(
                "## Decision boundary\n\n"
                "The package exposes odds-derived value ingredients for later low-N research. It does "
                "not use settlement labels, calibrate Beijing payout, rank fixtures, choose a selector, "
                "or claim an executable betting edge."
            ),
        ],
    }
    _execute(notebook, cwd=repo)
    atomic_write_json(target, notebook)
    print(target)


if __name__ == "__main__":
    main()
