"""
视频处理工具模块
"""

import os
import hashlib
import subprocess
import json
import logging
import re
import unicodedata
import threading
from functools import lru_cache
from typing import Optional, Sequence

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


# 标题精简仅使用本地规则，不访问网络，也不推测文件中没有的信息。
_NAME_TECH_RE = re.compile(
    r'(?<![a-z0-9\u3400-\u9fff])(?:'
    r'(?:480|576|720|1080|1440|2160|4320)[pi]|[48]k|'
    r'[hx][ .]?26[45]|hevc|avc|av1|bluray|blu-ray|bdrip|'
    r'web[ .-]?(?:dl|rip)|hdtv|remux|uhd|hdr10\+?|hdr|sdr|'
    r'(?:8|10|12)[ -]?bit|aac|ac3|eac3|dts(?:-hd)?|truehd|'
    r'\d+(?:\.\d+)?\s*(?:gib|mib|gb|mb|fps)'
    r')(?![a-z0-9\u3400-\u9fff])', re.IGNORECASE
)
_NAME_URL_RE = re.compile(
    r'(?:https?://|www\.)[a-z0-9.-]+(?::\d+)?(?:/[^\s\[\]【】()（）<>]*)?',
    re.IGNORECASE
)
_NAME_DOMAIN_RE = re.compile(
    r'(?:[a-z0-9-]+\.)+(?:com|net|org|cn|cc|tv|xyz|top|vip)', re.IGNORECASE
)
_NAME_PROMO_RE = re.compile(
    r'(?:高清(?:完整版)?|超清|蓝光|完整版|无水印|无广告|免费下载|'
    r'试看版|收藏版|精校版|[\w\u3400-\u9fff]{0,16}首发|'
    r'(?:更多资源|下载地址|关注公众号|加入群聊)[:：\s].*)', re.IGNORECASE
)
_NAME_HASH_RE = re.compile(r'(?:[0-9a-f]{16,64}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})', re.IGNORECASE)
_NAME_ID_RE = re.compile(
    r'(?<![a-z0-9])(?:s\d{1,2}(?:e\d{1,3})+(?:-e?\d{1,3})?|\d{1,2}x\d{1,3}|'
    r'(?:v|vid(?:eo)?|clip|file|img|dsc|ep?|part|cd|disc|p|season|s)[ ._-]*\d{1,6}|'
    r'第[零〇一二两三四五六七八九十百千\d]+[集期章节季部]|'
    r'(?:19|20)\d{2}(?:[-.年]\d{1,2}(?:[-.月]\d{1,2}日?)?)?|'
    r'[a-z]{2,10}-\d{2,6})(?![a-z0-9])', re.IGNORECASE
)

_NAME_GENERIC_RE = re.compile(
    r'(?:\d+(?:[ ._-]\d+)*|s\d+(?:e\d+)+(?:-e?\d+)?|\d{1,2}x\d{1,3}|'
    r'(?:v|vid(?:eo)?|clip|file|img|dsc|ep?|part|cd|disc|p|season|s)[ ._-]*\d+|'
    r'第[零〇一二两三四五六七八九十百千\d]+[集期章节季部]|'
    r'video|videos|movie|clip|file|untitled|download|downloads|media|temp|tmp|source|'
    r'视频|下载|素材|待整理|未分类|未命名|新建文件夹|合集)', re.IGNORECASE
)

# 通用口语和推广词只影响关键词候选，不会直接从短标题中删除。
_TITLE_STOP_WORDS = frozenset('''
这个 那个 这些 那些 这样 那样 这么 那么 什么 怎么 为什么 如何
我们 你们 他们 她们 自己 大家 一起 真的 非常 特别 十分 已经
就是 还是 但是 然后 因为 所以 如果 可以 可能 不是 没有 一个 一种
你爱 爱了 了吗 喜欢 看到 看看 看完 带你 带来 今天 这次 这期
点击 观看 点赞 收藏 关注 分享 转发 精彩 福利 震撼 千万 不要 错过
高清 超清 完整版 首发 免费 下载 视频 资源 合集
'''.split())
_title_keyword_lock = threading.Lock()
# 关键词提取前也保护用空格分隔的纯数字编号，日期等完整标识优先匹配。
_TITLE_IDENTIFIER_RE = re.compile(_NAME_ID_RE.pattern + r'|(?<!\w)\d+(?!\w)', re.IGNORECASE)


@lru_cache(maxsize=1)
def _get_title_keyword_extractor():
    """首次需要关键词时加载词典，独立实例不修改 jieba 的全局词库。"""
    try:
        import jieba
        from jieba.analyse import TFIDF
    except ImportError:
        logger.warning('jieba 未安装，智能精简暂时沿用规则，请安装 requirements.txt 中的依赖')
        return None
    extractor = TFIDF()
    extractor.tokenizer = jieba.Tokenizer()
    extractor.stop_words = set(extractor.stop_words) | _TITLE_STOP_WORDS
    return extractor


def _split_title_identifiers(parts):
    """提取日期、季集和编号，让关键词筛选不会丢弃这些区分信息。"""
    identifiers = []
    seen = set()
    bodies = []
    for part in parts:
        matches = [part] if part.isdecimal() else _TITLE_IDENTIFIER_RE.findall(part)
        for identifier in matches:
            if identifier.casefold() not in seen:
                identifiers.append(identifier)
                seen.add(identifier.casefold())
        body = '' if part.isdecimal() else _TITLE_IDENTIFIER_RE.sub(' ', part)
        body = re.sub(r'\s+', ' ', body).strip(' .-')
        if body:
            bodies.append(body)
    return identifiers, bodies


def _join_keyword_spans(text, spans):
    """按原文位置组合；相邻词恢复成短语，不按权重重新编排语序。"""
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return ' '.join(text[start:end] for start, end in merged)


def _compact_title_keywords(text, max_length, max_bytes):
    """提取最多六个关键词，按整词预算选择；失败交回原有规则处理。"""
    if max_length < 4 or max_bytes < 12:
        return '', [], '长度不足以保留关键词，沿用规则精简'
    try:
        # 同时保护首次词典加载和提取，避免监控与预览并发初始化。
        with _title_keyword_lock:
            extractor = _get_title_keyword_extractor()
            if extractor is None:
                return '', [], 'jieba 未安装，沿用规则精简'
            weighted_words = extractor.extract_tags(text, topK=30, withWeight=True)
    except Exception as error:
        logger.warning('jieba 关键词提取失败，沿用规则: %s', error)
        return '', [], 'jieba 关键词提取失败，沿用规则精简'

    selected = []
    spans = []
    seen = set()
    for word, _ in weighted_words:
        key = _title_key(word)
        if (not key or key in seen or word.casefold() in _TITLE_STOP_WORDS
                or not any(char.isalpha() for char in word)
                or _NAME_GENERIC_RE.fullmatch(word) or _NAME_HASH_RE.fullmatch(word)):
            continue
        start = text.find(word)
        if start < 0:
            continue
        trial = spans + [(start, start + len(word))]
        candidate = _join_keyword_spans(text, trial)
        if len(candidate) > max_length or len(candidate.encode('utf-8')) > max_bytes:
            continue
        selected.append((start, word))
        spans = trial
        seen.add(key)
        if len(selected) >= 6:
            break
    compacted = _join_keyword_spans(text, spans)
    if len(selected) < 2 or len(compacted) < 4:
        return '', [], '有效关键词不足，沿用规则精简'
    if len(compacted) >= len(text):
        return '', [], ''
    keywords = [word for _, word in sorted(selected)]
    return compacted, keywords, 'jieba / TF-IDF 提取关键词：' + '、'.join(keywords)


def _title_key(text: str) -> str:
    return re.sub(r'[\W_]+', '', text).casefold()


def _title_score(text: str) -> int:
    """对有效片段排序；编号单独保留，不因分数低而丢失。"""
    letters = sum(char.isalpha() for char in text)
    chinese = len(re.findall(r'[\u3400-\u9fff]', text))
    return min(letters, 30) + min(chinese, 15) + (10 if letters else 0)


def _fit_title(text: str, max_length: int, max_bytes: int = 220) -> str:
    """兼顾字符数和常见文件系统的字节限制，优先在片段边界截断。"""
    prefix = text[:max_length].encode('utf-8')[:max_bytes].decode('utf-8', errors='ignore')
    if len(prefix) < len(text):
        boundaries = list(re.finditer(r'[\s，,；;：:。!！?？、-]', prefix))
        if boundaries and boundaries[-1].start() >= len(prefix) * 0.6:
            prefix = prefix[:boundaries[-1].start()]
    return prefix.strip(' .-_，,；;：:。!！?？、')


def simplify_video_filename(filename: str, max_length: int = 60,
                            parent_names: Optional[Sequence[str]] = None,
                            *, use_keywords: bool = True) -> dict:
    """精简标题；无意义名称按由近到远的父目录回退，不读写文件。"""
    if type(max_length) is not int or not 20 <= max_length <= 80:
        raise ValueError('标题长度必须是 20～80 的整数')

    def result(name, reasons, fallback=False, keywords=None):
        return {
            'original': filename, 'filename': name, 'changed': name != filename,
            'reasons': reasons, 'fallback': fallback, 'keywords': keywords or []
        }

    stem, extension = os.path.splitext(filename)
    text = unicodedata.normalize('NFKC', stem)
    reasons = []
    cleaned = _NAME_URL_RE.sub(' ', text)
    if cleaned != text:
        reasons.append('移除网址')
    text = cleaned.replace('_', '|')
    cleaned = _NAME_TECH_RE.sub(' ', text)
    if cleaned != text:
        reasons.append('移除分辨率、编码或大小等标签')
    # 保留括号内的有效标题，只有明确的广告、技术标签和哈希片段会被丢弃。
    raw_parts = re.split(r'[\[\]【】()（）{}｛｝《》<>|｜]+|\s+[-—–]+\s+', cleaned)
    parts = []
    seen = set()
    for raw in raw_parts:
        part = raw.strip(' .-')
        if not part:
            continue
        if _NAME_DOMAIN_RE.fullmatch(part) or _NAME_PROMO_RE.fullmatch(part):
            reasons.append('移除推广或冗余标签')
            continue
        if _NAME_HASH_RE.fullmatch(part):
            reasons.append('移除哈希片段')
            continue
        # 点分隔的英文标题转为空格，日期和小数中的点保留。
        part = re.sub(r'(?<!\d)\.|\.(?!\d)', ' ', part)
        part = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', ' ', part)
        part = ''.join(char for char in part if unicodedata.category(char) != 'Cf')
        part = re.sub(r'\s+', ' ', part).strip(' .-')
        key = _title_key(part)
        if not key:
            continue
        if key in seen:
            reasons.append('合并重复片段')
            continue
        seen.add(key)
        parts.append(part)

    title = ' - '.join(parts)
    if (not parts or not any(_title_score(part) >= 10 for part in parts)
            or all(_NAME_GENERIC_RE.fullmatch(part) for part in parts)):
        for parent_name in parent_names or ():
            # 附加虚拟扩展名，防止目录里的点或年份被当成文件扩展名剥离。
            parent = simplify_video_filename(parent_name + '.mp4', 80, use_keywords=False)
            if parent['fallback']:
                continue
            parent_title = os.path.splitext(parent['filename'])[0]
            # 原始 V1、V2、001 等作为编号保留，不人为生成顺序。
            combined = parent_title + (' - ' + title if title else '') + extension
            renamed = simplify_video_filename(combined, max_length, use_keywords=use_keywords)
            if not renamed['fallback']:
                details = [f'从上级目录「{parent_name}」提取标题']
                if title:
                    details.append('保留原文件编号或标识')
                details.extend(reason for reason in renamed['reasons'] if reason != '未发现需要精简的内容')
                return result(renamed['filename'], details, keywords=renamed['keywords'])
        return result(filename, ['未找到有效标题或有意义的上级目录，保留原名'], True)

    selected_keywords = []
    chinese_count = len(re.findall(r'[\u3400-\u9fff]', title))
    # 即使未达到配置长度，描述性长句也进行提取；短标题和纯英文沿用规则。
    if use_keywords and (chinese_count >= 24 or (chinese_count >= 8 and len(title) > max_length)):
        identifiers, bodies = _split_title_identifiers(parts)
        suffix = (' - ' + ' '.join(identifiers)) if identifiers else ''
        compacted, selected_keywords, detail = _compact_title_keywords(
            ' - '.join(bodies), max_length - len(suffix), 220 - len(suffix.encode('utf-8'))
        )
        if detail:
            reasons.append(detail)
        if compacted:
            title = compacted + suffix
            parts = [compacted] + identifiers

    if len(title) > max_length or len(title.encode('utf-8')) > 220:
        # 缩短标题时预留日期、季集和编号，避免不同集被截成相同标题。
        identifiers, bodies = _split_title_identifiers(parts)
        suffix = (' - ' + ' '.join(identifiers)) if identifiers else ''
        budget = max_length - len(suffix)
        byte_budget = 220 - len(suffix.encode('utf-8'))
        if budget < 4 or byte_budget < 12 or not bodies:
            return result(filename, ['无法在长度限制内保留标题及编号，保留原名'], True)
        while len(bodies) > 1:
            body = ' - '.join(bodies)
            if len(body) <= budget and len(body.encode('utf-8')) <= byte_budget:
                break
            # 同分时先舍弃靠后的片段，保留原始顺序，不生成新文字。
            weakest = min(range(len(bodies)), key=lambda i: (_title_score(bodies[i]), -i))
            bodies.pop(weakest)
        title = _fit_title(' - '.join(bodies), budget, byte_budget) + suffix
        reasons.append('按片段评分精简长度，并保留日期及编号')

    # Windows 设备名不可作为文件名；其他平台也使用同一规则，便于迁移。
    if re.fullmatch(r'con|prn|aux|nul|com[1-9]|lpt[1-9]', title.split('.')[0], re.IGNORECASE):
        title = '_' + title
    new_name = title + extension
    if new_name != filename and not reasons:
        reasons.append('整理分隔符及文件名字符')
    reasons = list(dict.fromkeys(reasons))
    return result(new_name, reasons or ['未发现需要精简的内容'], keywords=selected_keywords)


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
