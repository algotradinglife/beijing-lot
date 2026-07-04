# 北单实盘决策台运行手册

本手册覆盖决策台的启动、重启、健康检查和远程访问诊断。安全默认值是 API 只监听本机；生产前端由 API 同源托管 `apps/decision-dashboard/dist`。远程访问优先走 Tailscale Serve 代理本机 API/static 入口，不直接把端口暴露到局域网或公网。

## 一键管理

从项目根目录运行：

```bash
export BEIDAN_DECISION_API_OPERATOR_TOKEN='replace-with-local-secret'
python3 scripts/manage_decision_dashboard.py start
python3 scripts/manage_decision_dashboard.py health
python3 scripts/manage_decision_dashboard.py restart
```

如果远程入口使用 Tailscale MagicDNS，启动或重启时让脚本同步配置 Tailscale Serve：

```bash
BEIDAN_DECISION_API_OPERATOR_TOKEN='replace-with-local-secret' \
python3 scripts/manage_decision_dashboard.py restart \
  --magic-dns YOUR_MAGICDNS_HOST.ts.net \
  --configure-tailscale-serve
```

默认脚本使用 `api-static` 生产模式：

- 先执行 `npm run build` 生成 `apps/decision-dashboard/dist`。
- 启动 API：`python3 -m src.decision_api`，默认监听本机回环地址。
- API 同源服务 `/`、`/assets/*` 和 `/api/*`；不再启动 Vite dev server。
- 启动后预热首屏接口：轻量期号列表和当前期 summary dashboard。

需要热更新调试时才显式使用：

```bash
python3 scripts/manage_decision_dashboard.py restart --frontend-mode vite-dev
```

健康检查结果会写入：

```text
tmp/decision_dashboard/runtime_status.json
```

Operations 页面只展示安全摘要：服务健康、进程状态、最近检查、workflow/复盘状态。PID、绑定地址、日志路径、SQLite 路径、Tailscale IP、MagicDNS 域名不会默认返回给浏览器。临时本机排障可设置 `BEIDAN_DECISION_API_PUBLIC_DIAGNOSTICS=1`，对外访问时不要常开。

## 首屏缓存

API 对首屏读路径做短 TTL 缓存：

- `GET /api/issues?include_replay=0`
- `GET /api/issues/:issue/dashboard?view=summary`

默认 TTL 为 30 秒，可用环境变量调整：

```bash
BEIDAN_DECISION_API_CACHE_TTL_SEC=30
```

设置为 `0` 可关闭缓存。确认决策快照、运行 live workflow、写入赛后复盘等 POST 会清空缓存；后台比分刷新依赖短 TTL 自然更新。

## 访问方式

本机访问：

```text
http://127.0.0.1:8790/
```

API 健康检查只建议在服务器本机执行：

```text
http://127.0.0.1:8790/healthz
```

远程访问优先使用 Tailscale Serve，把 Tailnet 入口代理到本机 API/static 入口：

```bash
tailscale serve --bg http://127.0.0.1:8790
```

前端通过同源 `/api` 访问本机 API。真实模式不会静默 fallback mock；如果 API 不通，页面应该直接报错。生产模式没有 Vite Host 白名单问题；只有 `--frontend-mode vite-dev` 调试时才需要 `VITE_ALLOWED_HOSTS`。

重要：Tailnet/Funnel 页面不是只读页面；同源 `/api` 也能访问 POST API。所有 mutating POST 默认需要
`BEIDAN_DECISION_API_OPERATOR_TOKEN` 和浏览器 `localStorage.BEIDAN_OPERATOR_TOKEN` 匹配：

```js
localStorage.setItem('BEIDAN_OPERATOR_TOKEN', 'replace-with-local-secret')
```

没有 token 时，确认 draft、实盘 workflow、复盘写入等操作会返回 403。Funnel 未加额外身份层前不要用于公网演示。

## Tailscale Serve / Funnel

Funnel 是公网入口，只适合短时演示或受控排障。开启前确认不展示敏感数据，关闭 API diagnostics，并确认 operator token 已启用：

```bash
tailscale funnel --bg 8790
```

开启后把公网地址写入环境变量再重跑 health，可让本机 runtime 快照记录：

```bash
BEIDAN_DASHBOARD_FUNNEL_URL=https://your-funnel-url \
python3 scripts/manage_decision_dashboard.py health --host-smoke YOUR_MAGICDNS_HOST.ts.net
```

## 排障顺序

1. 检查本机服务：

```bash
python3 scripts/manage_decision_dashboard.py health
curl -sS http://127.0.0.1:8790/healthz
curl -sSI http://127.0.0.1:8790/ | head -n 1
```

2. 检查 Tailscale Serve：

```bash
tailscale serve status
```

3. 检查端口监听：

```bash
ss -ltnp '( sport = :4173 or sport = :8790 )'
```

4. 检查日志：

```text
tmp/decision_dashboard/decision_api.log
tmp/decision_dashboard/decision_dashboard_vite.log
tmp/decision_dashboard/decision_dashboard_build.log
```

5. 如果本机能访问但 Tailnet 入口不能访问，优先检查系统或浏览器代理。Tailscale 地址建议加入 bypass：

```text
YOUR_MAGICDNS_HOST.ts.net
*.ts.net
100.64.0.0/10
```

## 数据链路

前端默认请求同源 `/api`，生产模式由 Flask 直接处理：

```text
http://127.0.0.1:8790
```

不要在远程页面里显式设置 `VITE_API_BASE_URL=http://127.0.0.1:8790`。推荐保持空值，让前端使用同源 `/api`；跨域 API 默认不开 CORS，如确有需要，用 `BEIDAN_DECISION_API_CORS_ORIGINS` 配置精确白名单。

实盘数据仍来自 SQLite 和本地主策略结果文件；Operations 页面只展示运行状态，不改变策略或下注算法。
