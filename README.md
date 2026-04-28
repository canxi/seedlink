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

1. 克隆仓库
2. 创建 `.env.local` 文件配置环境变量（或使用默认配置）
3. 启动服务

```bash
# 克隆
git clone https://github.com/canxi/seedlink.git
cd seedlink

# 启动
docker-compose up -d

# 访问
open http://localhost:5000
```

## 配置说明

所有配置通过环境变量管理，无需修改代码。

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `SOURCE_FOLDER` | `/downloads` | 源文件夹（PT下载目录） |
| `TARGET_FOLDER` | `/media` | 目标文件夹（媒体库目录） |
| `MIN_DURATION` | `600` | 最小视频时长（秒） |
| `DATABASE_URI` | `sqlite:///data/hardlinks.db` | 数据库路径 |
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

### Docker 环境变量

使用 `.env.docker` 文件：

```bash
SOURCE_FOLDER=/downloads
TARGET_FOLDER=/media
DATABASE_URI=sqlite:////app/data/hardlinks.db
```

## 目录说明

| 宿主机目录 | 容器内目录 | 说明 |
|-----------|-----------|------|
| `./data` | `/app/data` | SQLite 数据库文件 |
| `/downloads` | `/downloads:ro` | PT 下载目录（只读） |
| `/media` | `/media` | 媒体库目录 |

## 技术栈

- Flask 3.0
- SQLAlchemy 2.0
- Bootstrap 5
- watchdog（文件监控）
- ffprobe（视频信息）
