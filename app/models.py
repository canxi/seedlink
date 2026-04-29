"""
数据库模型模块

功能说明：
    1. 定义硬链接记录表（hard_links）
    2. 定义配置表（settings）
    3. 提供与数据库的交互接口

数据库说明：
    - 使用 SQLite 数据库
    - 通过 SQLAlchemy ORM 进行操作
    - 自动创建表结构

表结构：
    hard_links: 存储硬链接记录
        - id: 主键
        - source_path: 原始文件路径
        - link_path: 硬链接路径
        - file_size: 文件大小
        - duration: 视频时长
        - md5: 文件 MD5 哈希值
        - created_at: 创建时间
        - is_active: 是否有效（删除时标记为 False）

    settings: 存储配置（预留，目前使用 YAML 配置文件）
        - key: 配置键（主键）
        - value: 配置值
        - updated_at: 更新时间
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

# 初始化 SQLAlchemy 实例
# 稍后在 app/__init__.py 中与 Flask 应用关联
db = SQLAlchemy()


class HardLink(db.Model):
    """
    硬链接记录模型

    对应数据库表：hard_links

    使用场景：
        - 记录新创建的硬链接
        - 查询硬链接列表
        - 标记删除状态
    """

    # 表名
    __tablename__ = 'hard_links'

    # 字段定义
    id = db.Column(db.Integer, primary_key=True)  # 自增主键
    source_path = db.Column(db.String(512), nullable=False, index=True)  # 原始文件路径
    link_path = db.Column(db.String(512), nullable=False, index=True)  # 硬链接路径
    file_size = db.Column(db.BigInteger, default=0)  # 文件大小（字节）
    duration = db.Column(db.Float, default=0.0)  # 视频时长（秒）
    md5 = db.Column(db.String(32), nullable=True, index=True)  # 文件 MD5 哈希值
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # 创建时间
    is_active = db.Column(db.Boolean, default=True)  # 是否有效

    def to_dict(self):
        """
        将模型转换为字典格式，便于 JSON 序列化

        Returns:
            dict: 包含所有字段的字典
        """
        return {
            'id': self.id,
            'source_path': self.source_path,
            'link_path': self.link_path,
            'file_size': self.file_size,
            'duration': self.duration,
            'md5': self.md5,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_active': self.is_active
        }


class Setting(db.Model):
    """
    配置项模型（预留）

    对应数据库表：settings

    说明：
        目前配置使用 YAML 文件管理，此表预留用于存储动态配置
        如用户偏好设置、历史记录等
    """

    __tablename__ = 'settings'

    key = db.Column(db.String(128), primary_key=True)  # 配置键作为主键
    value = db.Column(db.Text, nullable=True)  # 配置值
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 更新时间

    def to_dict(self):
        """
        将模型转换为字典格式

        Returns:
            dict: 包含所有字段的字典
        """
        return {
            'key': self.key,
            'value': self.value,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
