# Strategy Interface Rollout Handoff

Date: 2026-07-04

This handoff freezes the boundary between the strategy worktree and the live
decision dashboard. Future model or decision-chain versions should be promoted
by publishing a release manifest and artifacts, not by editing frontend logic.

## Current Production Boundary

- Release registry: `config/strategy_release.json`
- Contract schema: `schemas/strategy_release_registry_v1.schema.json`
- Active strategy family: `N=7 fixed-384 main strategy`
- Active dashboard candidates:
  - `b384_dd32_smooth100`: steadier drawdown-control arm
  - `b384_dd32_smooth80_convex19`: higher convexity arm
- Decision variants exposed to the UI:
  - `active_v3.3.3` formal/default decision chain
  - `shadow_v4.2.*` manual diagnostic/experimental views when artifacts exist

`active_v3` is retired and must not be presented as a live selectable betting
version. Existing `shadow_v3.3.3` artifacts remain readable only as
`active_v3.3.3` legacy aliases.

The API is responsible for resolving which variants are available. The frontend
does not invent shadow versions and does not read shadow CSVs directly.

## Data And Artifact Chain

- Live match and SP database: `data/derived/500_bjdc/500_bjdc.sqlite`
- Main strategy artifacts:
  `results/n7_sleeve_mix_capital_plus2026_linefill_20260630`
- EV ticket pool:
  `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_selected_tickets.csv`
- Joint q/confidence/drift diagnostics:
  `results/n7_q_conf_drift_joint_2014_10h_trusted_plus2026_linefill_20260630/joint_leg_rows.csv`
- Structured shadow decisions:
  `results/structured_decision_chain_shadow`

SQLite databases, Excel files, and bulky raw data remain local artifacts and
must not be committed.

## API Contract

- `GET /api/strategy-release` returns the active release, artifact health, and
  decision variants.
- `GET /api/issues/:issue/dashboard?decision_variant=<id>` returns issue rows
  with `strategy_version_context` and `selected_decision_variant`.
- `GET /api/matches/:match_id?decision_variant=<id>` returns match detail under
  the same selected variant.
- `GET /api/issues/:issue/main-strategy?decision_variant=<id>` returns the EV
  ticket pool and risk state.
- `GET /api/issues/:issue/settlement?decision_variant=<id>` returns settlement
  review under the same variant context.

If the requested variant is unavailable, the API selects the manifest default
context and marks `selection_status: unavailable`. If the formal
`active_v3.3.3` artifact is missing or incomplete, the API exposes an
artifact-missing/no-buy placeholder; frontend must not substitute retired
`active_v3` or mock data.

## Frontend Boundary

- Real mode is default. Mock data is only allowed with `VITE_DATA_MODE=mock`.
- The selected decision version is one shared state in `App.tsx`.
- Issue Board, Match Detail, Settlement Review, and Main Strategy are loaded
  through the adapter using the same `decision_variant` query.
- Version warnings/degraded states are shown as compact UI status text.
- Historical settled issues only show variants declared by the API manifest.

## Validation Commands

Use the populated live SQLite path when the current repo root does not have the
large local DB:

```bash
export BEIDAN_LIVE_SQLITE=/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex/data/derived/500_bjdc/500_bjdc.sqlite
python3.14 scripts/smoke_decision_dashboard_data_chain.py --issue current --json
```

Full rollout validation:

```bash
python3.14 scripts/validate_strategy_release.py --allow-missing --json
python3.14 -m py_compile src/decision_api/app.py scripts/validate_strategy_release.py scripts/smoke_decision_dashboard_data_chain.py
pytest -q tests/decision_api
npm --prefix apps/decision-dashboard test -- --run
npm --prefix apps/decision-dashboard run build
git diff --check
git ls-files | rg '(^data/|\.(db|sqlite|sqlite3|xlsm|xlsx)$)' || true
```

## Reviewer Status

- `t_44b0b49a`: strategy release manifest contract implemented.
- `t_1ffe4602` / `t_7fd9936e`: contract enforcement fix reviewed PASS.
- `t_b87e1988` / `t_078cefc2` / `t_8bee72e5`: API manifest-bound
  active/shadow loading reviewed PASS.
- `t_bbb49ea6` / `t_ea796e48` / `t_186528b5`: frontend version boundary and
  tracked data adapter fix reviewed PASS.

## Known Local Environment Note

The main repo root may contain a tiny local
`data/derived/500_bjdc/500_bjdc.sqlite` created by an earlier failed smoke. It
is not a usable live database. The smoke script now rejects that case before
creating the Flask app. Point `--db` or `BEIDAN_LIVE_SQLITE` at the populated
live DB when running from a repo root that does not carry local data artifacts.
