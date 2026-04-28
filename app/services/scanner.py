"""
文件夹扫描服务模块

功能说明：
    1. 扫描源文件夹中的所有视频文件
    2. 检测视频时长
    3. 为符合条件的视频创建硬链接

工作流程：
    1. 遍历源文件夹中的所有文件
    2. 筛选出视频文件（根据扩展名）
    3. 检查是否已存在硬链接记录
    4. 使用 ffprobe 获取视频时长
    5. 时长符合要求则创建硬链接

设计考虑：
    - 使用扫描而非实时监控的好处是可以一次性处理大量文件
    - 配合 watcher 使用，扫描处理现有文件，watcher 处理新文件
"""

import os
import logging
from typing import List, Tuple
from app.config import config
from app.utils.video import get_video_duration, get_video_info
from app.services.hardlink import HardLinkService


logger = logging.getLogger(__name__)


class ScannerService:
    """
    文件夹扫描服务类

    用于一次性扫描整个源文件夹，
    为所有符合条件的视频创建硬链接
    """

    def __init__(self):
        """
        初始化扫描器

        从配置中读取：
            - source_folder: 源文件夹路径
            - target_folder: 目标文件夹路径
            - min_duration: 最小视频时长
            - video_extensions: 监控的文件扩展名
        """
        self.source_folder = config.source_folder
        self.target_folder = config.target_folder
        self.min_duration = config.min_duration
        self.video_extensions = config.video_extensions

    def refresh_config(self):
        """
        重新加载配置

        使用场景：
            - 配置被修改后，需要刷新扫描器的配置
            - 避免扫描过程中使用旧的配置值
        """
        config._load_config()
        self.source_folder = config.source_folder
        self.target_folder = config.target_folder
        self.min_duration = config.min_duration
        self.video_extensions = config.video_extensions

    def is_video_file(self, filename: str) -> bool:
        """
        检查文件是否是视频文件

        Args:
            filename: 文件名或文件路径

        Returns:
            bool: 是否是视频文件

        说明：
            - 只检查扩展名，不检查文件内容
            - 扩展名不区分大小写
        """
        ext = os.path.splitext(filename)[1].lower()
        return ext in self.video_extensions

    def get_video_files(self, folder: str) -> List[str]:
        """
        获取文件夹中所有视频文件

        Args:
            folder: 文件夹路径

        Returns:
            List[str]: 视频文件的绝对路径列表

        处理流程：
            1. 检查文件夹是否存在
            2. 递归遍历所有子文件夹
            3. 筛选出视频文件（根据扩展名）
        """
        video_files = []

        if not os.path.exists(folder):
            logger.warning(f"文件夹不存在: {folder}")
            return video_files

        # os.walk 递归遍历文件夹
        # root: 当前目录路径
        # dirs: 子目录列表
        # files: 文件列表
        for root, _, files in os.walk(folder):
            for filename in files:
                if self.is_video_file(filename):
                    video_files.append(os.path.join(root, filename))

        return video_files

    def get_relative_path(self, source_path: str) -> str:
        """
        获取相对于源文件夹的路径

        Args:
            source_path: 源文件的绝对路径

        Returns:
            str: 相对路径

        Example:
            source_folder = "/downloads"
            source_path = "/downloads/movie/test.mkv"
            return = "movie/test.mkv"
        """
        return os.path.relpath(source_path, self.source_folder)

    def get_target_path(self, source_path: str) -> str:
        """
        计算硬链接的目标路径

        Args:
            source_path: 源文件的绝对路径

        Returns:
            str: 硬链接的绝对路径

        Example:
            target_folder = "/media"
            source_path = "/downloads/movie/test.mkv"
            return = "/media/movie/test.mkv"

        说明：
            - 保持源文件的目录结构
            - 只改变根目录
        """
        relative_path = self.get_relative_path(source_path)
        return os.path.join(self.target_folder, relative_path)

    def scan_and_create_hardlinks(self) -> Tuple[int, int, List[str]]:
        """
        扫描源文件夹并创建符合条件的硬链接

        Returns:
            Tuple[int, int, List[str]]:
                - 处理的文件数
                - 创建的硬链接数
                - 错误信息列表

        处理流程：
            1. 获取所有视频文件
            2. 遍历每个文件：
               a. 检查是否已有硬链接记录
               b. 获取视频时长
               c. 时长符合要求则创建硬链接
        """
        # 重新加载配置，确保使用最新值
        self.refresh_config()

        processed = 0  # 处理的文件数
        created = 0  # 创建的硬链接数
        errors = []  # 错误信息

        # 检查源文件夹是否存在
        if not os.path.exists(self.source_folder):
            logger.warning(f"源文件夹不存在: {self.source_folder}")
            return processed, created, ["源文件夹不存在"]

        # 获取所有视频文件
        video_files = self.get_video_files(self.source_folder)
        logger.info(f"发现 {len(video_files)} 个视频文件")

        # 遍历处理每个视频文件
        for source_path in video_files:
            try:
                # 检查是否已有硬链接记录
                existing_link = HardLinkService.get_link_by_source(source_path)
                if existing_link:
                    logger.debug(f"已存在硬链接，跳过: {source_path}")
                    continue

                # 获取视频时长
                duration = get_video_duration(source_path)
                if duration is None:
                    errors.append(f"无法获取时长: {source_path}")
                    continue

                # 检查时长是否符合要求
                if duration < self.min_duration:
                    logger.debug(
                        f"视频时长 {duration}s 小于阈值 {self.min_duration}s，跳过: {source_path}"
                    )
                    continue

                # 获取文件大小
                file_size = os.path.getsize(source_path)

                # 计算目标路径
                target_path = self.get_target_path(source_path)

                # 创建硬链接
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

        logger.info(f"扫描完成: 处理 {processed} 个文件，创建 {created} 个硬链接")
        return processed, created, errors
