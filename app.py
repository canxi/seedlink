"""
PT 视频硬链接管理器 - 主入口文件
"""

import os
import atexit

from app import create_app
from app.services.watcher import get_watcher
from app.services.hardlink import HardLinkService

# 确保数据库目录存在
db_dir = '/data'
if not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# 创建 Flask 应用实例
app = create_app()

# 获取文件监控服务单例
watcher = get_watcher()


def cleanup():
    if watcher.is_running():
        watcher.stop()


atexit.register(cleanup)


if __name__ == '__main__':
    with app.app_context():
        HardLinkService.cleanup_invalid_links()
        watcher.start()

    app.run(host='0.0.0.0', port=5000, debug=False)
