import os
import yaml
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
        config_path = os.environ.get('CONFIG_PATH', '/app/config/config.yaml')

        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = self._default_config()
            self._ensure_directory(config_path)
            self.save()

    def _ensure_directory(self, config_path):
        config_dir = os.path.dirname(config_path)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)

    def _default_config(self) -> Dict[str, Any]:
        return {
            'app': {
                'source_folder': '/downloads',
                'target_folder': '/media',
                'min_duration': 600,
                'scan_interval': 60,
                'video_extensions': ['.mkv', '.mp4', '.avi', '.ts', '.mov', '.wmv', '.flv'],
                'debug': False
            },
            'database': {
                'uri': 'sqlite:///data/hardlinks.db'
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

    def save(self):
        config_path = os.environ.get('CONFIG_PATH', '/app/config/config.yaml')
        self._ensure_directory(config_path)
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(self._config, f, allow_unicode=True, default_flow_style=False)

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
