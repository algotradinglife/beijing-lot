# 北单实盘决策台 frontend v1

可运行的 React dashboard。默认生产入口由 Flask API 同源托管 `dist/`，真实场次数据通过本地只读 API 从 500.com SQLite 读取；Vite 只作为显式开发调试模式使用。

- Issue Dashboard
- Main Strategy
- Match Detail
- Ticket Builder
- Selector Shadow
- Live Signals
- Settlement Review
- Strategy Lab

## 本地运行

推荐使用项目根目录的一键管理脚本：

```bash
export BEIDAN_DECISION_API_OPERATOR_TOKEN='replace-with-local-secret'
python3 scripts/manage_decision_dashboard.py start
python3 scripts/manage_decision_dashboard.py health
```

默认 `start/restart` 会先执行前端 production build，再由 `src.decision_api` 同源服务 `/` 和 `/api`。

如果要通过 Tailscale Serve 的 MagicDNS 域名访问：

```bash
BEIDAN_DECISION_API_OPERATOR_TOKEN='replace-with-local-secret' \
python3 scripts/manage_decision_dashboard.py restart \
  --magic-dns YOUR_MAGICDNS_HOST.ts.net \
  --configure-tailscale-serve
```

完整运维手册见 [docs/operations/decision_dashboard_runbook.md](../../docs/operations/decision_dashboard_runbook.md)。

先刷新 500.com 当前期并写入 SQLite：

```bash
python3 scripts/scrape_500_bjdc.py --live-sp --force --sleep 0
```

实盘时一键管理脚本会托管两个后台刷新进程：

- `scripts/live_score_refresh_loop.py`：低延迟刷新捷报比分、半场和赛果。
- `scripts/live_sp_refresh_loop.py`：低频刷新 500 当前/近期/未结算期的结算 SP 和 live SP XML。

启动真实数据 API：

```bash
python3 -m src.decision_api
```

API 默认监听 `127.0.0.1:8790`，可用 `BEIDAN_DECISION_API_HOST` /
`BEIDAN_DECISION_API_PORT` 覆盖。除本机排障外，不建议直接把 API 端口暴露到局域网或公网。

开发调试时可以显式启动 Vite 热更新模式：

```bash
npm install
BEIDAN_DASHBOARD_FRONTEND_MODE=vite-dev python3 scripts/manage_decision_dashboard.py restart
```

生产默认本机入口：

```text
http://127.0.0.1:8790/
```

远程访问优先使用 Tailscale Serve，把 Tailnet HTTPS 入口代理到本机 API/static 入口：

```bash
tailscale serve --bg http://127.0.0.1:8790
```

前端默认使用同源 `/api`，生产模式不需要 Vite proxy，也不会让远程浏览器去请求它自己的
`127.0.0.1:8790`。只有明确要做 Tailnet 直连调试时，才使用
`--frontend-mode vite-dev`、`npm run dev:tailscale` 或 `--frontend-host 0.0.0.0`。Vite 默认不再放开所有 Host；
MagicDNS 直连 Vite 调试才需要 `VITE_ALLOWED_HOSTS=YOUR_MAGICDNS_HOST.ts.net`。

写操作默认需要 operator token。API 侧设置 `BEIDAN_DECISION_API_OPERATOR_TOKEN`；浏览器侧只在需要执行
确认 draft、实盘 workflow、复盘写入等 POST 操作时设置：

```js
localStorage.setItem('BEIDAN_OPERATOR_TOKEN', 'replace-with-local-secret')
```

没有 token 时页面仍可读取数据，但 POST 操作会被拒绝。

如果 MagicDNS 域名打不开但 IP 能打开，优先检查浏览器/系统代理。Tailscale 地址应绕过
HTTP 代理，至少把这些加入代理 bypass/no_proxy：

```text
YOUR_MAGICDNS_HOST.ts.net
*.ts.net
100.64.0.0/10
```

前端默认请求真实 API，不会静默 fallback mock。Operations 页面默认只显示安全摘要，不展示
端口、PID、日志路径、SQLite 路径、Tailscale IP 或 MagicDNS 域名。需要本机临时排障时可设置
`BEIDAN_DECISION_API_PUBLIC_DIAGNOSTICS=1`，不要在对外访问时常开。

`current` 会解析为 500.com 当前期，Issue Dashboard 默认展示整期比赛；真实模式下前端默认 5 分钟自动刷新一次，可用 `VITE_REFRESH_MS` 调整。主策略页面会同时读取：

- `GET /api/issues/current/dashboard`
- `GET /api/issues/current/main-strategy`

如果当前期没有正式主策略 EV 票池，页面只显示实时信号和 `live_market_proxy_not_main_ev_pool` 状态，不把 mock 或历史票池伪装成当前出票。

## 验证

```bash
npm test
npm run build
```

## 数据接入

`src/data/apiAdapter.ts` 是真实 API / mock API 的替换边界。实盘默认 fetch，不静默回退 mock：

```ts
new ApiDashboardAdapter({ mode: 'fetch', baseUrl: '' })
```

测试或纯前端开发可以显式设置：

```bash
VITE_DATA_MODE=mock npm run dev -- --port 4173
```

Canonical fetch read paths:

- `GET /api/issues/:issue/dashboard`
- `GET /api/matches/:match_id`
- `GET /api/issues/:issue/tickets`
- `GET /api/issues/:issue/main-strategy`
- `GET /api/issues/:issue/signals`
- `GET /api/issues/:issue/settlement`
- `GET /api/strategies/lab`
- `GET /api/issues/:issue/selector-shadow`

The adapter owns the snake_case API payload → camelCase frontend view-model transform. This keeps React components stable while allowing the backend to use the canonical data/API spec naming.

mock 数据位于 `src/data/mockData.ts`，只用于测试或显式 mock 模式。

## 主策略数据链

主策略 A/B 固化为：

- `b384_dd32_smooth100`：稳健/回撤控制。
- `b384_dd32_smooth80_convex19`：收益/凸性。

后端读取：

- `results/n7_sleeve_mix_capital_plus2026_linefill_20260630/sleeve_mix_summary.csv`
- `results/n7_sleeve_mix_capital_plus2026_linefill_20260630/sleeve_mix_annual.csv`
- `results/n7_sleeve_mix_capital_plus2026_linefill_20260630/sleeve_mix_issue_profit.csv`
- `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_selected_tickets.csv`
- `data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite`

line-gap 只作为诊断标签；SP drift 只作为诊断/极小 paper convex sleeve，不进入主 depth gate。
