"""
硬链接核心服务模块

功能说明：
    1. 创建硬链接并记录到数据库
    2. 删除硬链接记录和文件
    3. 根据源文件路径删除相关硬链接
    4. 清理无效的数据库记录

核心概念：
    - 硬链接：同一个文件系统的多个路径指向同一物理文件
    - 删除原文件时，硬链接文件仍存在但内容也会被删除（因为是同一文件）
    - 本模块处理这种情况，确保不会留下无效的硬链接

设计考虑：
    - 使用软删除：is_active 标记为 False，而不是真正从数据库删除
    - 这样可以保留历史记录，便于追溯
"""

import os
import logging
from typing import Optional, Tuple
from app.models import db, HardLink
from app.utils.video import get_video_duration, get_video_info


logger = logging.getLogger(__name__)


class HardLinkService:
    """
    硬链接管理服务类

    提供静态方法，无需实例化即可调用
    """

    @staticmethod
    def create_hardlink(source_path: str, target_path: str, duration: float = 0, file_size: int = 0) -> Tuple[bool, str]:
        """
        创建硬链接并记录到数据库

        Args:
            source_path: 原始文件路径
            target_path: 硬链接目标路径
            duration: 视频时长（秒），可选
            file_size: 文件大小（字节），可选

        Returns:
            Tuple[bool, str]: (是否成功, 消息)

        处理流程：
            1. 检查源文件是否存在
            2. 检查目标文件是否已存在
            3. 创建目标目录（如果不存在）
            4. 使用 os.link() 创建硬链接
            5. 在数据库中创建记录
        """
        try:
            # 检查源文件是否存在
            if not os.path.exists(source_path):
                return False, f"源文件不存在: {source_path}"

            # 检查目标文件是否已存在
            if os.path.exists(target_path):
                return False, f"目标文件已存在: {target_path}"

            # 创建目标目录（如果不存在）
            target_dir = os.path.dirname(target_path)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)

            # 创建硬链接
            # os.link(source, target) 创建硬链接
            # 成功后源文件和目标文件指向同一物理位置
            os.link(source_path, target_path)

            # 在数据库中创建记录
            link_record = HardLink(
                source_path=source_path,
                link_path=target_path,
                file_size=file_size or os.path.getsize(source_path),
                duration=duration,
                is_active=True
            )
            db.session.add(link_record)
            db.session.commit()

            logger.info(f"成功创建硬链接: {source_path} -> {target_path}")
            return True, "硬链接创建成功"

        except OSError as e:
            # 可能是跨文件系统、不支持硬链接等系统错误
            db.session.rollback()
            logger.error(f"创建硬链接失败: {e}")
            return False, f"创建硬链接失败: {str(e)}"
        except Exception as e:
            db.session.rollback()
            logger.error(f"创建硬链接时发生错误: {e}")
            return False, f"发生错误: {str(e)}"

    @staticmethod
    def remove_hardlink(link_id: int, delete_file: bool = True) -> Tuple[bool, str]:
        """
        删除硬链接

        Args:
            link_id: 硬链接记录 ID
            delete_file: 是否同时删除硬链接文件，默认为 True

        Returns:
            Tuple[bool, str]: (是否成功, 消息)

        注意：
            - 只标记 is_active 为 False（软删除）
            - 保留数据库记录便于追溯
        """
        link_record = HardLink.query.get(link_id)
        if not link_record:
            return False, "硬链接记录不存在"

        try:
            # 删除硬链接文件（如果存在且需要删除）
            if delete_file and os.path.exists(link_record.link_path):
                os.remove(link_record.link_path)
                logger.info(f"删除硬链接文件: {link_record.link_path}")

            # 标记为非活跃（软删除）
            link_record.is_active = False
            db.session.commit()
            return True, "硬链接已删除"

        except Exception as e:
            db.session.rollback()
            logger.error(f"删除硬链接失败: {e}")
            return False, f"删除失败: {str(e)}"

    @staticmethod
    def remove_by_source(source_path: str, delete_source: bool = False) -> Tuple[bool, str]:
        """
        根据源文件路径删除所有相关硬链接

        Args:
            source_path: 原始文件路径
            delete_source: 是否同时删除源文件，默认为 False

        Returns:
            Tuple[bool, str]: (是否成功, 消息)

        使用场景：
            - 当原文件被删除时，同步清理硬链接
            - 当用户选择删除原文件及其硬链接时
        """
        # 查找该源文件对应的所有硬链接记录
        links = HardLink.query.filter_by(source_path=source_path, is_active=True).all()
        if not links:
            return False, "没有找到相关的硬链接"

        deleted_count = 0
        errors = []

        # 逐个删除硬链接文件
        for link in links:
            try:
                if os.path.exists(link.link_path):
                    os.remove(link.link_path)
                    logger.info(f"删除硬链接文件: {link.link_path}")
                    deleted_count += 1

                # 标记为非活跃
                link.is_active = False
            except Exception as e:
                errors.append(f"{link.link_path}: {str(e)}")

        # 如果需要，删除源文件
        if delete_source and os.path.exists(source_path):
            try:
                os.remove(source_path)
                logger.info(f"删除源文件: {source_path}")
            except Exception as e:
                errors.append(f"源文件 {source_path}: {str(e)}")

        db.session.commit()

        if errors:
            return False, f"部分删除失败: {'; '.join(errors)}"
        return True, f"成功删除 {deleted_count} 个硬链接"

    @staticmethod
    def get_link_by_source(source_path: str) -> Optional[HardLink]:
        """
        获取源文件对应的硬链接记录

        Args:
            source_path: 原始文件路径

        Returns:
            HardLink 或 None: 找到的记录，不存在则返回 None
        """
        return HardLink.query.filter_by(source_path=source_path, is_active=True).first()

    @staticmethod
    def get_all_links(search: str = None, include_inactive: bool = False) -> list:
        """
        获取所有硬链接记录

        Args:
            search: 搜索关键字，会匹配 source_path 或 link_path
            include_inactive: 是否包含已删除的记录

        Returns:
            list: HardLink 对象列表，按创建时间倒序排列
        """
        query = HardLink.query

        # 是否包含已删除记录
        if not include_inactive:
            query = query.filter_by(is_active=True)

        # 搜索过滤
        if search:
            query = query.filter(
                db.or_(
                    HardLink.source_path.contains(search),
                    HardLink.link_path.contains(search)
                )
            )

        # 按创建时间倒序，最新的在前面
        return query.order_by(HardLink.created_at.desc()).all()

    @staticmethod
    def cleanup_invalid_links() -> int:
        """
        清理无效的硬链接记录

        场景：
            - 原文件被手动删除，但数据库记录仍存在
            - 硬链接文件被手动删除，但数据库记录仍存在

        处理：
            - 检查硬链接文件是否仍存在
            - 如果不存在，标记 is_active 为 False

        Returns:
            int: 清理的记录数量
        """
        links = HardLink.query.filter_by(is_active=True).all()
        cleaned = 0

        for link in links:
            # 检查硬链接文件是否还存在
            if not os.path.exists(link.link_path):
                link.is_active = False
                cleaned += 1
                logger.info(f"标记无效链接为非活跃: {link.link_path}")

        db.session.commit()
        return cleaned
