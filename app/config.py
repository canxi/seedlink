"""
配置管理模块

功能说明：
    1. 从 config.yaml 加载配置
    2. 提供配置的读取和修改接口
    3. 支持配置持久化到文件

设计模式：
    使用单例模式，确保全局只有一个配置实例

配置文件格式（YAML）：
    app:
        source_folder: 源文件夹路径
        target_folder: 目标文件夹路径
        min_duration: 最小视频时长（秒）
        scan_interval: 扫描间隔（秒）
        video_extensions: 监控的文件扩展名列表
        debug: 调试模式开关

    database:
        uri: 数据库连接 URI
"""

import os
import yaml
from typing import Any, Dict, List


class Config:
    """
    配置管理类（单例模式）

    使用方式：
        config = Config()  # 获取单例实例
        source = config.source_folder  # 读取配置
        config.set('app.min_duration', 300)  # 修改配置
        config.save()  # 保存到文件
    """

    _instance = None  # 单例实例
    _config: Dict[str, Any] = {}  # 配置字典

    def __new__(cls):
        """
        实现单例模式
        每次调用 Config() 都返回同一个实例
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """
        从 YAML 文件加载配置
        如果文件不存在，使用默认配置
        """
        # 支持通过环境变量指定配置文件路径
        config_path = os.environ.get('CONFIG_PATH', 'config.yaml')

        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
        else:
            # 文件不存在时使用默认配置
            self._config = self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        """
        获取默认配置

        Returns:
            包含默认配置的字典
        """
        return {
            'app': {
                'source_folder': '/downloads',  # PT 下载目录
                'target_folder': '/media',  # 媒体库目录
                'min_duration': 600,  # 10 分钟
                'scan_interval': 60,  # 1 分钟
                'video_extensions': ['.mkv', '.mp4', '.avi', '.ts', '.mov', '.wmv', '.flv'],
                'debug': False
            },
            'database': {
                'uri': 'sqlite:///data/hardlinks.db'
            }
        }

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值，支持嵌套 key

        Args:
            key: 配置键，使用点号分隔，如 'app.source_folder'
            default: 默认值，当 key 不存在时返回

        Returns:
            配置值

        Example:
            config.get('app.min_duration')  # 返回 600
            config.get('app.source_folder', '/default')  # 返回 '/downloads'
        """
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any):
        """
        设置配置值，支持嵌套 key

        Args:
            key: 配置键，使用点号分隔
            value: 要设置的值
        """
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def save(self):
        """
        将当前配置保存到 YAML 文件
        """
        config_path = os.environ.get('CONFIG_PATH', 'config.yaml')
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(self._config, f, allow_unicode=True, default_flow_style=False)

    # ----------------------
    # 便捷属性访问器
    # ----------------------

    @property
    def source_folder(self) -> str:
        """源文件夹路径（PT 下载目录）"""
        return self.get('app.source_folder', '/downloads')

    @property
    def target_folder(self) -> str:
        """目标文件夹路径（硬链接存放位置）"""
        return self.get('app.target_folder', '/media')

    @property
    def min_duration(self) -> int:
        """最小视频时长（秒），低于此值不创建硬链接"""
        return self.get('app.min_duration', 600)

    @property
    def scan_interval(self) -> int:
        """扫描间隔（秒）"""
        return self.get('app.scan_interval', 60)

    @property
    def video_extensions(self) -> List[str]:
        """监控的视频文件扩展名列表"""
        return self.get('app.video_extensions', ['.mkv', '.mp4', '.avi', '.ts'])

    @property
    def debug(self) -> bool:
        """调试模式开关"""
        return self.get('app.debug', False)

    @property
    def database_uri(self) -> str:
        """SQLAlchemy 数据库连接 URI"""
        return self.get('database.uri', 'sqlite:///data/hardlinks.db')


# 全局配置单例
config = Config()
