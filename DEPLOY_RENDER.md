# Render 上线清单

这份清单是给你把当前网页正式上线用的，目标是：

1. 网页更稳定
2. 有固定公网地址
3. 后续能绑定你自己的域名

## 先说结论

这套项目现在最适合的第一版部署方式是：

1. 用 GitHub 托管代码
2. 用 Render 部署 Python Web Service
3. 挂一个持久化磁盘保存 `data/`
4. 保持单实例运行

原因：

1. 现在项目是 Flask
2. 后台轮询和网页进程是同一套
3. 运行数据存在 `data/` 文件夹

所以第一版不要多实例，不要无磁盘部署。

## 第一步：把项目上传到 GitHub

Render 需要从 Git 仓库拉代码。

如果你还没有 GitHub 仓库，最简单做法：

1. 在 GitHub 新建一个空仓库
2. 本地进入项目目录
3. 执行下面这些命令

```bash
cd /Users/mac/Documents/Codex/ai-crypto-monitor-mvp
git init
git add .
git commit -m "Initial deployable version"
git branch -M main
git remote add origin YOUR_GITHUB_REPO_URL
git push -u origin main
```

把 `YOUR_GITHUB_REPO_URL` 换成你自己的仓库地址。

## 第二步：在 Render 创建服务

Render 后台操作步骤：

1. 登录 Render
2. 点 `New +`
3. 选择 `Blueprint`
4. 连接你的 GitHub 仓库
5. 选择这个项目

项目根目录里已经有：

`render.yaml`

Render 会自动识别它。

## 第三步：确认部署配置

这个项目已经准备好了这些配置：

- 启动命令：`gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT src.ai_crypto_monitor.webapp:app`
- 健康检查：`/healthz`
- 持久化磁盘挂载：`/opt/render/project/src/data`

对应文件：

- `/Users/mac/Documents/Codex/ai-crypto-monitor-mvp/render.yaml`

## 第四步：填写环境变量

上线后至少建议在 Render 填这两个：

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

如果只是先看网页，不立刻发消息，也可以先不填，但提醒功能不会完整工作。

## 第五步：确认磁盘

你这个项目必须保住 `data/`，否则这些内容会丢：

- 网页设置
- 信号历史
- 运行状态
- 趋势学习缓存

所以部署时一定要确认已经挂载持久化磁盘。

## 第六步：打开公网地址

部署成功后，Render 会给你一个：

`https://你的服务名.onrender.com`

这样的公网地址。

以后你应该打开这个地址，而不是本地：

- 正确：`https://...onrender.com`
- 本地调试：`http://127.0.0.1:5180`
- 错误：`file:///.../templates/index.html`

## 第七步：绑定自己的域名

等 Render 服务跑稳后，再做域名。

步骤很简单：

1. 打开 Render 服务详情
2. 找到 `Custom Domains`
3. 添加你的域名
4. 去你的域名 DNS 提供商那里按提示配置记录
5. 等 Render 自动签 HTTPS

## 第八步：上线后怎么判断稳不稳

重点看这几个点：

1. `https://你的域名/healthz` 能返回正常 JSON
2. 网页首页能正常打开
3. 设置保存后刷新还在
4. Telegram 测试消息能发出去
5. 重启服务后 `data/` 数据没有丢

## 这套方案的边界

这套第一版适合：

1. 单用户
2. 单实例
3. 轻量监控和提醒

如果后面你要做更大规模，再考虑拆成：

1. Web 服务
2. 后台 Worker
3. 独立数据库

但现在先别把架构做重，先稳定上线最重要。
