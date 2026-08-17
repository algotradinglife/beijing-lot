#!/usr/bin/env python3
"""Render the human-readable Issue #250 decision notebook source."""

from __future__ import annotations

from pathlib import Path

import nbformat


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "notebooks/research/issue-250/bj250_source_census.ipynb"


def main() -> int:
    notebook = nbformat.v4.new_notebook()
    notebook["metadata"]["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    notebook["cells"] = [
        nbformat.v4.new_markdown_cell(
            """# Issue #250 source census — PI takeover decision notebook

This is an **assessment-only** view. It profiles existing files and never crawls, backfills, imputes, trains, builds tickets, or computes ROI. The key distinction is between file presence, a scoped historical relative-time proxy, and canonical causal model eligibility."""
        ),
        nbformat.v4.new_code_cell(
            """import sys
from pathlib import Path
import pandas as pd

root = Path.cwd()
if str(root / 'src') not in sys.path:
    sys.path.insert(0, str(root / 'src'))
from source_census.census import PACKAGE_NAME, PROXY_POLICY_ID

package = root / 'results' / PACKAGE_NAME
assert package.is_dir(), package
print(f'Package: {package.relative_to(root)}')
print(f'Historical proxy policy: {PROXY_POLICY_ID}')
print('Trust note: independent verification still requires an external anchor.')"""
        ),
        nbformat.v4.new_code_cell(
            """def table(name: str) -> pd.DataFrame:
    return pd.read_csv(package / 'tables' / f'{name}.csv')

roles = table('source_role_matrix')
print('SOURCE ROLES')
print(roles[['source_id', 'lane', 'role', 'advance_to_251', 'advance_to_252', 'decision']].to_string(index=False))"""
        ),
        nbformat.v4.new_code_cell(
            """surface = table('proxy_surface_profile')
cols = ['market', 'snapshot_horizon', 'vector_semantics', 'admissible_use',
        'role_gate_eligible', 'vector_row_count', 'physical_cell_count',
        'non_null_physical_cell_count', 'native_identity_valid_match_count']
print('HISTORICAL RELATIVE-TIME SURFACES')
print(surface.loc[surface.source_id.eq('beidan_xlsm'), cols].to_string(index=False))
print()
print('Interpretation: only Euro 1X2 is a three-outcome role-gate surface. Asian handicap and over/under are two prices plus a line, not p34 outcome triplets.')"""
        ),
        nbformat.v4.new_code_cell(
            """period = table('proxy_coverage_by_period')
focus = period.loc[period.year_or_range.astype(str).eq('2024')]
cols = ['market', 'snapshot_horizon', 'match_denominator', 'issue_denominator',
        'vector_row_count', 'physical_cell_count', 'non_null_physical_cell_count',
        'complete_vector_row_count', 'missing_match_count']
print('2024 PERIOD × SURFACE COVERAGE (real denominators)')
print(focus[cols].to_string(index=False))
print()
print('The rows above deliberately separate matches, vector rows, and physical cells.')"""
        ),
        nbformat.v4.new_code_cell(
            """overrides = table('hist40_scope_overrides')
print('INHERITED R8 FIELD × MARKET PROHIBITIONS')
print(overrides[['table', 'column', 'market', 'admissible_use', 'provenance_grade']].to_string(index=False))

intersections = table('intersection_levels')
print()
print('FOUR INTERSECTION LEVELS')
print(intersections[['level', 'lower_bound', 'upper_bound', 'authoritative', 'decision']].to_string(index=False))"""
        ),
        nbformat.v4.new_code_cell(
            """availability = table('source_feature_availability')
print('SOURCE × FEATURE AVAILABILITY')
print(availability[['source_id', 'field_family', 'r8_generic_admissible_field_count',
                    'issue250_scoped_surface_evidence_count', 'present', 'role']].to_string(index=False))

m = table('m_per_issue_distribution')
summary = m.groupby('source_id').m_matches.agg(['count', 'min', 'median', 'max']).reset_index()
print()
print('M PER ISSUE')
print(summary.to_string(index=False))"""
        ),
        nbformat.v4.new_code_cell(
            """ledger = table('unresolved_question_ledger')
print('DECISION SUMMARY')
print('1. beidan_xlsm is usable only as an accepted retrospective relative-time proxy surface.')
print('2. File availability is not canonical causal eligibility; canonical overlap stays deferred to #251/#252.')
print('3. Both live lanes remain raw/unfrozen until clock and sealing policy is verified.')
print('4. No crawling or data recovery was performed in #250.')
print()
print('UNRESOLVED QUESTIONS')
print(ledger.to_string(index=False))"""
        ),
    ]
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, TARGET)
    print(f"RENDERED {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
