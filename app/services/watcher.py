"""
文件夹监控服务模块

功能说明：
    1. 使用 watchdog 监控源文件夹的文件变化
    2. 检测到新视频文件时自动创建硬链接
    3. 检测到文件删除时自动清理硬链接

监控事件：
    - on_created: 新建文件时触发
    - on_deleted: 删除文件时触发
    - on_modified: 修改文件时触发（用于检测下载完成）

设计考虑：
    - 使用独立线程处理文件，避免阻塞主线程
    - 添加处理锁防止同一文件被重复处理
    - 文件创建后等待 1 秒，确保文件下载完成

重要：
    - 硬链接只能在同一文件系统内创建
    - 跨分区或网络驱动器无法创建硬链接
"""

import os
import time
import logging
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from app.config import config
from app.services.hardlink import HardLinkService
from app.services.scanner import ScannerService


logger = logging.getLogger(__name__)


class VideoFileHandler(FileSystemEventHandler):
    """
    视频文件事件处理器

    继承自 watchdog 的 FileSystemEventHandler
    实现文件创建、删除、修改事件的处理

    主要功能：
        - 判断是否是视频文件
        - 检查路径是否在源文件夹内
        - 创建或删除硬链接
    """

    def __init__(self, scanner: ScannerService):
        """
        初始化处理器

        Args:
            scanner: 扫描器服务实例，用于路径计算等
        """
        self.scanner = scanner
        self._processing = set()  # 正在处理的文件集合
        self._lock = threading.Lock()  # 线程锁

    def is_video_file(self, path: str) -> bool:
        """
        检查路径是否是视频文件

        Args:
            path: 文件路径

        Returns:
            bool: 是否是视频文件
        """
        if not os.path.isfile(path):
            return False
        ext = os.path.splitext(path)[1].lower()
        return ext in self.scanner.video_extensions

    def _is_dir_in_source(self, path: str) -> bool:
        """
        检查路径是否在源文件夹内

        Args:
            path: 文件或目录路径

        Returns:
            bool: 是否在源文件夹内
        """
        try:
            source = os.path.abspath(self.scanner.source_folder)
            path = os.path.abspath(path)
            return path.startswith(source)
        except:
            return False

    def _process_new_file(self, file_path: str):
        """
        处理新文件

        处理流程：
            1. 检查是否正在处理中，避免重复
            2. 等待 1 秒，确保文件下载完成
            3. 检查是否已有硬链接记录
            4. 获取视频时长
            5. 时长符合要求则创建硬链接

        Args:
            file_path: 文件路径
        """
        # 检查是否正在处理
        with self._lock:
            if file_path in self._processing:
                return
            self._processing.add(file_path)

        try:
            # 等待文件写入完成
            # 下载中的文件可能无法获取时长
            time.sleep(1)

            # 文件可能已被删除
            if not os.path.exists(file_path):
                return

            # 检查是否已有硬链接记录
            if HardLinkService.get_link_by_source(file_path):
                logger.debug(f"文件已有硬链接记录: {file_path}")
                return

            # 获取视频时长
            from app.utils.video import get_video_duration
            duration = get_video_duration(file_path)
            if duration is None:
                logger.warning(f"无法获取视频时长: {file_path}")
                return

            # 检查时长是否符合要求
            if duration < self.scanner.min_duration:
                logger.info(
                    f"视频时长 {duration}s 小于阈值 {self.scanner.min_duration}s: {file_path}"
                )
                return

            # 获取文件大小
            file_size = os.path.getsize(file_path)

            # 计算目标路径
            target_path = self.scanner.get_target_path(file_path)

            # 创建硬链接
            success, message = HardLinkService.create_hardlink(
                source_path=file_path,
                target_path=target_path,
                duration=duration,
                file_size=file_size
            )

            if success:
                logger.info(f"自动创建硬链接成功: {file_path}")
            else:
                logger.error(f"自动创建硬链接失败: {message}")

        except Exception as e:
            logger.error(f"处理新文件失败 {file_path}: {e}")
        finally:
            with self._lock:
                self._processing.discard(file_path)

    def on_created(self, event: FileSystemEvent):
        """
        文件创建事件处理

        当新文件创建时触发

        Args:
            event: 文件系统事件对象
        """
        # 忽略目录事件
        if event.is_directory:
            return
        # 忽略非源文件夹的文件
        if not self._is_dir_in_source(event.src_path):
            return
        # 忽略非视频文件
        if not self.is_video_file(event.src_path):
            return

        logger.info(f"检测到新视频文件: {event.src_path}")

        # 在新线程中处理，避免阻塞
        threading.Thread(
            target=self._process_new_file,
            args=(event.src_path,),
            daemon=True
        ).start()

    def on_deleted(self, event: FileSystemEvent):
        """
        文件删除事件处理

        当原文件被删除时，自动删除对应的硬链接

        Args:
            event: 文件系统事件对象
        """
        if event.is_directory:
            return
        if not self._is_dir_in_source(event.src_path):
            return
        if not self.is_video_file(event.src_path):
            return

        logger.info(f"检测到文件删除: {event.src_path}")

        try:
            # 查找对应的硬链接
            link = HardLinkService.get_link_by_source(event.src_path)

            # 删除硬链接文件
            if link and os.path.exists(link.link_path):
                os.remove(link.link_path)
                logger.info(f"自动删除硬链接: {link.link_path}")

            # 更新数据库记录
            HardLinkService.remove_by_source(event.src_path, delete_source=False)

        except Exception as e:
            logger.error(f"处理文件删除失败 {event.src_path}: {e}")

    def on_modified(self, event: FileSystemEvent):
        """
        文件修改事件处理

        用于检测文件下载完成的情况

        Args:
            event: 文件系统事件对象
        """
        if event.is_directory:
            return
        if not self._is_dir_in_source(event.src_path):
            return
        if not self.is_video_file(event.src_path):
            return

        # 避免重复处理
        if event.src_path not in self._processing:
            threading.Thread(
                target=self._process_new_file,
                args=(event.src_path,),
                daemon=True
            ).start()


class WatcherService:
    """
    文件夹监控服务

    使用 watchdog 库监控文件系统变化
    提供启动、停止、重启等控制接口
    """

    def __init__(self):
        """
        初始化监控服务

        创建扫描器、事件处理器和观察者
        """
        self.scanner = ScannerService()
        self.handler = VideoFileHandler(self.scanner)
        self.observer = Observer()
        self._running = False

    def start(self):
        """
        启动文件夹监控

        监控会递归监控源文件夹的所有子文件夹
        """
        if self._running:
            logger.warning("监控服务已在运行")
            return

        source_folder = self.scanner.source_folder

        # 检查源文件夹是否存在
        if not os.path.exists(source_folder):
            logger.error(f"源文件夹不存在，无法启动监控: {source_folder}")
            return

        # 注册监控路径
        # recursive=True 会监控所有子文件夹
        self.observer.schedule(self.handler, source_folder, recursive=True)
        self.observer.start()
        self._running = True

        logger.info(f"文件夹监控已启动: {source_folder}")

    def stop(self):
        """
        停止文件夹监控
        """
        if not self._running:
            return

        self.observer.stop()
        self.observer.join()
        self._running = False
        logger.info("文件夹监控已停止")

    def is_running(self) -> bool:
        """
        检查监控是否正在运行

        Returns:
            bool: 是否正在运行
        """
        return self._running

    def restart(self):
        """
        重启监控服务

        用于配置修改后重新应用新设置
        """
        self.stop()
        time.sleep(1)
        self.start()


# 单例实例
_watcher_instance = None


def get_watcher() -> WatcherService:
    """
    获取监控服务单例

    Returns:
        WatcherService: 监控服务实例
    """
    global _watcher_instance
    if _watcher_instance is None:
        _watcher_instance = WatcherService()
    return _watcher_instance
