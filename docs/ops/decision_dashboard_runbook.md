# 北单实盘决策台运行手册

本手册覆盖本地 `4173` 前端和 `8790` 决策 API 的启动、重启、健康检查和远程访问诊断。

## 一键管理

从项目根目录运行：

```bash
python3 scripts/manage_decision_dashboard.py start --host-smoke trade-server.tail0aa0e9.ts.net
python3 scripts/manage_decision_dashboard.py health --host-smoke trade-server.tail0aa0e9.ts.net
python3 scripts/manage_decision_dashboard.py restart --host-smoke trade-server.tail0aa0e9.ts.net
```

脚本会管理两类进程：

- API：`python3 -m src.decision_api`，默认监听 `0.0.0.0:8790`。
- 前端：`npm run dev:tailscale`，默认监听 `0.0.0.0:4173`。

健康检查结果会写入：

```text
tmp/decision_dashboard/runtime_status.json
```

Operations 页面会读取这份快照，展示 PID、绑定地址、健康检查、Host smoke、日志路径和最近 workflow/复盘状态。

## 访问地址

本机访问：

```text
http://127.0.0.1:4173/
http://127.0.0.1:8790/healthz
```

Tailscale IP 访问：

```text
http://100.104.142.57:4173/
http://100.104.142.57:8790/healthz
```

MagicDNS 访问：

```text
http://trade-server.tail0aa0e9.ts.net:4173/
http://trade-server.tail0aa0e9.ts.net:8790/healthz
```

Vite 已配置 `allowedHosts: true`，并通过 `/api` proxy 转发到本机 API。真实模式不会静默 fallback mock；如果 API 不通，页面应该直接报错。

## Tailscale Serve / Funnel

如果浏览器无法直连 `:4173`，可以用 Tailscale Serve 暴露前端：

```bash
tailscale serve --bg --http=4173 http://127.0.0.1:4173
```

如果需要 Funnel 公网访问，在确认安全边界后开启：

```bash
tailscale funnel --bg 4173
```

开启后把公网地址写入环境变量再重跑 health，可让 Operations 页面显示：

```bash
BEIDAN_DASHBOARD_FUNNEL_URL=https://your-funnel-url \
python3 scripts/manage_decision_dashboard.py health --host-smoke trade-server.tail0aa0e9.ts.net
```

## 排障顺序

1. 检查本机服务：

```bash
python3 scripts/manage_decision_dashboard.py health --host-smoke trade-server.tail0aa0e9.ts.net
curl -sS http://127.0.0.1:8790/healthz
curl -sSI http://127.0.0.1:4173/ | head -n 1
```

2. 检查 Host header：

```bash
curl --noproxy '*' -sSI -H 'Host: trade-server.tail0aa0e9.ts.net' http://127.0.0.1:4173/ | head -n 1
```

3. 检查端口监听：

```bash
ss -ltnp '( sport = :4173 or sport = :8790 )'
```

4. 检查日志：

```text
tmp/decision_dashboard/decision_api.log
tmp/decision_dashboard/decision_dashboard_vite.log
```

5. 如果 IP 能访问但 MagicDNS 不能访问，优先检查系统或浏览器代理。Tailscale 地址建议加入 bypass：

```text
trade-server.tail0aa0e9.ts.net
*.ts.net
100.64.0.0/10
```

## 数据链路

前端默认请求同源 `/api`，由 Vite proxy 转发到：

```text
http://127.0.0.1:8790
```

如果显式设置 `VITE_API_BASE_URL=http://127.0.0.1:8790`，前端运行时会在非 localhost 页面上把 API hostname 改成当前页面 hostname，避免远程浏览器请求它自己的 `127.0.0.1`。

实盘数据仍来自 SQLite 和本地主策略结果文件；Operations 页面只展示运行状态，不改变策略或下注算法。
