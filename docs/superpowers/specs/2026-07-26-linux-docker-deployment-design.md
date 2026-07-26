# GenImage Linux Docker 部署设计

## 目标

- 使用 Docker Compose 在 Linux 服务器部署 GenImage。
- 统一通过服务器 `8083` 端口访问前端与 API。
- 保留 SQLite 配置、历史记录和生成图片，容器更新后数据不丢失。
- 不迁移本地数据库、API Key、历史记录或本地图片。
- 将完成后的 `master` 推送到空仓库 `git@github.com:zhangjietest666/GenImage.git`。

## 非目标

- 不引入 PostgreSQL、对象存储或外部缓存。
- 不将 API Key 写入镜像、Compose 文件或 Git 仓库。
- 不开放 FastAPI 的内部端口给宿主机。
- 不在本次部署中配置 HTTPS、域名或自动更新服务。

## 部署架构

采用两个容器：

1. `web` 容器使用 Node.js 构建 Vue 应用，再由 Nginx 提供静态文件。
2. `backend` 容器运行 FastAPI 和 Uvicorn，仅在 Compose 内部网络监听 `8002`。

宿主机端口映射为 `8083:80`。Nginx 处理前端路由，并将 `/api/` 请求代理到 `backend:8002`。浏览器始终使用同源地址，不需要生产环境 CORS 配置。

## 数据流

1. 用户访问 `http://SERVER_IP:8083/`。
2. Nginx 返回 Vue 静态资源。
3. Vue 使用相对路径请求 `/api/*`。
4. Nginx 将 API 请求转发给 FastAPI。
5. FastAPI 将设置、历史记录和图片二进制保存到 `/app/backend/data/genimage.db`。
6. Docker 命名卷挂载到 `/app/backend/data`，容器重建后继续使用原数据。

## 文件设计

- `compose.yaml`：定义 `web`、`backend`、网络、健康检查和数据卷。
- `backend/Dockerfile`：安装固定版本 Python 依赖并启动 Uvicorn。
- `frontend/Dockerfile`：多阶段构建 Vue，并复制产物到 Nginx。
- `frontend/nginx.conf`：SPA 回退、API 代理、上传大小和代理超时。
- `.dockerignore`：排除 Git 元数据、依赖、虚拟环境、数据库、测试图片和本地工具目录。
- `deploy.sh`：在 Linux 服务器执行构建、启动和状态检查。
- `README.md`：记录首次部署、更新、查看日志和备份数据的方法。

## 运行配置

`compose.yaml` 使用以下约束：

- `web` 暴露 `8083:80`。
- `backend` 只使用 `expose: 8002`，不使用宿主机端口映射。
- 两个服务均设置 `restart: unless-stopped`。
- `backend` 健康检查请求 `/health`。
- `web` 在后端健康后启动，并提供自身 HTTP 健康检查。
- Nginx 的生成请求代理超时不短于后端最大生成等待时间。

## 数据与安全

首次部署创建空 SQLite 数据库，用户在网页中重新填写 API Key。以下内容不得提交到 GitHub：

- `backend/data/*.db`、`*.db-shm`、`*.db-wal`
- `note.txt`
- `testfiles/` 及其中图片
- `.codegraph/`、`.cursor/`、`.firecrawl/`
- 本地日志、虚拟环境、Node.js 依赖和构建产物

生成图片存储在 SQLite 数据库中，因此随命名卷一起持久化，不写入仓库目录。

## 部署与更新

首次部署：

```bash
git clone -b master git@github.com:zhangjietest666/GenImage.git
cd GenImage
chmod +x deploy.sh
./deploy.sh
```

后续更新：

```bash
git pull --ff-only
./deploy.sh
```

部署脚本执行 `docker compose up -d --build`，失败时返回非零状态，不删除已有数据卷。

## GitHub 发布

目标仓库当前为空。实现完成并验证后：

1. 将部署分支合并到本地 `master`。
2. 将 `origin` 设置为 `git@github.com:zhangjietest666/GenImage.git`。
3. 推送本地 `master` 并设置上游分支。
4. 不提交任何未跟踪的本地数据文件。

## 验证

- 后端 Pytest 全量测试通过。
- 前端 Vitest 全量测试通过。
- 前端生产构建通过。
- `docker compose config` 通过。
- Docker 镜像可成功构建。
- 容器启动后 `http://127.0.0.1:8083/` 返回前端页面。
- `http://127.0.0.1:8083/health` 返回后端健康状态。
- 通过 `8083` 的 `/api/settings` 可访问后端。
- 重建容器后 SQLite 命名卷仍存在。

## 已确认决策

- 对外端口固定为 `8083`。
- 使用 Nginx 与 FastAPI 双容器架构。
- SQLite 使用 Docker 命名卷。
- 不迁移本地数据库和图片。
- GitHub 仓库使用 `zhangjietest666/GenImage` 的 `master` 分支。
