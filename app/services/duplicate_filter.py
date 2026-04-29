"""
重复文件过滤服务模块

功能说明：
    使用 MD5 哈希检测重复视频文件，避免为重复文件创建硬链接

工作流程：
    1. 每次创建硬链接时计算并存储 MD5
    2. 扫描新文件时，先计算 MD5，再查询数据库是否有相同 MD5 的记录
    3. 如果有相同 MD5 的记录，说明是重复文件，跳过
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
    def check_duplicate_by_md5(file_path: str, file_size: int) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        检查文件是否为重复文件

        每次都计算 MD5 并查询数据库，确保新添加的文件也能被记录

        Args:
            file_path: 待检查的文件路径
            file_size: 文件大小

        Returns:
            Tuple[bool, Optional[str], Optional[str]]
            - is_duplicate: 是否为重复文件
            - duplicate_path: 重复文件的 source_path（如果有）
            - md5: 计算出的 MD5 值
        """
        md5 = calculate_md5(file_path)
        if not md5:
            logger.warning(f"无法计算 MD5: {file_path}")
            return False, None, None

        existing_link = HardLink.query.filter(
            HardLink.md5 == md5,
            HardLink.is_active == True
        ).first()

        if existing_link:
            logger.info(f"发现重复文件: {file_path} <-> {existing_link.source_path} (MD5: {md5})")
            return True, existing_link.source_path, md5

        return False, None, md5

    @staticmethod
    def get_by_md5(md5: str) -> Optional[HardLink]:
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
