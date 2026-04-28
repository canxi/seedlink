import os
from typing import Any, Dict, List


class Config:
    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        # 只从环境变量读取配置
        self._config = {
            'app': {
                'source_folder': os.environ.get('SOURCE_FOLDER', '/downloads'),
                'target_folder': os.environ.get('TARGET_FOLDER', '/media'),
                'min_duration': int(os.environ.get('MIN_DURATION', 600)),
                'scan_interval': int(os.environ.get('SCAN_INTERVAL', 60)),
                'video_extensions': ['.mkv', '.mp4', '.avi', '.ts', '.mov', '.wmv', '.flv'],
                'debug': os.environ.get('DEBUG', 'false').lower() == 'true'
            },
            'database': {
                'uri': os.environ.get('DATABASE_URI', 'sqlite:///data/hardlinks.db')
            }
        }

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
        return self.get('app.video_extensions', ['.mkv', '.mp4', '.avi', '.ts'])

    @property
    def debug(self) -> bool:
        return self.get('app.debug', False)

    @property
    def database_uri(self) -> str:
        return self.get('database.uri', 'sqlite:///data/hardlinks.db')


config = Config()
