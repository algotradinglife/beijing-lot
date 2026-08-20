#!/usr/bin/env python3
"""Programmatically build the issue-209 Gate A notebook (thin orchestration)."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path("notebooks/research/issue-209/bj209_gate_a.ipynb")


def md(src): return {"cell_type": "markdown", "metadata": {}, "source": ["\n".join(src)]}
def code(src):
    return {"cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [],
            "source": ["\n".join(src)]}


cells = [
    md([
        "# Issue #209 — Unified Learning Gate A: divergence-aware M×3 value model",
        "",
        "**Contract:** BJ-UNIFIED-FULL-CYCLE-HIST-001/v3 (PI amendment 2026-08-20, accepted #238 interface).",
        "**Audit mode:** exploration. **Scope:** Gate A development through 2023. **2024 labels stay sealed** (Gate B not opened).",
        "",
        "Pipeline: tensor → census → distributional probability → SP quantiles → cell value → ticket/policy → bankroll → freeze identity.",
        "",
        "Reusable package-first code under `src/issue209/`; this notebook is a thin orchestration layer.",
    ]),
    code([
        "import sys, warnings",
        'warnings.filterwarnings("ignore")',
        'sys.path.insert(0, "../..")',
        "from issue209.data import build_tensor, build_census",
        "from issue209.models import (",
        "    build_match_units, market_only_probabilities, fit_calibrated_logistic,",
        "    fit_mlp_challenger, predict_logistic, predict_mlp, evaluate_calibration, _compute_losses,",
        ")",
        "from issue209.value import fit_sp_quantile_model, predict_sp_quantiles, cell_value_distribution",
        "from issue209.ticket import select_ticket_panel, settle_ticket",
        "from issue209.bankroll import simulate_bankroll, summarize_capital",
        "import numpy as np, pandas as pd, json",
    ]),
    md(["## Stage 0/1 — tensor + census (REQ-209-01/02/07)"]),
    code([
        "tensor = build_tensor()",
        'sealed = int((tensor["issue_year"] >= 2024).sum()) + int(tensor["issue"].astype(str).str.match(r"^24").sum())',
        'print("tensor rows:", len(tensor), "| sealed 2024 rows:", sealed, "(must be 0)")',
        "census = build_census(tensor)",
        "display(census)",
    ]),
    md(["## Stage 2 — distributional probability learning (REQ-209-04, -03)"]),
    code([
        "units = build_match_units(tensor)",
        "market = market_only_probabilities(units)",
        "logistic = fit_calibrated_logistic(units)",
        "mlp = fit_mlp_challenger(units)",
        "pred_l = predict_logistic(logistic, units)",
        "pred_m = predict_mlp(mlp, units)",
        'tune_idx = np.where(units["temporal_role"].isin(["tune"]))[0]',
        'yt = units["realized_outcome"].astype(str).iloc[tune_idx]',
        "tune = {",
        '  "market_only": _compute_losses(yt, market.iloc[tune_idx])["log_loss"],',
        '  "logistic": _compute_losses(yt, pred_l.iloc[tune_idx])["log_loss"],',
        '  "mlp": _compute_losses(yt, pred_m.iloc[tune_idx])["log_loss"],',
        "}",
        'print("tune 2022 log-loss:", json.dumps(tune, indent=2))',
        "chosen = min(tune, key=tune.get)",
        'print("frozen candidate family:", chosen)',
    ]),
    md(["## Stage 3 — SP quantiles + cell-value distribution (REQ-209-04)"]),
    code([
        "sp = fit_sp_quantile_model(units)",
        "sp_q = predict_sp_quantiles(sp, units)",
        'prob_chosen = market if chosen == "market_only" else (pred_m if chosen == "mlp" else pred_l)',
        "value = cell_value_distribution(prob_chosen, sp_q, units)",
        'print("cell value columns:", [c for c in value.columns])',
        'display(value[["ev_raw_3","ev_raw_1","ev_raw_0"]].head())',
    ]),
    md(["## Stage 4 — ticket/policy + bankroll on 2023 dry-run (REQ-209-05/06/08)"]),
    code([
        'cal = units[units["temporal_role"].isin(["calibration"])].copy()',
        "res = []",
        'for issue in sorted(cal["issue"].unique()):',
        '    panel = select_ticket_panel(cal, value, issue, "10h", n=7, k=8, seed=209003)',
        "    if panel.empty:",
        '        res.append({"issue":issue,"n_tickets":0,"stake_total":0.0,"realized_gross":0.0}); continue',
        "    gross = 0.0",
        "    for _, r in panel.iterrows():",
        '        ti = tensor[tensor["issue"].astype(str)==str(issue)]',
        '        gross += settle_ticket(r["matches"], r["outcomes"], ti)["gross_multiple"] * 2.0',
        '    res.append({"issue":issue,"n_tickets":len(panel),"stake_total":len(panel)*2.0,"realized_gross":gross})',
        "issue_res = pd.DataFrame(res)",
        "path = simulate_bankroll(issue_res)",
        "summary = summarize_capital(path)",
        'print("2023 dry-run:", json.dumps(summary, indent=2))',
    ]),
    md(["## Gate A decision (REQ-209-11: 2024 sealed; Gate B not opened)"]),
    code([
        'print("GATE_A_FROZEN_IDENTITY:", chosen)',
        'print("Gate B (2024 terminal): NOT_OPENED — sealed until PI authorizes")',
    ]),
]

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3 (issue209)", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11.15"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(nb, indent=1))
print("wrote", OUT)
