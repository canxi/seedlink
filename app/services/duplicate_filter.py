"""
重复文件过滤服务模块

功能说明：
    使用 MD5 哈希检测重复视频文件，避免为重复文件创建硬链接

分层过滤策略：
    1. 按文件大小快速预筛选（相同大小才可能重复）
    2. 对相同大小的文件计算 MD5 确认
    3. 检查数据库中是否已存在相同 MD5 的文件
"""

import os
import logging
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
from app.models import db, HardLink
from app.utils.video import calculate_md5

logger = logging.getLogger(__name__)


class DuplicateFilterService:

    @staticmethod
    def get_md5_from_db(md5: str) -> Optional[HardLink]:
        """查询数据库中是否存在相同 MD5 的活跃硬链接"""
        return HardLink.query.filter_by(md5=md5, is_active=True).first()

    @staticmethod
    def get_by_size(file_size: int) -> List[HardLink]:
        """查询数据库中相同大小的活跃硬链接"""
        return HardLink.query.filter_by(
            file_size=file_size,
            is_active=True
        ).all()

    @staticmethod
    def check_duplicate_by_md5(file_path: str, file_size: int) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        检查文件是否重复

        使用分层策略：
        1. 先检查数据库中是否有相同大小的文件
        2. 如果有，再计算 MD5 进行确认

        Args:
            file_path: 待检查的文件路径
            file_size: 文件大小

        Returns:
            Tuple[bool, Optional[str], Optional[str]]
            - is_duplicate: 是否为重复文件
            - duplicate_path: 重复文件的 source_path（如果有）
            - md5: 计算出的 MD5 值
        """
        same_size_links = DuplicateFilterService.get_by_size(file_size)
        if not same_size_links:
            return False, None, None

        md5 = calculate_md5(file_path)
        if not md5:
            logger.warning(f"无法计算 MD5: {file_path}")
            return False, None, None

        for link in same_size_links:
            if link.md5 and link.md5 == md5:
                logger.info(f"发现重复文件: {file_path} <-> {link.source_path} (MD5: {md5})")
                return True, link.source_path, md5

        return False, None, md5

    @staticmethod
    def find_duplicates_in_folder(folder: str, video_extensions: List[str]) -> Dict[str, List[str]]:
        """
        扫描文件夹找出所有重复文件

        Args:
            folder: 要扫描的文件夹路径
            video_extensions: 视频文件扩展名列表

        Returns:
            Dict[str, List[str]] - MD5 -> [文件路径列表]
        """
        size_groups: Dict[int, List[str]] = defaultdict(list)

        for root, _, files in os.walk(folder):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in video_extensions:
                    continue
                file_path = os.path.join(root, filename)
                try:
                    size = os.path.getsize(file_path)
                    size_groups[size].append(file_path)
                except OSError as e:
                    logger.warning(f"无法获取文件大小 {file_path}: {e}")

        duplicates: Dict[str, List[str]] = {}
        for size, files in size_groups.items():
            if len(files) < 2:
                continue

            for file_path in files:
                md5 = calculate_md5(file_path)
                if not md5:
                    continue

                if md5 in duplicates:
                    duplicates[md5].append(file_path)
                else:
                    duplicates[md5] = [file_path]

        return {k: v for k, v in duplicates.items() if len(v) > 1}
