"""
PT 视频硬链接管理器 - 主入口文件

功能说明：
    1. 初始化 Flask 应用
    2. 启动文件夹监控服务
    3. 清理无效的硬链接记录

使用方式：
    python app.py
    或在 Docker 容器中运行
"""

import os
import atexit

from app import create_app
from app.services.watcher import get_watcher
from app.services.hardlink import HardLinkService


# 创建 Flask 应用实例
app = create_app()

# 获取文件监控服务单例
watcher = get_watcher()


def cleanup():
    """
    应用退出时的清理函数
    确保监控服务被正确停止
    """
    if watcher.is_running():
        watcher.stop()


# 注册退出清理函数
atexit.register(cleanup)


if __name__ == '__main__':
    with app.app_context():
        # 启动时清理数据库中无效的硬链接记录
        # （文件已被删除但数据库未更新的情况）
        HardLinkService.cleanup_invalid_links()

        # 启动文件夹监控服务
        watcher.start()

    # 运行 Flask 开发服务器
    # host=0.0.0.0 使其可以从外部访问
    app.run(host='0.0.0.0', port=5000, debug=False)
