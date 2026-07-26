# GenImage

GenImage 是一个基于 Vue、FastAPI 和 SQLite 的图片生成工作台。生产环境使用 Docker Compose 运行，统一通过服务器的 `8083` 端口访问。

## Linux 部署

服务器需要安装 Git、Docker Engine 和 Docker Compose v2，并允许防火墙访问 TCP `8083` 端口。

```bash
git clone -b master git@github.com:zhangjietest666/GenImage.git
cd GenImage
chmod +x deploy.sh
./deploy.sh
```

部署完成后访问：

```text
http://SERVER_IP:8083/
```

首次部署会创建空的 SQLite 数据库。进入页面后展开接口配置并填写 API Key；本地开发环境中的 API Key、历史记录和图片不会迁移到服务器。

## 更新与管理

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

健康检查地址为 `http://SERVER_IP:8083/health`。
