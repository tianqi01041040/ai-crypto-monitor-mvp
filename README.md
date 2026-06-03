# Crypto Alert Bot

这是一个给新手使用的第一版加密货币交易提醒机器人。

它只做三件事：

1. 连接 Binance 或 OKX 的公开行情 API
2. 每 5 分钟检查 BTC、ETH、SOL、SUI、DOGE
3. 触发条件后发送 Telegram 提醒，并在网页后台展示最近信号

重要原则：

1. 不自动下单
2. 不接交易所账户私钥
3. 只做行情监控、信号生成、Telegram 提醒

## 现在有哪些功能

- 网页后台
- Binance / OKX 公开行情读取
- 5 分钟涨跌幅检查
- 成交量变化检查
- BTC 是否带动全市场同步波动检查
- Telegram 测试消息
- Telegram 正式信号推送
- 机器人手动开启 / 关闭
- 最近信号展示
- 胜率统计预留

## 项目目录

- 项目路径：`/Users/mac/Documents/Codex/ai-crypto-monitor-mvp`
- 启动脚本：`/Users/mac/Documents/Codex/ai-crypto-monitor-mvp/start.command`
- 设置文件：`/Users/mac/Documents/Codex/ai-crypto-monitor-mvp/data/web_settings.json`
- 信号记录：`/Users/mac/Documents/Codex/ai-crypto-monitor-mvp/data/signal_history.jsonl`

## 第一步：创建 Telegram Bot

1. 打开 Telegram
2. 搜索 `@BotFather`
3. 发送 `/newbot`
4. 按提示输入机器人名字
5. 再输入一个以 `bot` 结尾的用户名
6. 创建成功后，BotFather 会给你一串 Token

这串 Token 就是：

`TELEGRAM_BOT_TOKEN`

例子：

`123456789:AAExampleTokenHere`

## 第二步：拿到 TELEGRAM_CHAT_ID

最简单的方法：

1. 在 Telegram 里找到你刚创建的机器人
2. 给机器人先发送一条消息，比如：`hello`
3. 浏览器打开下面这个地址，把 `YOUR_BOT_TOKEN` 换成你的真实 Token：

`https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates`

4. 页面里会出现一段 JSON
5. 找到里面的 `chat`
6. 再找到 `id`

这个数字就是：

`TELEGRAM_CHAT_ID`

如果你看到的是负数，也正常，群组聊天常见。

## 第三步：本地运行

### 最简单方法

1. 打开文件夹：

`/Users/mac/Documents/Codex/ai-crypto-monitor-mvp`

2. 双击：

`start.command`

3. 等几秒

4. 浏览器会自动打开：

[http://127.0.0.1:5180](http://127.0.0.1:5180)

### 打开网页后怎么操作

1. 先填写 `TELEGRAM_BOT_TOKEN`
2. 再填写 `TELEGRAM_CHAT_ID`
3. 打开“开启 Telegram 推送”
4. 点“保存设置”
5. 点“测试 Telegram”
6. 确认 Telegram 能收到消息
7. 点“开启机器人”

完成后，机器人就会开始每 5 分钟自动检查一次。

## 第三步补充：更稳的 Mac 自动启动

如果你希望以后重启电脑后也自动恢复，推荐用项目里自带的正式版脚本。

你可以看到这些文件：

- `/Users/mac/Documents/Codex/ai-crypto-monitor-mvp/start.command`
- `/Users/mac/Documents/Codex/ai-crypto-monitor-mvp/stop.command`
- `/Users/mac/Documents/Codex/ai-crypto-monitor-mvp/restart.command`
- `/Users/mac/Documents/Codex/ai-crypto-monitor-mvp/status.command`
- `/Users/mac/Documents/Codex/ai-crypto-monitor-mvp/install_launch_agent.command`
- `/Users/mac/Documents/Codex/ai-crypto-monitor-mvp/uninstall_launch_agent.command`

它们的作用分别是：

- `start.command`
  手动启动网页后台
- `stop.command`
  手动停止
- `restart.command`
  一键重启
- `status.command`
  查看本地服务和网页接口是否还活着
- `install_launch_agent.command`
  安装 Mac 开机自动启动
- `uninstall_launch_agent.command`
  取消开机自动启动

### 推荐做法

第一次确认机器人能正常运行后，再安装自动启动。

安装成功后：

1. 你重启 Mac
2. 机器人会自动在后台启动
3. 你打开浏览器访问 [http://127.0.0.1:5180](http://127.0.0.1:5180) 就能继续看

这个自动启动版本会把运行副本同步到：

`~/Library/Application Support/AI Crypto Monitor`

这样可以避开 macOS 对 `Documents` 目录的后台权限限制，更稳定。

### 如果网页打不开

按这个顺序最简单：

1. 双击 `status.command`
2. 如果显示接口不可访问，双击 `restart.command`
3. 再打开网页

## 第四步：信号触发逻辑

机器人每轮会看：

- 5 分钟涨跌幅
- 成交量是否明显放大
- BTC 是否带动其他主流币同步波动

当满足较强条件时，会发一条 Telegram 消息，里面包含：

- 标的
- 当前价格
- 偏多 / 偏空
- 入场观察区
- 止损位
- 止盈1
- 止盈2
- 风险等级
- 触发原因

## 第五步：网页后台会显示什么

- 当前监控币种
- 当前价格
- 5 分钟涨跌幅
- 24 小时涨跌幅
- 成交量放大倍数
- 最近信号
- 机器人运行状态
- 胜率统计预留

## 如何填写 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID

你有两种方式：

### 方式 A：直接在网页里填

这是最推荐的方式。

打开网页后，直接在 Telegram 设置区域填写：

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

然后点击“保存设置”。

### 方式 B：部署到云端时用环境变量

云端部署时，建议配置两个环境变量：

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

这样更安全。

## 本地命令行运行

如果你想手动启动，也可以在终端里运行：

```bash
cd /Users/mac/Documents/Codex/ai-crypto-monitor-mvp
PYTHONPATH=.vendor:. AI_CRYPTO_MONITOR_PORT=5180 python3 -m src.ai_crypto_monitor.webapp
```

如果你本机没有装 Flask，最简单还是双击 `start.command`。

## 云端 24 小时运行

第一版最省心的方式：用一台 Linux 云服务器。

推荐配置：

- 1 核 CPU
- 1 GB 内存
- Ubuntu 22.04

部署步骤：

1. 把整个项目上传到服务器
2. 安装 Python 3
3. 安装依赖
4. 配置环境变量
5. 用 `systemd` 常驻运行

### 安装依赖

## 为什么你会看到“网页不稳定”

如果你看到页面里直接出现：

- `{{ payload.updated_at }}`
- `{{ payload.bot.last_success_at or "暂无" }}`

这通常不是接口挂了，而是你打开了：

- `file:///.../templates/index.html`

也就是直接打开了模板文件。

这种打开方式不会经过 Flask 渲染，所以页面看起来就像“坏掉了”。

正确打开方式应该是服务地址，例如：

- `http://127.0.0.1:5180`

## 更稳定的部署方案

如果你后面想：

1. 网页更稳定
2. 不依赖这台 Mac 一直开着
3. 后续绑定你自己的域名

我更推荐直接部署到 Render。

原因很简单：

1. 这项目是 Flask + 本地文件存储
2. Render 对 Python Web Service 支持直接
3. 可以加持久化磁盘，避免 `data/` 在重启后丢失
4. 后面加自定义域名也顺

我已经给项目补好了这些部署准备：

- `requirements.txt`
  现在包含 `gunicorn`
- `src/ai_crypto_monitor/webapp.py`
  现在包含 `/healthz` 健康检查，并支持云端 `PORT`
- `render.yaml`
  已经有一份可直接用于 Render Blueprint 的部署配置

## Render 部署步骤

### 1. 先把项目放到 GitHub

因为 Render 需要从 Git 仓库拉代码。

### 2. 在 Render 新建 Blueprint

1. 登录 Render
2. 选择 `New +`
3. 选择 `Blueprint`
4. 连接你的 GitHub 仓库
5. Render 会识别项目根目录里的：

`render.yaml`

### 3. 配置环境变量

至少建议补这两个：

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

如果你不想在云端发消息，也可以先不填，但正式提醒功能会受影响。

### 4. 挂持久化磁盘

这个项目会把运行数据写在：

- `data/runtime_state.json`
- `data/web_settings.json`
- `data/bot_runtime.json`
- `data/signal_history.jsonl`

所以云端部署时必须保留 `data/`。

我已经在 `render.yaml` 里把磁盘挂载路径配成了：

`/opt/render/project/src/data`

### 5. 部署后访问

部署成功后，Render 会给你一个：

- `https://xxx.onrender.com`

的地址。

## 后续加域名

后面你只需要：

1. 在 Render 的服务里添加 Custom Domain
2. 在你的域名 DNS 提供商那里配置记录
3. 等 Render 自动签发 HTTPS 证书

这样就能把现在的地址换成你自己的域名。

## 现阶段最重要的稳定性提醒

这套项目现在还是“单实例更稳”的结构，因为它有两个特点：

1. 后台轮询 worker 跟网页进程在一起
2. 运行状态主要保存在本地文件里

所以不建议一开始就多实例扩容。

最稳的第一版方案是：

1. `gunicorn` 跑 1 个 worker
2. Render Web Service 跑 1 个实例
3. 挂一个持久化磁盘

等你后面真的要做更大规模，再把：

- Web
- Worker
- Data storage

拆开会更合适。

```bash
sudo apt update
sudo apt install -y python3 python3-pip
cd /path/to/ai-crypto-monitor-mvp
python3 -m pip install -r requirements.txt
```

### 配置环境变量

```bash
export TELEGRAM_BOT_TOKEN="你的 Token"
export TELEGRAM_CHAT_ID="你的 Chat ID"
export AI_CRYPTO_MONITOR_HOST="0.0.0.0"
export AI_CRYPTO_MONITOR_PORT="5180"
```

### 启动

```bash
cd /path/to/ai-crypto-monitor-mvp
PYTHONPATH=. python3 -m src.ai_crypto_monitor.webapp
```

### 做成 systemd 服务

在服务器创建文件：

`/etc/systemd/system/crypto-alert-bot.service`

内容如下：

```ini
[Unit]
Description=Crypto Alert Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/path/to/ai-crypto-monitor-mvp
Environment=PYTHONPATH=/path/to/ai-crypto-monitor-mvp
Environment=AI_CRYPTO_MONITOR_HOST=0.0.0.0
Environment=AI_CRYPTO_MONITOR_PORT=5180
Environment=TELEGRAM_BOT_TOKEN=你的Token
Environment=TELEGRAM_CHAT_ID=你的ChatID
ExecStart=/usr/bin/python3 -m src.ai_crypto_monitor.webapp
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

然后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable crypto-alert-bot
sudo systemctl start crypto-alert-bot
sudo systemctl status crypto-alert-bot
```

## 提醒

- 第一版只是提醒机器人，不是自动交易系统
- 消息里的入场区、止损、止盈属于观察建议，不代表一定成交
- 公开行情 API 偶尔会短时失败，所以网页里如果看到错误提示，通常再等下一轮即可
