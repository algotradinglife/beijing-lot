"""BJ #234 — canonical source registry / identity / temporal store contract.

BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1 (PI-user design freeze, 2026-08-16).

Package layout:
- contract.py    — frozen contract (tables, domains, enums, identity rule)
- schemas.py     — DDL + PyArrow schema renderers, domain dictionary
- profiler.py    — read-only profiling of existing source databases/packages
- crosswalk.py   — legacy identity → canonical fixture crosswalk (REQ-DS02)
- feasibility.py — source feasibility matrix + replacement plan
- publication.py — immutable package publication + verification
"""
