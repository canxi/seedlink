"""
视频处理工具模块
"""

import os
import hashlib
import subprocess
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# MD5 chunk size: 8MB - good balance for memory and progress
MD5_CHUNK_SIZE = 8 * 1024 * 1024


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
    """获取视频文件的详细信息（含视频流和音频流）"""
    info = {
        'duration': 0.0,
        'size': 0,
        'format': None,
        'video': None,
        'audio': None
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

            # 提取视频流和音频流信息
            for stream in data.get('streams', []):
                codec_type = stream.get('codec_type', '')
                if codec_type == 'video' and info['video'] is None:
                    # 解析帧率 (如 "24000/1001" → 23.976)
                    fps = 0.0
                    r_frame_rate = stream.get('r_frame_rate', '0/1')
                    try:
                        num, den = r_frame_rate.split('/')
                        den_val = float(den) if float(den) != 0 else 1
                        fps = round(float(num) / den_val, 3)
                    except (ValueError, ZeroDivisionError):
                        pass

                    info['video'] = {
                        'codec': stream.get('codec_name', ''),
                        'width': int(stream.get('width', 0)),
                        'height': int(stream.get('height', 0)),
                        'fps': fps,
                        'bitrate': int(stream.get('bit_rate', 0)) if stream.get('bit_rate') else 0
                    }
                elif codec_type == 'audio' and info['audio'] is None:
                    info['audio'] = {
                        'codec': stream.get('codec_name', ''),
                        'channels': int(stream.get('channels', 0)),
                        'language': stream.get('tags', {}).get('language', '')
                    }

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


def calculate_md5(file_path: str, chunk_size: int = MD5_CHUNK_SIZE) -> Optional[str]:
    """计算文件的 MD5 值（分块读取，适合大文件）"""
    if not os.path.exists(file_path):
        return None

    md5_hash = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except (IOError, OSError) as e:
        logger.warning(f"计算 MD5 失败 {file_path}: {e}")
        return None
