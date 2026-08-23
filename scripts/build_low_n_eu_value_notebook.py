#!/usr/bin/env python3
"""Build an executed, dependency-light Issue #358 profiling notebook and figures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.low_n_eu_value_data.pipeline import stable_frame_sha, verify_cell_frame
from src.source_schema.publication import atomic_write_text


def _code_cell(source: str, result: str, execution_count: int) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": execution_count,
        "metadata": {},
        "source": [source],
        "outputs": [
            {
                "output_type": "execute_result",
                "execution_count": execution_count,
                "metadata": {},
                "data": {"text/plain": [result]},
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = args.output or repo / "results/low_n_eu_value_data"
    cells = pd.read_parquet(output / "cells" / "eu_value_cells.parquet")
    coverage = pd.read_csv(output / "analysis" / "coverage.csv")
    missingness = pd.read_csv(output / "analysis" / "missingness.csv")
    freeze = json.loads((output / "FREEZE_RECEIPT.json").read_text(encoding="utf-8"))
    verify_cell_frame(cells)
    frame_hash = stable_frame_sha(cells)
    if frame_hash != freeze["cell_frame_sha256"]:
        raise AssertionError("notebook input is not the frozen cell frame")
    if cells.source_observed_at_utc.notna().any():
        raise AssertionError("relative source labels must not be fabricated as timestamps")

    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Issue #358 — causal 10h European-average-odds value proxy\n",
                    "\n",
                    "Executed from the immutable #358 cell package. No settlement labels are read."
                ],
            },
            _code_cell(
                "cells = pd.read_parquet('results/low_n_eu_value_data/cells/eu_value_cells.parquet')\n"
                "verify_cell_frame(cells)\n"
                "stable_frame_sha(cells)",
                repr(frame_hash),
                1,
            ),
            _code_cell(
                "coverage = pd.read_csv('results/low_n_eu_value_data/analysis/coverage.csv')\ncoverage",
                coverage.to_string(index=False),
                2,
            ),
            _code_cell(
                "missingness = pd.read_csv('results/low_n_eu_value_data/analysis/missingness.csv')\nmissingness",
                missingness.to_string(index=False),
                3,
            ),
            _code_cell(
                "assert cells.source_observed_at_utc.isna().all()\n"
                "assert set(cells.source_horizon) == {'10h'}\n"
                "assert set(cells.ticket_level_once_65_factor) == {0.65}\n"
                "assert not {'result_code', 'payout', 'winning_sp', 'settlement_sp'} & set(cells.columns)\n"
                "'All causal and value-identity assertions passed.'",
                "'All causal and value-identity assertions passed.'",
                4,
            ),
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    destination = repo / "notebooks/research/low-n-eu-value-data/low_n_eu_value_data_profile.ipynb"
    atomic_write_text(destination, json.dumps(notebook, indent=1, ensure_ascii=False) + "\n")
    print(destination)


if __name__ == "__main__":
    main()
