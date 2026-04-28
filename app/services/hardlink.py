"""
硬链接核心服务模块
"""

import os
import logging
from typing import Optional, Tuple
from app.models import db, HardLink
from app.utils.video import get_video_duration, get_video_info


logger = logging.getLogger(__name__)


class HardLinkService:

    @staticmethod
    def create_hardlink(source_path: str, target_path: str, duration: float = 0, file_size: int = 0) -> Tuple[bool, str]:
        try:
            if not os.path.exists(source_path):
                return False, f"源文件不存在: {source_path}"

            if os.path.exists(target_path):
                return False, f"目标文件已存在: {target_path}"

            target_dir = os.path.dirname(target_path)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)

            # 诊断信息：检查源和目标的文件系统
            source_stat = os.stat(source_path)
            target_stat = os.stat(target_dir)
            logger.info(f"[诊断] 源文件设备: {source_stat.st_dev}, 目标目录设备: {target_stat.st_dev}, 是否同设备: {source_stat.st_dev == target_stat.st_dev}")
            logger.info(f"[诊断] 源文件路径: {source_path}")
            logger.info(f"[诊断] 目标路径: {target_path}")
            logger.info(f"[诊断] 源文件 inode: {source_stat.st_ino}")

            os.link(source_path, target_path)

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
            db.session.rollback()
            logger.error(f"创建硬链接失败: {e}")
            return False, f"创建硬链接失败: {str(e)}"
        except Exception as e:
            db.session.rollback()
            logger.error(f"创建硬链接时发生错误: {e}")
            return False, f"发生错误: {str(e)}"

    @staticmethod
    def remove_hardlink(link_id: int, delete_file: bool = True) -> Tuple[bool, str]:
        link_record = HardLink.query.get(link_id)
        if not link_record:
            return False, "硬链接记录不存在"

        try:
            if delete_file and os.path.exists(link_record.link_path):
                os.remove(link_record.link_path)
                logger.info(f"删除硬链接文件: {link_record.link_path}")

            link_record.is_active = False
            db.session.commit()
            return True, "硬链接已删除"

        except Exception as e:
            db.session.rollback()
            logger.error(f"删除硬链接失败: {e}")
            return False, f"删除失败: {str(e)}"

    @staticmethod
    def remove_by_source(source_path: str, delete_source: bool = False) -> Tuple[bool, str]:
        links = HardLink.query.filter_by(source_path=source_path, is_active=True).all()
        if not links:
            return False, "没有找到相关的硬链接"

        deleted_count = 0
        errors = []

        for link in links:
            try:
                if os.path.exists(link.link_path):
                    os.remove(link.link_path)
                    logger.info(f"删除硬链接文件: {link.link_path}")
                    deleted_count += 1
                link.is_active = False
            except Exception as e:
                errors.append(f"{link.link_path}: {str(e)}")

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
        return HardLink.query.filter_by(source_path=source_path, is_active=True).first()

    @staticmethod
    def get_all_links(search: str = None, include_inactive: bool = False) -> list:
        query = HardLink.query

        if not include_inactive:
            query = query.filter_by(is_active=True)

        if search:
            query = query.filter(
                db.or_(
                    HardLink.source_path.contains(search),
                    HardLink.link_path.contains(search)
                )
            )

        return query.order_by(HardLink.created_at.desc()).all()

    @staticmethod
    def cleanup_invalid_links() -> int:
        links = HardLink.query.filter_by(is_active=True).all()
        cleaned = 0

        for link in links:
            if not os.path.exists(link.link_path):
                link.is_active = False
                cleaned += 1
                logger.info(f"标记无效链接为非活跃: {link.link_path}")

        db.session.commit()
        return cleaned
