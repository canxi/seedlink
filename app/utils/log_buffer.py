"""
日志缓冲处理器
将日志输出到内存缓冲区，供前端查看
"""

import logging
import threading
from typing import List
from datetime import datetime


class LogBufferHandler(logging.Handler):
    """日志处理器，将日志写入缓冲区"""

    def __init__(self, max_size: int = 1000):
        super().__init__()
        self.buffer: List[dict] = []
        self.max_size = max_size
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            log_entry = {
                'timestamp': datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S'),
                'level': record.levelname,
                'logger': record.name,
                'message': msg
            }
            with self._lock:
                self.buffer.append(log_entry)
                # 超过最大容量时移除最旧的
                if len(self.buffer) > self.max_size:
                    self.buffer = self.buffer[-self.max_size:]
        except Exception:
            self.handleError(record)

    def get_logs(self, level: str = None, limit: int = 100) -> List[dict]:
        """获取日志"""
        with self._lock:
            logs = self.buffer[-limit:] if limit > 0 else self.buffer
            if level:
                logs = [log for log in logs if log['level'] == level]
            return logs

    def clear(self):
        """清空日志"""
        with self._lock:
            self.buffer.clear()


# 全局日志缓冲区
_log_buffer = LogBufferHandler(max_size=1000)


def get_log_buffer() -> LogBufferHandler:
    return _log_buffer


def setup_log_buffer():
    """设置日志缓冲处理器"""
    import app
    handler = get_log_buffer()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    app.logger.addHandler(handler)
    # 设置根日志器
    logging.getLogger().addHandler(handler)
