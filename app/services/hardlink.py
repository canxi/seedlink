"""
硬链接核心服务模块
"""

import os
import logging
from pathlib import Path
from typing import Optional, Tuple, List
from app.models import db, HardLink
from app.utils.video import get_video_duration, get_video_info
from app.config import config
from app.services.nfo import NfoService


logger = logging.getLogger(__name__)


class HardLinkService:

    @staticmethod
    def create_hardlink(source_path: str, target_path: str, duration: float = 0, file_size: int = 0, md5: str = None) -> Tuple[bool, str]:
        try:
            src = Path(source_path)
            dest = Path(target_path)

            if not src.exists():
                return False, f"源文件不存在: {source_path}"

            if dest.exists():
                return False, f"目标文件已存在: {target_path}"

            dest.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"[诊断] 创建硬链接前 - 源: {src}, 目标: {dest}")
            logger.info(f"[诊断] 源文件 stat: {src.stat()}")

            # 使用 pathlib 创建硬链接
            dest.hardlink_to(src)

            # 验证硬链接是否有效（检查 inode 是否相同）
            if dest.stat().st_ino != src.stat().st_ino:
                dest.unlink()
                return False, "硬链接创建失败：inode 不匹配"

            # 诊断：列出目标目录内容
            logger.info(f"[诊断] 创建硬链接后 - 目标文件是否存在: {dest.exists()}")
            logger.info(f"[诊断] 目标目录内容: {list(dest.parent.iterdir())}")
            logger.info(f"[诊断] 目标文件 stat: {dest.stat()}")

            link_record = HardLink(
                source_path=source_path,
                link_path=target_path,
                file_size=file_size or src.stat().st_size,
                duration=duration,
                md5=md5,
                is_active=True
            )
            db.session.add(link_record)
            db.session.commit()

            # 生成 NFO 元数据文件
            if config.generate_nfo:
                try:
                    nfo_ok, nfo_msg = NfoService.generate_nfo(target_path)
                    if not nfo_ok:
                        logger.warning(f"NFO 生成失败: {nfo_msg}")
                except Exception as nfo_err:
                    logger.warning(f"NFO 生成异常: {nfo_err}")

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

            # 删除对应的 NFO 文件
            NfoService.remove_nfo(link_record.link_path)

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
                # 删除对应的 NFO 文件
                NfoService.remove_nfo(link.link_path)
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

    @staticmethod
    def cleanup_deleted_sources() -> Tuple[int, int, List[str]]:
        """
        扫描所有活跃的硬链接记录,清理源文件已被删除的记录:
        - 若 source_path 不存在于磁盘,则删除对应的 link_path 硬链接文件
        - 将这些记录标记为 is_active=False
        这是 watcher.on_deleted() 反应式清理的补充安全网,用于处理
        应用离线、watchdog 漏检或外部删除等情况。
        Returns:
            (checked, cleaned, errors): 检查总数,清理总数,错误信息列表
        """
        links = HardLink.query.filter_by(is_active=True).all()
        checked = len(links)
        cleaned = 0
        errors = []

        for link in links:
            # 仅当源文件已不存在时才清理(源文件被删除的情况)
            if not os.path.exists(link.source_path):
                try:
                    if os.path.exists(link.link_path):
                        os.remove(link.link_path)
                        logger.info(f"清理已删除源文件的硬链接: {link.link_path}")
                    # 清理对应的 NFO 文件
                    NfoService.remove_nfo(link.link_path)
                    link.is_active = False
                    cleaned += 1
                    logger.info(f"标记非活跃(源文件已删除): {link.source_path}")
                except Exception as e:
                    errors.append(f"{link.link_path}: {str(e)}")
                    logger.error(f"清理记录失败 {link.source_path}: {e}")

        db.session.commit()
        logger.info(f"源文件清理扫描完成: 检查 {checked} 条,清理 {cleaned} 条,错误 {len(errors)} 条")
        return checked, cleaned, errors
