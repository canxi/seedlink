"""
视频处理工具模块
"""

import os
import subprocess
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_video_duration(file_path: str) -> Optional[float]:
    """使用 ffprobe 获取视频时长（秒）"""
    if not os.path.exists(file_path):
        return None

    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        file_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            data = json.loads(result.stdout)
            duration = float(data.get('format', {}).get('duration', 0))
            return duration
        else:
            logger.warning(f"ffprobe 执行失败: {result.stderr}")
    except FileNotFoundError:
        logger.warning("ffprobe 未找到，请安装 ffmpeg 并确保 ffprobe 在 PATH 中")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        pass

    return None


def get_video_info(file_path: str) -> dict:
    """获取视频文件的详细信息"""
    info = {
        'duration': 0.0,
        'size': 0,
        'format': None
    }

    if not os.path.exists(file_path):
        return info

    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        file_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            data = json.loads(result.stdout)
            format_info = data.get('format', {})

            info['duration'] = float(format_info.get('duration', 0))
            info['size'] = int(format_info.get('size', 0))
            info['format'] = format_info.get('format_name')

    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        pass

    return info


def format_duration(seconds: float) -> str:
    """将秒数格式化为 HH:MM:SS 格式"""
    if seconds <= 0:
        return "00:00:00"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_size(bytes_size: int) -> str:
    """将字节大小格式化为可读字符串"""
    if bytes_size <= 0:
        return "0 B"

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    size = float(bytes_size)

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    return f"{size:.2f} {units[unit_index]}"
