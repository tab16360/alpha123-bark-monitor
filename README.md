# Alpha123 空投监控与 Bark 推送服务

这是一个专为 iPhone 用户打造的 Alpha123 空投实时监控与 Bark 推送项目。项目采用 Python 3.12 + SQLite 开发，无需 Redis 或 MySQL 等复杂中间件，支持 Docker Compose 一键部署，非常适合部署在 Linux 服务器或 NAS（如群晖、威联通、Unraid）上。

---

## 🌟 主要功能

- ⏱ **定时轮询**：默认每 20 秒请求一次 Alpha123 API，及时捕捉最新空投信息。
- 🪂 **新空投提醒**：发现新空投项目时向 iPhone 发送 Bark 推送。
- 🔄 **信息变动通知**：对比积分门槛、奖励数量、开始时间、状态等字段变化，精确列出前后差异。
- ⏰ **多阶段倒计时提醒**：
  - 开始前 **20 分钟** 预警提醒
  - 开始前 **5 分钟** 强提醒（Bark 时效性通知 `timeSensitive` + 警报音 `alarm`）
  - 开始时刻 **🔥 空投已开始** 实时通知
- 🛡 **防刷屏与重启持久化**：使用 SQLite 保存事件状态与已发通知记录，容器或服务重启后绝不重复推送。
- 🚨 **容错与自我修复**：
  - Bark 推送失败 3 次指数退避重试，自动脱敏日志中的设备 Key。
  - API 连续失败 3 次自动推送故障告警，恢复正常后发送恢复通知。
  - API 成功返回但无法解析出数据时触发结构异常保护（防止误删库，自动保存调试样本）。
- 🩺 **轻量健康检查**：内置 `http.server` 提供 `/health` 接口，支持 Docker Healthcheck。

---

## 🛠 技术栈

- **Python 3.12**
- **httpx** (HTTP 请求)
- **SQLite** (轻量持久化)
- **Docker & Docker Compose** (轻量部署)
- **ZoneInfo (`Asia/Shanghai`)** (标准时区转换)
- **pytest** (单元测试)

---

## 🚀 快速部署指南

### 1. iPhone 安装 Bark App
- 在 App Store 搜索并下载 **Bark**。
- 打开 Bark App，复制专属推送地址（例如 `https://api.day.app/YourDeviceKey`）。

### 2. 克隆项目与配置环境变量
```bash
cd alpha123-bark-monitor
cp .env.example .env
```

编辑 `.env` 文件，填入你的 Bark 推送地址：
```env
ALPHA_API_URL=https://alpha123.uk/api/data?fresh=1

# 方案一：直接填写 Bark 复制的完整 URL
BARK_BASE_URL=https://api.day.app/你的设备Key

# 方案二：如果使用自建 Bark 服务器，可填写 server 与 device_key
BARK_SERVER=
BARK_DEVICE_KEY=

BARK_GROUP=Alpha123
BARK_SOUND=alarm
BARK_LEVEL=timeSensitive

POLL_INTERVAL_SECONDS=20
TIMEZONE=Asia/Shanghai
NOTIFY_EXISTING_ON_FIRST_RUN=false
```

### 3. 测试 Bark 推送
在启动监控前，请先测试 Bark 配置是否正确：

**使用 Docker：**
```bash
docker compose build
docker compose run --rm alpha-monitor python -m app.main test-bark
```

**本地运行：**
```bash
python -m app.main test-bark
```
如果手机收到测试推送 `🔔 Alpha123 监控测试`，说明配置成功！

---

## 🐳 Docker Compose 启动与维护

### 启动服务
```bash
docker compose up -d
```

### 查看实时日志
```bash
docker compose logs -f
```

### 查看容器健康状态
```bash
docker compose ps
curl http://localhost:8080/health
```

### 更新程序
```bash
git pull
docker compose build
docker compose up -d
```

### 数据备份与恢复
所有事件数据和已发送日志存储在本地 `./data/alpha_monitor.db` 中。
备份只需复制 `./data` 目录即可：
```bash
cp -r ./data ./data_backup_$(date +%Y%m%m)
```

---

## 🖥 命令行工具 (CLI)

服务提供多种命令行辅助命令：

```bash
# 1. 运行持续监控 (Docker 默认执行)
python -m app.main run

# 2. 发送 Bark 测试通知
python -m app.main test-bark

# 3. 单次请求接口并打印解析后的事件与顶层 JSON 结构
python -m app.main fetch-once

# 4. 查看 SQLite 中存储的所有空投事件
python -m app.main show-events

# 5. 清空数据库 (需二次确认或加 -y 选项)
python -m app.main reset-database
```

---

## ❓ 常见问题排查

1. **手机接收不到 Bark 通知？**
   - 检查 `.env` 中的 `BARK_BASE_URL` 是否填写正确。
   - 在终端运行 `python -m app.main test-bark` 查看详细日志。
   - 确认手机网络正常且 Bark App 允许接收通知。

2. **首次启动为什么没有收到旧空投提醒？**
   - 默认策略 `NOTIFY_EXISTING_ON_FIRST_RUN=false` 会将首次启动时的已知空投记录到数据库，仅发送一条“监控已启动”总览通知，避免首刷爆弹。
   - 如果需要推送历史空投，可在 `.env` 中修改 `NOTIFY_EXISTING_ON_FIRST_RUN=true`。

3. **接口数据格式突变怎么办？**
   - 如果接口结构变化导致未解析出事件，程序会自动触发保护机制，在 `/data/debug/` 保存原始响应样本（最多保留 10 份），并向手机推送 `⚠️ Alpha123 数据结构可能变化` 告警。
   - 可运行 `python -m app.main fetch-once` 观察顶层字段，调整 `app/parser.py` 中的字段适配逻辑。

---

## 🧪 运行测试 suite

运行全部单元测试（包含时间戳解析、防重复推送、倒计时提醒逻辑）：
```bash
pytest
```
