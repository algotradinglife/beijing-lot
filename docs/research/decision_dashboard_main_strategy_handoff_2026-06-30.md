# Decision Dashboard Main Strategy Handoff

Date: 2026-06-30

Hermes card: `t_ca4b7664`

## Scope

The new React decision dashboard at `http://127.0.0.1:4173/` now uses real API data by default and exposes the current fixed-384 main strategy candidates:

- `b384_dd32_smooth100`: stable / drawdown-control candidate.
- `b384_dd32_smooth80_convex19`: profit / convex-upside candidate.

This card intentionally stops expanding line-gap/drift research. The UI treats both as diagnostics only.

## Data Chain

Backend entry:

- `python3 -m src.decision_api`
- API port: `127.0.0.1:8790`

Primary data sources:

- Live/current matches: `data/derived/500_bjdc/500_bjdc.sqlite`
- Main A/B summary/annual/review: `results/n7_sleeve_mix_capital_plus2026_linefill_20260630/`
- EV ticket pool: `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_selected_tickets.csv`
- Historical leg context: `data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite`
- q/conf/drift leg diagnostics: `results/n7_q_conf_drift_joint_2014_10h_trusted_plus2026_linefill_20260630/joint_leg_rows.csv`
- Paper diagnostic arms: `results/main_strategy_linegap_drift_depth_20260630/paper_arm_summary.csv`

Current issue behavior:

- `current/latest` is resolved from 500.com SQLite.
- If the current issue has no historical replay EV pool, `/main-strategy` returns `mode=live_monitoring` and `ev_pool.status=no_replay_pool_for_issue`.
- The live proxy is labeled `live_market_proxy_not_main_ev_pool`; it is not production N=7 selector output.

Historical issue behavior:

- Historical issues such as `26051` do not need to exist in 500.com SQLite.
- `/api/issues/26051/main-strategy` reads replay CSV/modeling DB and returns `mode=historical_replay`.

## API Paths

- `GET /healthz`
- `GET /api/issues/:issue/dashboard`
- `GET /api/issues/:issue/main-strategy`
- `GET /api/issues/:issue/tickets`
- `GET /api/issues/:issue/signals`
- `GET /api/issues/:issue/settlement`
- `GET /api/strategies/lab`
- `GET /api/issues/:issue/selector-shadow`

Key payload sections for `/main-strategy`:

- `candidates`: A/B metrics, budget, ROI, maxDD, allocation.
- `ev_pool`: historical core EV ticket pool; filtered to `selector=all` to avoid duplicate research selector rows.
- `risk_state`: fixed-384 budget, risk level, cooldown state, recommended A/B arm.
- `diagnostics`: line-gap/SP drift policy and paper-only arms.
- `review`: recent historical issue profit/hit/risk-state rows for both A/B arms.

## UI Entry

Frontend app:

```bash
cd apps/decision-dashboard
npm run dev -- --host 127.0.0.1 --port 4173
```

Main browser URL:

```text
http://127.0.0.1:4173/
```

Default page is now `Main Strategy`. Other pages remain available for match list, ticket draft, live signals, settlement review, strategy lab, and selector-shadow context.

## Real/Mock Boundary

Real mode is default:

```ts
new ApiDashboardAdapter({ mode: 'fetch', baseUrl: 'http://127.0.0.1:8790' })
```

Mock mode is allowed only when explicitly requested:

```bash
VITE_DATA_MODE=mock npm run dev -- --port 4173
```

Fetch failures are surfaced as UI errors. The adapter does not silently fallback to mock in real mode.

## Validation

Commands run:

```bash
cd apps/decision-dashboard && npm test
cd apps/decision-dashboard && npm run build
python3 -m py_compile src/decision_api/app.py src/decision_api/__main__.py
```

API smoke:

```text
/healthz -> ok=true, current_issue=26069
/api/issues/current/dashboard -> issue=26069, matches=4, capture_status=complete
/api/issues/current/main-strategy -> live_monitoring, A/B candidates present, no_replay_pool_for_issue
/api/issues/26051/main-strategy -> historical_replay, historical_core_ev_pool, 30 tickets
/api/strategies/lab -> b384_dd32_smooth100 + b384_dd32_smooth80_convex19
```

## Reviewer Notes

- Confirm the `selector=all` EV pool filter is the right production-facing ticket pool view. It avoids duplicate research selector rows; A/B extra sleeves are represented in candidate allocation/review rather than duplicated as ticket rows.
- Current issue `26069` has live 500.com rows but no generated production EV pool. This is intentionally shown as live monitoring, not as actionable N=7 output.
- `line-gap` and `SP drift` are visible only as diagnostics/paper context and are not used as hard gates in the UI.
