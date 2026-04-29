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
    def __init__(self, scanner: ScannerService):
        self.scanner = scanner
        self._processing = set()
        self._lock = threading.Lock()

    def is_video_file(self, path: str) -> bool:
        if not os.path.isfile(path):
            return False
        ext = os.path.splitext(path)[1].lower()
        return ext in self.scanner.video_extensions

    def _is_dir_in_source(self, path: str) -> bool:
        try:
            source = os.path.abspath(self.scanner.source_folder)
            target = os.path.abspath(self.scanner.target_folder)
            path = os.path.abspath(path)
            if path.startswith(target):
                return False
            return path.startswith(source)
        except:
            return False

    def _process_new_file(self, file_path: str):
        with self._lock:
            if file_path in self._processing:
                return
            self._processing.add(file_path)

        try:
            time.sleep(1)

            if not os.path.exists(file_path):
                return

            from app import create_app
            app = create_app()
            with app.app_context():
                if HardLinkService.get_link_by_source(file_path):
                    logger.debug(f"文件已有硬链接记录: {file_path}")
                    return

                from app.utils.video import get_video_duration
                duration = get_video_duration(file_path)
                if duration is None:
                    logger.warning(f"无法获取视频时长: {file_path}")
                    return

                if duration < self.scanner.min_duration:
                    logger.info(f"视频时长 {duration}s 小于阈值 {self.scanner.min_duration}s: {file_path}")
                    return

                file_size = os.path.getsize(file_path)
                target_path = self.scanner.get_target_path(file_path)

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
        if event.is_directory:
            return
        if not self._is_dir_in_source(event.src_path):
            return
        if not self.is_video_file(event.src_path):
            return

        logger.info(f"检测到新视频文件: {event.src_path}")

        threading.Thread(
            target=self._process_new_file,
            args=(event.src_path,),
            daemon=True
        ).start()

    def on_deleted(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if not self._is_dir_in_source(event.src_path):
            return
        if not self.is_video_file(event.src_path):
            return

        logger.info(f"检测到文件删除: {event.src_path}")

        try:
            from app import create_app
            app = create_app()
            with app.app_context():
                link = HardLinkService.get_link_by_source(event.src_path)

                if link and os.path.exists(link.link_path):
                    os.remove(link.link_path)
                    logger.info(f"自动删除硬链接: {link.link_path}")

                HardLinkService.remove_by_source(event.src_path, delete_source=False)

        except Exception as e:
            logger.error(f"处理文件删除失败 {event.src_path}: {e}")

    def on_modified(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if not self._is_dir_in_source(event.src_path):
            return
        if not self.is_video_file(event.src_path):
            return

        if event.src_path not in self._processing:
            threading.Thread(
                target=self._process_new_file,
                args=(event.src_path,),
                daemon=True
            ).start()


class WatcherService:
    def __init__(self):
        self.scanner = ScannerService()
        self.handler = VideoFileHandler(self.scanner)
        self.observer = None
        self._running = False

    def _recreate_scanner(self):
        self.scanner = ScannerService()
        self.handler = VideoFileHandler(self.scanner)

    def start(self):
        if self._running:
            logger.warning("监控服务已在运行")
            return

        # 启动前重新刷新配置，确保使用最新配置
        self.scanner.refresh_config()
        source_folder = self.scanner.source_folder

        if not os.path.exists(source_folder):
            logger.error(f"源文件夹不存在，无法启动监控: {source_folder}")
            return

        self.observer = Observer()
        self.observer.schedule(self.handler, source_folder, recursive=True)
        self.observer.start()
        self._running = True

        logger.info(f"文件夹监控已启动: {source_folder}")

    def stop(self):
        if not self._running:
            return

        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
        self._running = False
        logger.info("文件夹监控已停止")

    def is_running(self) -> bool:
        return self._running

    def restart(self):
        self.stop()
        time.sleep(1)
        self._recreate_scanner()
        self.start()


_watcher_instance = None


def get_watcher() -> WatcherService:
    global _watcher_instance
    if _watcher_instance is None:
        _watcher_instance = WatcherService()
    return _watcher_instance
