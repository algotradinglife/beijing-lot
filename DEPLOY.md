# Beijing-Lot 服务器迁移/部署指南

> 更新于 2026-06-10。适用于将整套服务从旧 macOS 主机迁移到新主机。

---

## 一、前提条件

- 新主机为 macOS（launchd 服务依赖 macOS）
- 已安装 [miniforge3](https://github.com/conda-forge/miniforge)（Python 3.11+）
- 已安装 cloudflared（`brew install cloudflare/cloudflare/cloudflared`）
- SSH 公钥已加入 GitHub（用于 clone）
- 可从旧机器通过 SSH 拉取文件

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

数据文件不在 git 里，需从旧机器手动拉取（约 195 MB）。

**在新机器上执行**（替换 `OLD_HOST` 为旧机器地址）：

```bash
mkdir -p ~/data/beijing-lot

rsync -avz --progress \
  OLD_HOST:"/Volumes/Data\ Drive/data/derived/beijing-lot/" \
  ~/data/beijing-lot/
```

迁移前在旧机器上先做 WAL checkpoint，确保数据完整：

```bash
# 旧机器上执行
sqlite3 "/Volumes/Data Drive/data/derived/beijing-lot/beidan_live.db" \
  "PRAGMA wal_checkpoint(TRUNCATE);"
```

需要同步的关键文件：

| 文件 | 大小 | 说明 |
|------|------|------|
| `beidan_live.db` | ~123 MB | 主数据库（快照、比赛、结算） |
| `beidan_history.db` | ~7 MB | 历史赔率库（回测用） |
| `webui.db` | ~4 MB | WebUI 策略配置、bankroll 状态 |
| `500com_cookies.json` | 4 KB | 爬虫登录 Cookie |
| `raw/` | ~33 MB | 历史原始数据 |

---

## 四、目录结构配置

旧机器的路径约定是 `/Volumes/Data Drive/...`，新机器改为 `~/data/beijing-lot`。

需要在 shell 环境（`~/.zshrc` 或 `~/.bashrc`）里设置：

```bash
export BEIDAN_DATA_DIR="$HOME/data/beijing-lot"
export BEIDAN_REPO_DIR="$HOME/code/trading/beijing-lot"
```

> 注意：当前代码中部分路径仍为硬编码，见 `MIGRATION.md` 中的 `hardcoded_path_hits`。
> 如遇路径问题请手动核查 `src/` 下引用 `data/` 的位置。

创建日志目录：

```bash
mkdir -p ~/data/beijing-lot/logs
```

---

## 五、launchd 服务配置

仓库 `launchd/` 目录下有三个服务的 plist 模板，**安装前需批量替换路径**：

```bash
REPO="$HOME/code/trading/beijing-lot"
DATA="$HOME/data/beijing-lot"
PYTHON="$HOME/miniforge3/bin/python3"
USER=$(whoami)

for f in "$REPO/launchd/"*.plist; do
  sed \
    -e "s|/Volumes/Data Drive/workspace/trading/beijing-lot|$REPO|g" \
    -e "s|/Volumes/Data Drive/workspace/trading/beijing-lot/data|$DATA|g" \
    -e "s|/Users/huhan/miniforge3|$HOME/miniforge3|g" \
    -e "s|/Users/huhan|$HOME|g" \
    "$f" > ~/Library/LaunchAgents/$(basename "$f")
done
```

加载服务：

```bash
launchctl load ~/Library/LaunchAgents/com.beidanlot.webui.plist
launchctl load ~/Library/LaunchAgents/com.beidanlot.autoplan.plist
launchctl load ~/Library/LaunchAgents/com.beidanlot.autocheck.plist
```

验证：

```bash
launchctl list | grep beidanlot
# 每个服务应显示 PID（非 -），exit code 为 0
```

检查 WebUI 是否正常：

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/
# 期望：302
```

---

## 六、Cloudflare Tunnel 配置

Tunnel 绑定在 Cloudflare 账号上，不需要重新创建，只需把凭证文件复制过来。

**从旧机器拉取：**

```bash
mkdir -p ~/.cloudflared
rsync -avz OLD_HOST:"~/.cloudflared/" ~/.cloudflared/
```

拉取后检查 `~/.cloudflared/config.yml`，确认 `service` 地址与新机器端口一致：

```yaml
tunnel: 6f11c8e0-219a-4a6b-8f24-624368b33b22
credentials-file: ~/.cloudflared/6f11c8e0-219a-4a6b-8f24-624368b33b22.json
protocol: http2   # WARP 环境必须保留，否则报 1033

ingress:
  - hostname: trading.drwhospaper.site
    service: http://localhost:8000
  - service: http_status:404
```

安装并启动 tunnel 服务：

```bash
sudo cloudflared service install
sudo launchctl load /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
```

验证公网可访问：

```bash
curl -s -o /dev/null -w "%{http_code}" https://trading.drwhospaper.site/
# 期望：302
```

---

## 七、迁移后验收清单

- [ ] `launchctl list | grep beidanlot` 三个服务均有 PID
- [ ] `curl http://localhost:8000/` 返回 302
- [ ] `https://trading.drwhospaper.site/` 可访问
- [ ] WebUI 策略页面加载正常，历史期次数据可查
- [ ] Live collector 正常采集（检查 `~/data/beijing-lot/logs/live_collector.stdout.log`）
- [ ] `sqlite3 ~/data/beijing-lot/beidan_live.db "SELECT count(*) FROM snapshots;"` 返回正确行数

---

## 八、旧机器善后

确认新机器运转正常后：

1. 停止旧机器上的服务，避免双写数据库：
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.beidanlot.webui.plist
   launchctl unload ~/Library/LaunchAgents/com.beidanlot.autoplan.plist
   launchctl unload ~/Library/LaunchAgents/com.beidanlot.autocheck.plist
   launchctl unload ~/Library/LaunchAgents/com.beidanlot.live_collector.plist
   ```
2. 停止旧机器上的 cloudflared tunnel（否则两端都在监听同一 hostname）。
