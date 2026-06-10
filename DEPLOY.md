# Beijing-Lot 服务器迁移/部署指南

> 更新于 2026-06-10。
> **新主机环境：Windows + WSL2（Ubuntu）**
> 旧主机：macOS（launchd）→ 新主机：WSL2（systemd）

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

**autoplan.service**

```bash
cat > "$UNIT_DIR/beidanlot-autoplan.service" <<EOF
[Unit]
Description=Beijing-Lot Auto Planner
After=network.target

[Service]
Type=simple
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO/src
ExecStart=$PYTHON -m auto.autoplan
Restart=always
RestartSec=10
StandardOutput=append:$DATA/logs/autoplan.stdout.log
StandardError=append:$DATA/logs/autoplan.stderr.log

[Install]
WantedBy=default.target
EOF
```

**autocheck.service**

```bash
cat > "$UNIT_DIR/beidanlot-autocheck.service" <<EOF
[Unit]
Description=Beijing-Lot Auto Checker
After=network.target

[Service]
Type=simple
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO/src
ExecStart=$PYTHON -m auto.autocheck
Restart=always
RestartSec=10
StandardOutput=append:$DATA/logs/autocheck.stdout.log
StandardError=append:$DATA/logs/autocheck.stderr.log

[Install]
WantedBy=default.target
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
systemctl --user enable --now beidanlot-autoplan
systemctl --user enable --now beidanlot-autocheck
systemctl --user enable --now beidanlot-live-collector

# 允许用户服务在登出后继续运行
sudo loginctl enable-linger $USER
```

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
