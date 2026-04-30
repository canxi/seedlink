# SeedLink

PT 视频硬链接管理器 - 自动为符合条件的视频创建硬链接

## 功能特性

- **视频时长筛选**: 使用 ffprobe 检测视频时长，只为超过指定时长的视频创建硬链接
- **实时监控**: 监控源文件夹，新视频自动创建硬链接
- **原文件删除同步**: 删除原文件时自动删除对应的硬链接，避免资源浪费
- **Web 管理界面**: 美观的 Bootstrap 5 界面，配置管理简便
- **SQLite 记录**: 所有硬链接关系存储在 SQLite 数据库中
- **Docker 部署**: 一键部署，开箱即用

## 快速开始

### 使用 Docker Compose（推荐）

```bash

services:
  app:
    image: ghcr.io/canxi/seedlink:latest
    container_name: seedlink
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
      - /downloads:/downloads
      - /media:/media
    environment:
      - TZ=Asia/Shanghai
    restart: unless-stopped
# 创建数据目录
mkdir -p data

# 启动服务（首次会自动生成配置文件）
docker-compose up -d

# 访问
open http://localhost:5000
```

首次启动后，访问 Web 界面修改源文件夹和目标文件夹路径，配置会自动保存到 `./data/.env` 文件中。

## 配置说明

### 通过 Web 界面配置（推荐）

启动服务后，访问 http://localhost:5000 ，在设置页面修改配置后保存即可。

### 手动配置

配置文件位于 `./data/.env`（Docker 环境）或 `.env.local`（本地开发）：

```bash
SOURCE_FOLDER=/downloads
TARGET_FOLDER=/media
MIN_DURATION=600
SCAN_INTERVAL=60
VIDEO_EXTENSIONS=.mkv,.mp4,.avi,.ts,.mov,.wmv,.flv
DEBUG=false
```

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `SOURCE_FOLDER` | `/downloads` | 源文件夹（PT下载目录） |
| `TARGET_FOLDER` | `/media` | 目标文件夹（媒体库目录） |
| `MIN_DURATION` | `600` | 最小视频时长（秒），过滤短视频 |
| `SCAN_INTERVAL` | `60` | 扫描间隔（秒） |
| `VIDEO_EXTENSIONS` | `.mkv,.mp4,.avi,.ts,.mov,.wmv,.flv` | 支持的视频格式 |
| `DEBUG` | `false` | 调试模式 |

### 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 创建本地配置
cp .env.example .env.local
# 编辑 .env.local 修改配置

# 运行
python app.py
```

## 目录说明

| 宿主机目录 | 容器内目录 | 说明 |
|-----------|-----------|------|
| `./data` | `/app/data` | SQLite 数据库和配置文件 |
| `/downloads` | `/downloads` | PT 下载目录 |
| `/media` | `/media` | 媒体库目录 |

## 技术栈

- Flask 3.0
- SQLAlchemy 2.0
- Bootstrap 5
- watchdog（文件监控）
- ffprobe（视频信息）
