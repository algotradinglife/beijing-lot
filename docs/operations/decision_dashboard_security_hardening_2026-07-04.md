# Decision Dashboard Security Hardening

Date: 2026-07-04

## Findings

- Vite and the decision API were easy to run on `0.0.0.0`, which exposed the dashboard and API ports to any reachable network path.
- Operations status exposed runtime topology in the browser: URLs, ports, PID, bind host, command, log path, SQLite path, Tailscale IP, and MagicDNS host.
- `/healthz` returned local filesystem paths and model/data locations.
- API CORS was `*`, which allowed any origin to call the API if the port was reachable.

## Changes

- Default API and frontend hosts now bind to `127.0.0.1`.
- Direct `python -m src.decision_api` also defaults to `127.0.0.1`.
- Remote use should go through Tailscale Serve proxying the frontend; the API stays local and is reached through same-origin `/api`.
- Operations API returns a safe runtime summary by default.
- Dashboard and main-strategy payload source paths are redacted unless diagnostics are explicitly enabled.
- Sensitive diagnostics are only exposed when `BEIDAN_DECISION_API_PUBLIC_DIAGNOSTICS=1`.
- CORS is disabled by default. Cross-origin access requires exact `BEIDAN_DECISION_API_CORS_ORIGINS` allow-list entries.
- Operations UI hides URLs, ports, PID, commands, log paths, SQLite path, Tailscale IP, and MagicDNS host.
- Vite no longer uses `allowedHosts: true` by default. MagicDNS access requires `VITE_ALLOWED_HOSTS` or the dashboard manager's `--magic-dns`.
- Mutating `/api/**` POST routes require `BEIDAN_DECISION_API_OPERATOR_TOKEN` plus `X-Beidan-Operator-Token`.

## Operating Guidance

- Keep `VITE_API_BASE_URL` empty in real mode so the frontend uses same-origin `/api`.
- Do not publish the API port through Funnel or direct Tailnet binds.
- Set browser `localStorage.BEIDAN_OPERATOR_TOKEN` only for trusted operator sessions that need POST actions.
- Treat Funnel as temporary demo access only, and keep public diagnostics disabled.
