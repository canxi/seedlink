## 功能特性

- **视频时长筛选**: 使用 ffprobe 检测视频时长，只为超过指定时长的视频创建硬链接
- **实时监控**: 监控源文件夹，新视频自动创建硬链接
- **原文件删除同步**: 删除原文件时自动删除对应的硬链接，避免资源浪费
- **Web 管理界面**: 美观的 Bootstrap 5 界面，配置管理简便
- **SQLite 记录**: 所有硬链接关系存储在 SQLite 数据库中
- **Docker 部署**: 一键部署，开箱即用

## 快速开始

### 使用 Docker Compose（推荐）
``bash
# 1. 创建 docker-compose.yml
# 2. 启动
docker-compose up -d

# 3. 访问
open http://localhost:5200
```
