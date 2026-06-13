# Beijing-Lot 服务器迁移/部署指南

> 更新于 2026-06-10。
> **新主机环境：Windows + WSL2（Ubuntu）**
> 旧主机：macOS（launchd）→ 新主机：WSL2（systemd）

---

## 〇、实际部署现状（2026-06-11，权威记录）

> **本节记录已完成的真实落地配置；与下方第一～八节的规划稿如有出入，以本节为准。**
> 下方规划稿保留作背景参考，但其中若干命令与实际不符（见各处「⚠️ 实际」标注）。

**主机 / 路径**

| 项 | 实际值 |
|----|--------|
| 用户 / 主机 | `drwho1985` @ `DrWhoTrade1985`（WSL2，systemd PID1） |
| 仓库 | `/home/drwho1985/workspace/soccer/beijing-lot` |
| 数据目录 | **仓库内 `data/`**（代码用相对路径，**不要**用 `~/data/beijing-lot`） |
| 旧机数据源 | `huhan@dr:/Volumes/Data Drive/data/derived/beijing-lot/`（约 195 MB） |
| Python | 系统 `python3.14` + 仓库内 venv `.venv`（`ensurepip` 缺失，用 `get-pip.py` 引导 pip） |
| 依赖 | 仓库 `requirements.txt`（已精简为真实 import；旧的 398 包全局 freeze 已弃用） |
| `PYTHONPATH` | `$REPO:$REPO/src`（代码混用 `from src.x` 与 `from x` 两种风格，需同时在路径上） |

**数据迁移用 `sqlite3 .backup` 取一致性快照**（折叠 WAL，避免拷到撕裂副本）：

```bash
# 旧机生成快照
ssh huhan@dr 'cd "/Volumes/Data Drive/data/derived/beijing-lot"; \
  for db in beidan_live webui beidan_history; do sqlite3 "$db.db" ".backup /tmp/$db.db"; done'
# 新机：支撑文件 + 3 个快照库 → 仓库内 data/
rsync -az --exclude="*.db" --exclude="*.db-wal" --exclude="*.db-shm" \
  huhan@dr:"/Volumes/Data Drive/data/derived/beijing-lot/" data/
for db in beidan_live webui beidan_history; do rsync -az huhan@dr:/tmp/$db.db data/$db.db; done
```

**环境搭建**

```bash
cd /home/drwho1985/workspace/soccer/beijing-lot
python3 -m venv .venv
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python   # 系统缺 ensurepip
.venv/bin/python -m pip install -r requirements.txt
```

**已运行的 systemd --user 单元**（`linger=yes`，开机/登出自启）

| 单元 | 类型 | 调度 / 说明 |
|------|------|-------------|
| `beidanlot-webui.service` | 常驻 | `-m src.webui --host 127.0.0.1 --port 8000`；`EnvironmentFile=~/.config/beidanlot/webui.env` |
| `beidanlot-live-collector.service` | 常驻 | `-m live_collector --interval-min 300 --interval-max 900` |
| `beidanlot-autoplan.service` + `.timer` | **oneshot + timer** | 每小时（`OnCalendar=hourly`） |
| `beidanlot-autocheck.service` + `.timer` | **oneshot + timer** | 每天 10:00 |
| `cloudflared-trading.service` | 常驻 | `cloudflared tunnel --config <cfg> --metrics 127.0.0.1:20241 run` |
| `cloudflared-watchdog.service` + `.timer` | **oneshot + timer** | 每 2 分钟，边缘连接为 0 就重启 tunnel |
| `beidanlot-sp-forward.service` + `.timer` | **oneshot + timer** | 每周一 09:00，纸面 forward-test 评估，写 ledger + 报告 |

> **⚠️ 关键纠正**：autoplan / autocheck 是**跑完即退的 one-shot 脚本**，绝不能配成 `Restart=always`
> 常驻服务（会被 systemd 疯狂重启）。正确做法是 `Type=oneshot` service + `.timer` 定时触发，
> 周期对应旧机 launchd 的 `StartInterval=3600`（每小时）与 `StartCalendarInterval Hour=10`（每天 10:00）。

**跨平台修复（已提交 `bc4a2f8`）**：`src/webui/notify.py` 的 iMessage 走 macOS `osascript`，
非 mac 主机会抛未捕获的 `FileNotFoundError` 拖垮 autoplan/autocheck → 已改为捕获并降级为日志。
WSL 上桌面/iMessage 通知不可用（仅记日志）；如需通知可后续接飞书。

**Cloudflare Tunnel**：tunnel `6f11c8e0-...` 仅本机运行（旧机已停，无 replica 冲突）。
`config.yml` 保留全部 4 条 ingress，但只有 `trading.drwhospaper.site → :8000` 在本机；
其余 3 个（option-timing / wx / wxmonitor）本机无对应服务会 502（其中 `wx` 仍在旧机 :3000）。

**登录方式（已从 Cloudflare Access 改为 app 级算术门）**：
- 原 trading 域名的 **Cloudflare Access 应用已删除**（不再要邮箱 OTP）。
- webui 内置**算术门 + 固定口令**（`src/webui/app.py` 的 `/gate` + `before_request` 守卫）：
  答对算术题并输入口令后置 30 天 session。提交 `70af408` / 修复竞态 `83bbaca`。
- 口令与强 `BEIDAN_SECRET` 存于 `~/.config/beidanlot/webui.env`（600，**不入 git**）：
  ```
  BEIDAN_GATE_PASS=<口令>
  BEIDAN_SECRET=<openssl/secrets 生成的强随机串>
  ```
  未设 `BEIDAN_GATE_PASS` → 门自动关闭（本地/测试无门）。
- ⚠️ 安全级别低（算术题只挡机器人，口令是唯一关卡，页面展示真实 bankroll），仅供少数信任的人。

**⚠️ WARP 拦截 + watchdog**：本机/网络上的 WARP 会间歇劫持 cloudflared 到边缘的 TLS
（edge IP 落在 `198.18.x`，报 `TLS handshake EOF` / `no free edge addresses`），导致公网 530。
此时 cloudflared **进程仍活着**，`Restart=always` 不触发 → 必须靠 `cloudflared-watchdog.timer`：
每 2 分钟读 `--metrics 127.0.0.1:20241` 的 `cloudflared_tunnel_ha_connections`，为 0 则 `restart`。
（注意 `--metrics` 必须放在 `run` **之前**，放在 `run` 后会被拒绝并打印 usage。）

**已验证**：`snapshots=742067`、`integrity=ok`、`http://localhost:8000/ → 302`、
`https://trading.drwhospaper.site/` 公网经算术门 + 口令登录后 dashboard 200、watchdog 报 healthy、collector 启动即写入新快照。

**遗留 / 可选**：`sqlite3` CLI 未装（需 sudo；校验可用 `.venv/bin/python` 的 sqlite3 模块）；
`camoufox`/`pycryptodome` 未装（惰性 import，仅 soccerway 爬取 / 刷 cookie 需要）；
旧 mac 脚本 `scripts/live_collector_daemon.sh`（launchctl）在 WSL 下废弃，改用 systemd。

---

## 一、前提条件

在 WSL2（Ubuntu）内确认以下工具已就绪：

```bash
# 检查 WSL 版本（需要 WSL2，否则 systemd 不可用）
wsl.exe --list --verbose          # 在 Windows PowerShell 里运行

# WSL 内检查 systemd 是否启用
systemctl --version               # 能输出版本号说明 systemd 已启用
```

若 systemd 未启用，在 WSL 的 `/etc/wsl.conf` 中添加：

```ini
[boot]
systemd=true
```

然后在 PowerShell 里重启 WSL：`wsl.exe --shutdown`，再重新进入。

其他依赖：

```bash
sudo apt update && sudo apt install -y git rsync sqlite3 curl
```

Python（miniforge3，安装到 WSL 内）：

```bash
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p ~/miniforge3
echo 'export PATH="$HOME/miniforge3/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## 二、代码同步

```bash
git clone git@github.com:algotradinglife/beijing-lot.git ~/code/trading/beijing-lot
```

安装 Python 依赖：

```bash
pip install -r ~/code/trading/beijing-lot/requirements.txt
```

---

## 三、数据同步

数据文件不在 git 里，需从旧 macOS 主机拉取（约 195 MB）。

迁移前先在**旧机器**上做 WAL checkpoint，确保数据完整：

```bash
# 旧机器（macOS）上执行
sqlite3 "/Volumes/Data Drive/data/derived/beijing-lot/beidan_live.db" \
  "PRAGMA wal_checkpoint(TRUNCATE);"
```

然后在**新机器（WSL）**上执行（替换 `OLD_HOST` 为旧机器地址或 IP）：

```bash
mkdir -p ~/data/beijing-lot

rsync -avz --progress \
  OLD_HOST:"/Volumes/Data\ Drive/data/derived/beijing-lot/" \
  ~/data/beijing-lot/
```

> 如果旧机器没有开 SSH，也可以在 Windows 文件管理器里把数据目录复制到某个路径，
> 然后在 WSL 内通过 `/mnt/c/...` 访问。例如：
> ```bash
> rsync -avz /mnt/d/beijing-lot-data/ ~/data/beijing-lot/
> ```

需要同步的关键文件：

| 文件 | 大小 | 说明 |
|------|------|------|
| `beidan_live.db` | ~123 MB | 主数据库（快照、比赛、结算） |
| `beidan_history.db` | ~7 MB | 历史赔率库（回测用） |
| `webui.db` | ~4 MB | WebUI 策略配置、bankroll 状态 |
| `500com_cookies.json` | 4 KB | 爬虫登录 Cookie |
| `raw/` | ~33 MB | 历史原始数据 |

---

## 四、目录结构与环境变量

在 `~/.bashrc` 里追加：

```bash
export BEIDAN_DATA_DIR="$HOME/data/beijing-lot"
export BEIDAN_REPO_DIR="$HOME/code/trading/beijing-lot"
```

```bash
source ~/.bashrc
mkdir -p ~/data/beijing-lot/logs
```

> 注意：代码中部分路径仍为硬编码（指向旧 macOS 的 `/Volumes/Data Drive/...`），
> 见 `MIGRATION.md` 中的 `hardcoded_path_hits`。
> 如遇路径问题，检查 `src/` 下引用 `data/` 的位置并手动修正。

---

## 五、systemd 服务配置（替代 macOS launchd）

WSL2 使用 systemd 管理后台服务。为三个服务分别创建 unit 文件：

```bash
REPO="$HOME/code/trading/beijing-lot"
DATA="$HOME/data/beijing-lot"
PYTHON="$HOME/miniforge3/bin/python3"
USER=$(whoami)
UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$UNIT_DIR"
```

**webui.service**

```bash
cat > "$UNIT_DIR/beidanlot-webui.service" <<EOF
[Unit]
Description=Beijing-Lot WebUI
After=network.target

[Service]
Type=simple
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO/src
ExecStart=$PYTHON -m src.webui --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:$DATA/logs/webui.stdout.log
StandardError=append:$DATA/logs/webui.stderr.log

[Install]
WantedBy=default.target
EOF
```

**autoplan / autocheck（⚠️ 实际：oneshot + timer，不是常驻服务）**

> 下面这两个 `Restart=always` 写法是**错的**——autoplan/autocheck 跑完即退，会被疯狂重启。
> 实际部署用 `Type=oneshot` service + `.timer`（见第〇节）。正确写法：

```bash
# autoplan：oneshot service + 每小时 timer
cat > "$UNIT_DIR/beidanlot-autoplan.service" <<EOF
[Unit]
Description=Beijing-Lot Auto Planner (oneshot)
After=network.target
[Service]
Type=oneshot
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO:$REPO/src
ExecStart=$PYTHON -m auto.autoplan
StandardOutput=append:$DATA/logs/autoplan.stdout.log
StandardError=append:$DATA/logs/autoplan.stderr.log
EOF
cat > "$UNIT_DIR/beidanlot-autoplan.timer" <<EOF
[Unit]
Description=Run autoplan hourly
[Timer]
OnCalendar=hourly
Persistent=true
[Install]
WantedBy=timers.target
EOF

# autocheck：oneshot service + 每天 10:00 timer
cat > "$UNIT_DIR/beidanlot-autocheck.service" <<EOF
[Unit]
Description=Beijing-Lot Auto Checker (oneshot)
After=network.target
[Service]
Type=oneshot
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO:$REPO/src
ExecStart=$PYTHON -m auto.autocheck
StandardOutput=append:$DATA/logs/autocheck.stdout.log
StandardError=append:$DATA/logs/autocheck.stderr.log
EOF
cat > "$UNIT_DIR/beidanlot-autocheck.timer" <<EOF
[Unit]
Description=Run autocheck daily at 10:00
[Timer]
OnCalendar=*-*-* 10:00:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
```

**live_collector.service**

```bash
cat > "$UNIT_DIR/beidanlot-live-collector.service" <<EOF
[Unit]
Description=Beijing-Lot Live Collector
After=network.target

[Service]
Type=simple
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO/src
ExecStart=$PYTHON -m live_collector --interval-min 300 --interval-max 900
Restart=always
RestartSec=10
StandardOutput=append:$DATA/logs/live_collector.stdout.log
StandardError=append:$DATA/logs/live_collector.stderr.log

[Install]
WantedBy=default.target
EOF
```

加载并启动：

```bash
systemctl --user daemon-reload
systemctl --user enable --now beidanlot-webui
systemctl --user enable --now beidanlot-live-collector
systemctl --user enable --now beidanlot-autoplan.timer    # timer，不是 .service
systemctl --user enable --now beidanlot-autocheck.timer   # timer，不是 .service

# 允许用户服务在登出后继续运行
sudo loginctl enable-linger $USER
```

> 查看 timer 排程：`systemctl --user list-timers 'beidanlot-*'`

验证状态：

```bash
systemctl --user status beidanlot-webui beidanlot-autoplan beidanlot-autocheck beidanlot-live-collector
```

检查 WebUI：

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/
# 期望：302
```

---

## 六、Cloudflare Tunnel 配置

Tunnel 绑定在 Cloudflare 账号上，凭证文件从旧机器复制过来即可，不需要重新创建。

**安装 cloudflared（WSL 内）：**

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
  -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
```

**从旧机器拉取凭证：**

```bash
mkdir -p ~/.cloudflared
rsync -avz OLD_HOST:"~/.cloudflared/" ~/.cloudflared/
```

检查 `~/.cloudflared/config.yml`，确认内容如下（端口与 webui 一致）：

```yaml
tunnel: 6f11c8e0-219a-4a6b-8f24-624368b33b22
credentials-file: /home/<你的用户名>/.cloudflared/6f11c8e0-219a-4a6b-8f24-624368b33b22.json
protocol: http2   # WARP 环境必须保留，否则报 1033

ingress:
  - hostname: trading.drwhospaper.site
    service: http://localhost:8000
  - service: http_status:404
```

> 注意：`credentials-file` 路径需改为 WSL 内的绝对路径（`/home/...`），不能用 `~`。

用 systemd 管理 tunnel：

```bash
cat > "$HOME/.config/systemd/user/cloudflared-trading.service" <<EOF
[Unit]
Description=Cloudflare Tunnel (trading)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/cloudflared tunnel --config $HOME/.cloudflared/config.yml run
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user enable --now cloudflared-trading
```

验证公网可访问：

```bash
curl -s -o /dev/null -w "%{http_code}" https://trading.drwhospaper.site/
# 期望：302
```

---

## 七、迁移后验收清单

- [ ] `systemctl --user status beidanlot-webui` 显示 `active (running)`
- [ ] `systemctl --user status beidanlot-live-collector` 显示 `active (running)`
- [ ] `curl http://localhost:8000/` 返回 302
- [ ] `https://trading.drwhospaper.site/` 公网可访问
- [ ] WebUI 策略页面加载正常，历史期次数据可查
- [ ] `sqlite3 ~/data/beijing-lot/beidan_live.db "SELECT count(*) FROM snapshots;"` 返回正确行数
- [ ] 查看 live collector 日志无报错：`tail -f ~/data/beijing-lot/logs/live_collector.stdout.log`

---

## 八、旧机器善后

确认新机器运转正常后，停止旧机器上的所有服务，**避免两台机器同时写数据库**：

```bash
# 旧机器（macOS）上执行
launchctl unload ~/Library/LaunchAgents/com.beidanlot.webui.plist
launchctl unload ~/Library/LaunchAgents/com.beidanlot.autoplan.plist
launchctl unload ~/Library/LaunchAgents/com.beidanlot.autocheck.plist
launchctl unload ~/Library/LaunchAgents/com.beidanlot.live_collector.plist
launchctl unload ~/Library/LaunchAgents/com.cloudflare.cloudflared.trading-tunnel.plist
```
