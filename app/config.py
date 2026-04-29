import os
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    # 本地开发加载 .env.local，Docker 环境由 env_file 加载
    env_local = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env.local')
    load_dotenv(env_local, override=True)
except ImportError:
    pass


class Config:
    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _env_file_path(self) -> str:
        # Docker 环境: /app/data/.env (通过 docker-compose 的 volumes ./data:/app/data 映射)
        # 本地开发: .env.local
        if os.path.exists('/app/data'):
            return '/app/data/.env'
        return '.env.local'

    def _write_env_file(self):
        """直接写入 .env 文件，不触发 reload"""
        env_path = self._env_file_path()
        env_dir = os.path.dirname(env_path)
        if env_dir and not os.path.exists(env_dir):
            os.makedirs(env_dir, exist_ok=True)

        lines = [
            f"SOURCE_FOLDER={self._config['app']['source_folder']}",
            f"TARGET_FOLDER={self._config['app']['target_folder']}",
            f"MIN_DURATION={self._config['app']['min_duration']}",
            f"SCAN_INTERVAL={self._config['app']['scan_interval']}",
            f"VIDEO_EXTENSIONS={','.join(self._config['app']['video_extensions'])}",
            f"DEBUG={'true' if self._config['app']['debug'] else 'false'}",
        ]

        with open(env_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        logger.info(f"[Config] _write_env_file: 已写入 {env_path}")

    def _load_config(self):
        """从环境变量加载配置到内存"""
        self._config = {
            'app': {
                'source_folder': os.environ.get('SOURCE_FOLDER', '/downloads'),
                'target_folder': os.environ.get('TARGET_FOLDER', '/media'),
                'min_duration': int(os.environ.get('MIN_DURATION', 600)),
                'scan_interval': int(os.environ.get('SCAN_INTERVAL', 60)),
                'video_extensions': os.environ.get('VIDEO_EXTENSIONS', '.mkv,.mp4,.avi,.ts,.mov,.wmv,.flv').split(','),
                'debug': os.environ.get('DEBUG', 'false').lower() == 'true'
            },
            'database': {
                'uri': os.environ.get('DATABASE_URI', 'sqlite:////app/data/hardlinks.db')
            }
        }

    def reload(self):
        """重新加载配置（从文件读取最新值）"""
        env_path = self._env_file_path()
        logger.info(f"[Config] reload: 文件路径={env_path}, 存在={os.path.exists(env_path)}")

        if os.path.exists(env_path):
            try:
                from dotenv import dotenv_values
                env_vars = dotenv_values(env_path)
                logger.info(f"[Config] reload: 读取到的变量={list(env_vars.keys())}")
                for key, value in env_vars.items():
                    os.environ[key] = value
                logger.info(f"[Config] reload: SOURCE_FOLDER={os.environ.get('SOURCE_FOLDER')}, TARGET_FOLDER={os.environ.get('TARGET_FOLDER')}")
            except Exception as e:
                logger.error(f"[Config] reload 失败: {e}")
        else:
            # 文件不存在，写入默认配置
            logger.info(f"[Config] reload: .env 文件不存在，创建默认配置")
            self._write_env_file()

        self._load_config()

    def save(self):
        """保存配置到文件"""
        self._write_env_file()
        self.reload()

    def get(self, key: str, default: Any = None) -> Any:
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
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    @property
    def source_folder(self) -> str:
        return self.get('app.source_folder', '/downloads')

    @property
    def target_folder(self) -> str:
        return self.get('app.target_folder', '/media')

    @property
    def min_duration(self) -> int:
        return self.get('app.min_duration', 600)

    @property
    def scan_interval(self) -> int:
        return self.get('app.scan_interval', 60)

    @property
    def video_extensions(self) -> List[str]:
        ext = self.get('app.video_extensions', ['.mkv', '.mp4', '.avi', '.ts'])
        if isinstance(ext, str):
            ext = ext.split(',')
        return ext

    @property
    def debug(self) -> bool:
        return self.get('app.debug', False)

    @property
    def database_uri(self) -> str:
        return self.get('database.uri', 'sqlite:////app/data/hardlinks.db')


config = Config()
