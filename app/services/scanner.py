"""
文件夹扫描服务模块
"""

import os
import logging
from typing import List, Tuple
from app.config import config
from app.utils.video import get_video_duration, get_video_info
from app.services.hardlink import HardLinkService


logger = logging.getLogger(__name__)


class ScannerService:

    def __init__(self):
        # 每次创建时重新加载配置
        config.reload()
        self.source_folder = config.source_folder
        self.target_folder = config.target_folder
        self.min_duration = config.min_duration
        self.video_extensions = config.video_extensions

    def refresh_config(self):
        config.reload()
        self.source_folder = config.source_folder
        self.target_folder = config.target_folder
        self.min_duration = config.min_duration
        self.video_extensions = config.video_extensions

    def is_video_file(self, filename: str) -> bool:
        ext = os.path.splitext(filename)[1].lower()
        return ext in self.video_extensions

    def get_video_files(self, folder: str) -> List[str]:
        video_files = []

        if not os.path.exists(folder):
            logger.warning(f"文件夹不存在: {folder}")
            return video_files

        for root, _, files in os.walk(folder):
            for filename in files:
                if self.is_video_file(filename):
                    video_files.append(os.path.join(root, filename))

        return video_files

    def get_relative_path(self, source_path: str) -> str:
        return os.path.relpath(source_path, self.source_folder)

    def get_target_path(self, source_path: str) -> str:
        relative_path = self.get_relative_path(source_path)
        return os.path.join(self.target_folder, relative_path)

    def scan_and_create_hardlinks(self) -> Tuple[int, int, List[str], List[str]]:
        self.refresh_config()

        processed = 0
        created = 0
        errors = []
        skipped = []

        if not os.path.exists(self.source_folder):
            logger.warning(f"源文件夹不存在: {self.source_folder}")
            return processed, created, ["源文件夹不存在"], skipped

        video_files = self.get_video_files(self.source_folder)
        logger.info(f"发现 {len(video_files)} 个视频文件")

        for source_path in video_files:
            try:
                existing_link = HardLinkService.get_link_by_source(source_path)
                if existing_link:
                    logger.info(f"跳过（已存在硬链接）: {source_path}")
                    skipped.append(f"已存在硬链接: {source_path}")
                    continue

                duration = get_video_duration(source_path)
                if duration is None:
                    logger.warning(f"跳过（无法获取时长）: {source_path}")
                    errors.append(f"无法获取时长: {source_path}")
                    continue

                if duration < self.min_duration:
                    logger.info(f"跳过（时长不足 {duration}s < {self.min_duration}s）: {source_path}")
                    skipped.append(f"视频时长 {duration}s 小于阈值 {self.min_duration}s: {source_path}")
                    continue

                file_size = os.path.getsize(source_path)
                target_path = self.get_target_path(source_path)

                success, message = HardLinkService.create_hardlink(
                    source_path=source_path,
                    target_path=target_path,
                    duration=duration,
                    file_size=file_size
                )

                if success:
                    created += 1
                else:
                    errors.append(f"{source_path}: {message}")

                processed += 1

            except Exception as e:
                logger.error(f"处理文件失败 {source_path}: {e}")
                errors.append(f"{source_path}: {str(e)}")

        logger.info(f"扫描完成: 处理 {processed} 个文件，创建 {created} 个硬链接，跳过 {len(skipped)} 个")
        return processed, created, errors, skipped
