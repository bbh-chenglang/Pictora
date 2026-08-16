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

Pictora（画境）是一个基于 Vue、FastAPI 和 SQLite 的图片生成工作台。生产环境使用 Docker Compose 运行，统一通过服务器的 `8083` 端口访问。

## Linux 部署

服务器需要安装 Git、Docker Engine 和 Docker Compose v2，并允许防火墙访问 TCP `8083` 端口。

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

SQLite 数据保存在名为 `genimage_data` 的 Docker 卷中。可在项目目录执行：

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
