# Pictora

## Legacy v1 Docker Deployment (Port 9001)

The v1 deployment is isolated from the default deployment. It uses `compose.v1.yaml`, host port `9001`, containers `genimage-v1-web` and `genimage-v1-backend`, and the `genimage_v1_data` volume.

Deploy v1 on Linux:

```bash
git checkout v1
chmod +x deploy-v1.sh
./deploy-v1.sh
```

Access the v1 deployment at `http://SERVER_IP:9001/` and check health with `curl http://127.0.0.1:9001/health`.

Manage only the v1 deployment:

```bash
docker compose -p genimage-v1 -f compose.v1.yaml ps
docker compose -p genimage-v1 -f compose.v1.yaml logs -f --tail=200
docker compose -p genimage-v1 -f compose.v1.yaml restart
docker compose -p genimage-v1 -f compose.v1.yaml down
```

Do not use `docker compose down -v` unless the isolated v1 database and generated images can be deleted.

Pictora（画境）是一个基于 Vue、FastAPI 和 SQLite 的图片 / 视频生成工作台。保留原有图片生成、编辑、参考图和项目管理，新增独立视频 Key、多模态参考素材、异步视频任务及 R2 私有结果存储。基础生产部署仍通过服务器的 `8083` HTTP 端口访问；公网素材上传可选用 Caddy HTTPS。

视频功能升级、备份、R2 / HTTPS 配置、接口及任务恢复说明见 [视频功能部署与接口](docs/视频功能部署与接口.md)。没有公网 HTTPS 时禁用本地素材上传 / 已有图片引用，没有 R2 或 ffprobe 时禁用视频提交；图片功能继续可用。升级前请先备份 SQLite 和数据卷。

## Linux 部署

服务器需要安装 Git、Docker Engine 和 Docker Compose 2.24 或更新版本（可选私有环境文件所需），并允许防火墙访问 TCP `8083` 端口。

```bash
git clone -b V1 https://github.com/bbh-chenglang/Pictora.git
cd Pictora
chmod +x deploy.sh
./deploy.sh
```

部署完成后访问：

```text
http://SERVER_IP:8083/
```

首次部署会创建空的 SQLite 数据库。进入页面后展开接口配置并填写 API Key；本地开发环境中的 API Key、历史记录和图片不会迁移到服务器。

## 版本发布、更新与管理

正式版本使用大写 Git 标签递增命名：当前版本为 `V1`，后续使用 `V2`、`V3`。从对应标签部署，版本更新页面会显示标签名称，不会显示提交哈希：

```bash
git fetch --tags origin
git checkout V2
./deploy.sh
```

也可以显式指定版本：

```bash
APP_VERSION=V2 ./deploy.sh
```

拉取最新代码并重新构建：

```bash
git pull --ff-only
./deploy.sh
```

查看容器状态和日志：

```bash
docker compose ps
docker compose logs -f --tail=200
```

重启或停止服务：

```bash
docker compose restart
docker compose down
```

`docker compose down` 不会删除 SQLite 数据卷。不要使用 `docker compose down -v`，该命令会删除 API Key、历史记录和数据库中的图片。

## 数据备份

SQLite 数据和视频参考素材保存在名为 `genimage_data` 的 Docker 卷中。先停止后端写入再复制整个卷；R2 结果需要另外备份，具体升级流程见上方视频部署文档。可在项目目录执行：

```bash
docker run --rm \
  -v genimage_data:/data:ro \
  -v "$PWD:/backup" \
  alpine:3.21 \
  tar czf "/backup/genimage-data-$(date +%Y%m%d-%H%M%S).tar.gz" -C /data .
```

备份文件包含接口配置、历史记录和图片，请按敏感数据妥善保管。

## 服务结构

- `web`：构建并托管 Vue 页面，通过 Nginx 将 `/api/*` 和 `/health` 转发到后端。
- `backend`：在 Compose 内部端口 `8002` 运行 FastAPI，不直接映射到宿主机。
- `genimage_data`：挂载到 `/app/backend/data`，用于持久化 SQLite 数据。

后端生成任务使用 SQLite 租约防止多个 worker 重复落图，但任务执行仍由进程内协程负责。当前部署必须保持单个 backend 实例、单个 Uvicorn worker；服务异常退出时，未完成任务会在租约过期后标记为失败，不会自动重放。

健康检查地址为 `http://SERVER_IP:8083/health`。

## 邮箱注册与管理员

V4 使用邮箱验证码注册，并使用邮箱和密码登录。部署前在项目根目录创建 `.env`，至少配置：

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=your-account@gmail.com
SMTP_APP_PASSWORD=your-google-app-password
SMTP_SENDER=your-account@gmail.com
ADMIN_EMAILS=admin@example.com
```

`SMTP_APP_PASSWORD` 必须是 Google 账号开启两步验证后生成的应用专用密码，不是 Gmail 登录密码。`ADMIN_EMAILS` 可填写多个邮箱并用英文逗号分隔；名单内邮箱完成验证码注册或重新登录后获得管理员权限。

数据库升级会保留旧账号和历史记录，但旧账号没有已验证邮箱，原用户名登录和旧会话将失效。旧用户需要在注册页填写原用户名、原密码、新邮箱和验证码来绑定邮箱，绑定后项目与历史记录保持不变。管理员可以查看用户的注册、登录、活动和模型使用统计，并可重置密码；系统始终只保存 bcrypt 密码哈希，不提供明文密码或哈希查看功能。

## 找回密码

顾客可在登录页点击“忘记密码？”，填写已绑定并验证的邮箱，获取 6 位验证码后设置新密码。密码至少 6 位，两次输入需一致。重置成功后返回登录页，所有设备的原有登录会话失效，项目、历史记录和接口配置保留。未绑定邮箱的旧账号需要联系管理员处理。

找回密码复用上述 SMTP 配置，无需新增邮件凭据。验证码默认 10 分钟有效，发送间隔 60 秒，连续错误 5 次失效；重新发送后旧验证码失效，注册验证码不能用于找回密码。发送请求和重置请求均有限流保护。

页面统一显示受理提示，不公开邮箱是否注册。邮件在后台发送；如未收到，请确认输入的是账号绑定邮箱、检查垃圾邮件，等待倒计时结束后重试。“邮件服务尚未配置”表示 SMTP 凭据缺失；发送失败时后台记录 `Password reset email delivery failed`，应检查 SMTP 主机、端口、应用密码和服务器网络。服务在受理后重启也可能导致邮件未送达，可稍后重新获取验证码。

升级会自动将 SQLite 数据库版本更新为 20，并创建独立的找回密码验证码表。部署前按上文备份数据库，再更新并重新构建服务。
