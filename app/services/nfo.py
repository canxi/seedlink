"""
NFO 元数据生成服务

功能说明：
    为硬链接的视频文件自动生成 .nfo 元数据文件，供 Emby/Jellyfin/Kodi 等
    媒体服务器直接识别和刮削。

工作流程：
    1. 通过 ffprobe 获取视频流和音频流信息
    2. 从文件名解析标题（电影名或剧集季/集信息）
    3. 生成符合 Kodi/Emby NFO 规范的 XML 文件
    4. 将 .nfo 文件写入视频文件同目录，文件名与视频文件相同但扩展名为 .nfo
"""

import os
import re
import logging
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Optional, Tuple
from app.utils.video import get_video_info

logger = logging.getLogger(__name__)

# 常见的 PT 文件名标签，解析标题时需要清除
_TAG_PATTERNS = [
    # 分辨率
    r'\b\d{3,4}p\b', r'\b4K\b', r'\b2160P\b', r'\b1080P\b', r'\b720P\b',
    # 来源
    r'\bBluRay\b', r'\bBDRip\b', r'\bWEBRip\b', r'\bWEB-DL\b', r'\bHDTV\b',
    r'\bDVDRip\b', r'\bREMUX\b', r'\bUHD\b',
    # 编码
    r'\bx264\b', r'\bx265\b', r'\bH\.?264\b', r'\bH\.?265\b', r'\bHEVC\b',
    r'\bAVC\b', r'\bVC-?1\b', r'\bMPEG-?2\b', r'\bAV1\b',
    # 音频编码
    r'\bDTS\b', r'\bDTS-HD\b', r'\bDTS-HDMA\b', r'\bTrueHD\b', r'\bAtmos\b',
    r'\bAAC\b', r'\bAC3\b', r'\bEAC3\b', r'\bFLAC\b', r'\bDDP\b', r'\bDD\b',
    r'\bDD\+?\b', r'\bLPCM\b',
    # 其他标签
    r'\bREPACK\b', r'\bPROPER\b', r'\bEXTENDED\b', r'\bUNCUT\b',
    r'\bIMAX\b', r'\bHYBRID\b', r'\bREMASTERED\b', r'\bINTERNAL\b',
    r'\b10bit\b', r'\b10BIT\b', r'\bSDR\b', r'\bHDR\b', r'\bDV\b',
    r'\bMULTi\b', r'\bDUAL\b', r'\bDUAL-AUDIO\b',
    # 码率/组名等末尾方括号内容
    r'\[[^\]]+\]',
]

# 合并为一个正则
_TAG_REGEX = re.compile('|'.join(_TAG_PATTERNS), re.IGNORECASE)

# 剧集季集匹配：S01E05, s01e05, 1x05
_EPISODE_REGEX = re.compile(r'[Ss](\d{1,2})[Ee](\d{1,3})|(\d{1,2})x(\d{1,3})')

# 年份匹配
_YEAR_REGEX = re.compile(r'\b(19\d{2}|20\d{2})\b')


class NfoService:
    """NFO 元数据生成服务"""

    @staticmethod
    def parse_filename(filename: str) -> dict:
        """
        从文件名解析标题信息

        Returns:
            dict:
                - title: 清理后的标题
                - original_title: 原始文件名（不含扩展名）
                - is_episode: 是否为剧集
                - season: 季号（剧集时）
                - episode: 集号（剧集时）
                - show_title: 剧集名（剧集时）
                - year: 年份（电影时，如有）
        """
        # 去除扩展名
        name = os.path.splitext(filename)[0]

        result = {
            'title': '',
            'original_title': name,
            'is_episode': False,
            'season': None,
            'episode': None,
            'show_title': None,
            'year': None
        }

        # 检测剧集季集信息
        ep_match = _EPISODE_REGEX.search(name)
        if ep_match:
            result['is_episode'] = True
            if ep_match.group(1):
                result['season'] = int(ep_match.group(1))
                result['episode'] = int(ep_match.group(2))
            else:
                result['season'] = int(ep_match.group(3))
                result['episode'] = int(ep_match.group(4))

            # 剧集名 = 季集标记之前的部分
            show_part = name[:ep_match.start()]
            result['show_title'] = _clean_title(show_part)
            result['title'] = result['show_title']
        else:
            # 电影：提取年份
            year_match = _YEAR_REGEX.search(name)
            if year_match:
                result['year'] = year_match.group(1)
                title_part = name[:year_match.start()]
            else:
                title_part = name

            result['title'] = _clean_title(title_part)

        return result

    @staticmethod
    def generate_nfo(video_path: str) -> Tuple[bool, str]:
        """
        为视频文件生成 .nfo 元数据文件

        Args:
            video_path: 视频文件路径

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        if not os.path.exists(video_path):
            return False, f"视频文件不存在: {video_path}"

        # 获取视频信息
        info = get_video_info(video_path)
        if info['duration'] == 0 and info['video'] is None:
            logger.warning(f"无法获取视频信息，跳过 NFO 生成: {video_path}")
            return False, "无法获取视频信息"

        # 解析文件名
        filename = os.path.basename(video_path)
        parsed = NfoService.parse_filename(filename)

        # 生成 XML
        xml_str = NfoService._build_nfo_xml(info, parsed)

        # 写入 .nfo 文件
        nfo_path = os.path.splitext(video_path)[0] + '.nfo'
        try:
            with open(nfo_path, 'w', encoding='utf-8') as f:
                f.write(xml_str)
            logger.info(f"已生成 NFO 文件: {nfo_path}")
            return True, f"NFO 已生成: {nfo_path}"
        except IOError as e:
            logger.error(f"写入 NFO 文件失败: {e}")
            return False, f"写入 NFO 失败: {str(e)}"

    @staticmethod
    def remove_nfo(video_path: str) -> bool:
        """
        删除视频文件对应的 .nfo 文件

        Args:
            video_path: 视频文件路径

        Returns:
            bool: 是否成功删除（文件不存在也返回 True）
        """
        nfo_path = os.path.splitext(video_path)[0] + '.nfo'
        if os.path.exists(nfo_path):
            try:
                os.remove(nfo_path)
                logger.info(f"已删除 NFO 文件: {nfo_path}")
                return True
            except OSError as e:
                logger.warning(f"删除 NFO 文件失败: {e}")
                return False
        return True

    @staticmethod
    def _build_nfo_xml(info: dict, parsed: dict) -> str:
        """构建 NFO XML 内容"""
        if parsed['is_episode']:
            root = ET.Element('episodedetails')
        else:
            root = ET.Element('movie')

        # 基本信息
        title_el = ET.SubElement(root, 'title')
        title_el.text = parsed['title'] or parsed['original_title']

        original_el = ET.SubElement(root, 'originaltitle')
        original_el.text = parsed['original_title']

        # 时长（分钟）
        runtime = max(1, round(info['duration'] / 60))
        runtime_el = ET.SubElement(root, 'runtime')
        runtime_el.text = str(runtime)

        # 年份（仅电影）
        if not parsed['is_episode'] and parsed['year']:
            year_el = ET.SubElement(root, 'year')
            year_el.text = parsed['year']

        # 剧集额外信息
        if parsed['is_episode']:
            show_el = ET.SubElement(root, 'showtitle')
            show_el.text = parsed['show_title'] or ''

            season_el = ET.SubElement(root, 'season')
            season_el.text = str(parsed['season'])

            episode_el = ET.SubElement(root, 'episode')
            episode_el.text = str(parsed['episode'])

        # 文件流信息
        fileinfo_el = ET.SubElement(root, 'fileinfo')
        streamdetails_el = ET.SubElement(fileinfo_el, 'streamdetails')

        # 视频流
        video_info = info.get('video')
        if video_info:
            video_el = ET.SubElement(streamdetails_el, 'video')
            _add_text_element(video_el, 'codec', video_info['codec'])
            _add_text_element(video_el, 'width', str(video_info['width']))
            _add_text_element(video_el, 'height', str(video_info['height']))
            _add_text_element(video_el, 'durationinseconds', str(int(info['duration'])))
            if video_info['fps'] > 0:
                _add_text_element(video_el, 'fps', str(video_info['fps']))
            if video_info['bitrate'] > 0:
                _add_text_element(video_el, 'bitrate', str(video_info['bitrate']))

            # 宽高比
            if video_info['width'] > 0 and video_info['height'] > 0:
                aspect = round(video_info['width'] / video_info['height'], 4)
                _add_text_element(video_el, 'aspect', str(aspect))

        # 音频流
        audio_info = info.get('audio')
        if audio_info:
            audio_el = ET.SubElement(streamdetails_el, 'audio')
            _add_text_element(audio_el, 'codec', audio_info['codec'])
            _add_text_element(audio_el, 'channels', str(audio_info['channels']))
            if audio_info['language']:
                _add_text_element(audio_el, 'language', audio_info['language'])

        # 美化输出
        rough = ET.tostring(root, encoding='unicode')
        parsed_xml = minidom.parseString(rough)
        return parsed_xml.toprettyxml(indent='  ', encoding='UTF-8').decode('utf-8')


def _clean_title(text: str) -> str:
    """清理文件名中的标签，提取干净的标题"""
    # 替换点和下划线为空格
    title = text.replace('.', ' ').replace('_', ' ')
    # 移除已知标签
    title = _TAG_REGEX.sub(' ', title)
    # 合并多余空格
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def _add_text_element(parent: ET.Element, tag: str, text: str):
    """添加子元素并设置文本"""
    el = ET.SubElement(parent, tag)
    el.text = text
