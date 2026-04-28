"""
视频处理工具模块

功能说明：
    1. 使用 ffprobe 获取视频文件的时长、大小等信息
    2. 格式化视频时长和文件大小的显示

依赖：
    - ffprobe（来自 ffmpeg 包）
    - subprocess（标准库）

安装 ffmpeg：
    # Ubuntu/Debian
    apt install ffmpeg

    # macOS
    brew install ffmpeg

    # Windows
    choco install ffmpeg
"""

import os
import subprocess
import json
from typing import Optional


def get_video_duration(file_path: str) -> Optional[float]:
    """
    使用 ffprobe 获取视频时长（秒）

    Args:
        file_path: 视频文件路径

    Returns:
        float 或 None: 视频时长（秒），获取失败返回 None

    说明：
        - ffprobe 是 ffmpeg 的一部分，用于读取媒体文件信息
        - 超时时间设置为 30 秒
        - 如果文件不存在或 ffprobe 失败，返回 None
    """
    if not os.path.exists(file_path):
        return None

    # ffprobe 命令参数说明：
    # -v quiet: 只输出错误信息
    # -print_format json: 输出 JSON 格式
    # -show_format: 输出格式信息（包含时长）
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        file_path
    ]

    try:
        # 执行命令，设置超时避免长时间阻塞
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            data = json.loads(result.stdout)
            # 从 JSON 中提取 duration 字段
            duration = float(data.get('format', {}).get('duration', 0))
            return duration

    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        pass

    return None


def get_video_info(file_path: str) -> dict:
    """
    获取视频文件的详细信息

    Args:
        file_path: 视频文件路径

    Returns:
        dict: 包含以下字段的字典
            - duration: 视频时长（秒）
            - size: 文件大小（字节）
            - format: 视频格式名称

    说明：
        - 同时获取时长、大小、格式信息
        - 相比 get_video_duration 更全面
        - 适合需要多信息的场景
    """
    info = {
        'duration': 0.0,
        'size': 0,
        'format': None
    }

    if not os.path.exists(file_path):
        return info

    # -show_streams: 输出流信息（视频、音频等）
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
    """
    将秒数格式化为 HH:MM:SS 格式

    Args:
        seconds: 秒数（可以是浮点数）

    Returns:
        str: 格式化后的字符串

    Examples:
        format_duration(3661) -> "01:01:01"
        format_duration(65) -> "00:01:05"
        format_duration(0) -> "00:00:00"
    """
    if seconds <= 0:
        return "00:00:00"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_size(bytes_size: int) -> str:
    """
    将字节大小格式化为可读字符串

    Args:
        bytes_size: 字节大小（整数）

    Returns:
        str: 格式化后的字符串

    Examples:
        format_size(1024) -> "1.00 KB"
        format_size(1048576) -> "1.00 MB"
        format_size(1073741824) -> "1.00 GB"

    说明：
        - 自动选择合适的单位（B, KB, MB, GB, TB）
        - 保留两位小数
        - 最小单位是字节
    """
    if bytes_size <= 0:
        return "0 B"

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    size = float(bytes_size)

    # 循环除以 1024，直到无法继续或到达最大单位
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    return f"{size:.2f} {units[unit_index]}"
