# Phase 5a — Live → Plan → Reconcile Pipeline

Operational glue between the Live Collector (3-SP snapshots written to
`data/beidan_live.db`) and an executable weekly bet plan in markdown +
JSON form. Adds `src/phase5a/` and `tests/phase5a/` without touching any
existing module.

## Layout

```
src/phase5a/
  __init__.py       public API (load, qualify, build, reconcile)
  data_loader.py    LiveSnapshot + load_open_matches (latest SP per match)
  filter.py         NicheConfig (JSON) + qualify_candidates → Candidate
  planner.py        build_weekly_plan, format_plan_markdown, save_plan_json
  pnl_log.py        append-only CSV with cumulative_pnl
  reconcile.py      compare saved plan vs settlements; append PnL row
  cli.py            python -m src.phase5a {plan|reconcile}
  niches_default.json  surviving niches from data/raw/archetype_B_niches.csv
```

## Flow

```
beidan_live.db.matches/snapshots
        │  data_loader.load_open_matches(window_days=7, status='open')
        ▼
   List[LiveSnapshot]
        │  filter.qualify_candidates(snaps, NicheConfig.load(...))
        ▼
   List[QualifiedCandidate]   (one per (match, option) that hits a niche)
        │  planner.build_weekly_plan(...) → combo_optimizer.build_plan(...)
        ▼
   PlanResult (List[TicketPlan])  ──► markdown table + data/phase5a_plans/{ISO_WEEK}.json

[later, after kaijiang]
   reconcile.reconcile_plan(plan_json, db, pnl_log)
        ▼
   ReconcileResult + appended row in data/phase5a_pnl/pnl_log.csv
```

## Defaults

- N=4 legs, Kelly=1/16=0.0625 — Calmar-optimal cell from
  `data/raw/kelly_n_grid.csv` (Calmar 7.15, max-DD −36%).
- Single-leg edge floor relaxed to −1.0; surviving niches have
  per-leg q ≈ 1.07–1.20, so single-leg EV is always negative under
  0.65 rake. The +EV emerges at the combo level
  ((mean_q)^N × 0.65 > 1 for N=4 when q ≥ 1.07). Filtering happens at
  the combo-EV stage (`combo_ev_threshold`, default 0.05).
- weekly stake cap = 25% of bankroll, tax-cap = 9 999 yuan/ticket.

## Niche config

`niches_default.json` encodes the 11 surviving Phase-4 niches (Archetype
B). Each rule may constrain any subset of `option`, `[sp_lo, sp_hi)`,
`league_tier`, `handicap_class`. First match wins; `p_hat_train` becomes
the leg's prior probability. Override at the CLI: `--niches my.json`.

## CLI

```bash
python -m src.phase5a plan --bankroll 100000          # build & save plan
python -m src.phase5a plan --bankroll 50000 \
    --n-legs 4 --kelly 0.0625 --window-days 7
python -m src.phase5a reconcile \
    --plan data/phase5a_plans/2026-W18.json
```

Outputs: stderr `_Saved: <path>_`; stdout markdown plan or reconcile
table. Empty DB / no qualifying niches produce a "no tickets" message
rather than an exception.
