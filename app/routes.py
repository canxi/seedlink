"""
Web 路由模块

功能说明：
    1. 定义所有页面路由（/、/settings、/links）
    2. 定义所有 API 路由（/api/*）
    3. 处理前端请求并返回 JSON 响应或 HTML 页面

路由列表：
    页面路由：
        GET /           - 仪表盘页面
        GET /settings   - 设置页面
        GET /links      - 硬链接列表页面

    API 路由：
        GET  /api/stats             - 获取统计信息
        GET  /api/settings          - 获取配置
        PUT  /api/settings          - 更新配置
        POST /api/settings/scan     - 触发手动扫描
        GET  /api/links             - 获取硬链接列表
        DELETE /api/links/<id>      - 删除硬链接
        DELETE /api/links/<id>/delete-source - 删除原文件和硬链接
        GET  /api/watcher/status    - 获取监控状态
        POST /api/watcher/start     - 启动监控
        POST /api/watcher/stop      - 停止监控
"""

import os
from flask import Blueprint, render_template, request, jsonify
from app.models import db, HardLink
from app.config import config
from app.services.hardlink import HardLinkService
from app.services.scanner import ScannerService
from app.services.watcher import get_watcher
from app.utils.video import format_duration, format_size


# 创建蓝图
# url_prefix 会自动添加到所有路由前面
# 这里的蓝图没有设置 url_prefix，所以在使用时 routes.py 中的路由会直接以 / 开头
bp = Blueprint('main', __name__)


# ==================== 页面路由 ====================

@bp.route('/')
def index():
    """
    仪表盘页面

    显示：
        - 硬链接总数
        - 总大小
        - 监控状态
        - 最小视频时长
        - 最近创建的硬链接列表
        - 快速操作按钮
    """
    return render_template('index.html')


@bp.route('/settings')
def settings():
    """
    设置页面

    显示：
        - 源文件夹路径输入
        - 目标文件夹路径输入
        - 最小视频时长滑块
        - 扫描间隔输入
        - 视频扩展名多选
        - 保存按钮
    """
    return render_template('settings.html')


@bp.route('/links')
def links():
    """
    硬链接列表页面

    显示：
        - 所有硬链接记录表格
        - 搜索框
        - 显示/隐藏已删除记录的开关
        - 删除操作按钮
    """
    return render_template('links.html')


# ==================== API 路由 ====================

@bp.route('/api/settings', methods=['GET'])
def get_settings():
    """
    获取所有配置

    Returns:
        JSON: 包含所有配置项的字典
    """
    settings_data = {
        'source_folder': config.source_folder,
        'target_folder': config.target_folder,
        'min_duration': config.min_duration,
        'scan_interval': config.scan_interval,
        'video_extensions': config.video_extensions
    }
    return jsonify(settings_data)


@bp.route('/api/settings', methods=['PUT'])
def update_settings():
    """
    更新配置

    请求体（JSON）：
        source_folder: 源文件夹路径
        target_folder: 目标文件夹路径
        min_duration: 最小视频时长（秒）
        scan_interval: 扫描间隔（秒）
        video_extensions: 视频扩展名列表

    Returns:
        JSON: {"success": true, "message": "设置已保存"}
    """
    data = request.get_json()

    # 更新各项配置（只更新提供的字段）
    if 'source_folder' in data:
        config.set('app.source_folder', data['source_folder'])
    if 'target_folder' in data:
        config.set('app.target_folder', data['target_folder'])
    if 'min_duration' in data:
        config.set('app.min_duration', int(data['min_duration']))
    if 'scan_interval' in data:
        config.set('app.scan_interval', int(data['scan_interval']))
    if 'video_extensions' in data:
        config.set('app.video_extensions', data['video_extensions'])

    # 保存到配置文件
    config.save()

    # 如果监控服务正在运行，重启它以应用新配置
    watcher = get_watcher()
    if watcher.is_running():
        watcher.restart()

    return jsonify({'success': True, 'message': '设置已保存'})


@bp.route('/api/settings/scan', methods=['POST'])
def trigger_scan():
    """
    触发手动扫描

    扫描源文件夹中的所有视频文件，
    为符合条件的文件创建硬链接

    Returns:
        JSON: {
            "success": true,
            "processed": 处理的文件数,
            "created": 创建的硬链接数,
            "errors": 错误列表
        }
    """
    scanner = ScannerService()
    processed, created, errors = scanner.scan_and_create_hardlinks()

    return jsonify({
        'success': True,
        'processed': processed,
        'created': created,
        'errors': errors
    })


@bp.route('/api/links', methods=['GET'])
def get_links():
    """
    获取硬链接列表

    查询参数：
        search: 搜索关键字（可选）
        include_inactive: 是否包含已删除记录，true/false（可选）

    Returns:
        JSON: {
            "links": [硬链接对象列表],
            "total": 总数
        }
    """
    search = request.args.get('search', '')
    # 将字符串 'true'/'false' 转换为布尔值
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'

    links = HardLinkService.get_all_links(search=search, include_inactive=include_inactive)

    return jsonify({
        'links': [link.to_dict() for link in links],
        'total': len(links)
    })


@bp.route('/api/links/<int:link_id>', methods=['DELETE'])
def delete_link(link_id):
    """
    删除指定硬链接

    Args:
        link_id: 硬链接记录 ID

    Returns:
        JSON: {"success": true/false, "message": "错误信息或成功信息"}
    """
    success, message = HardLinkService.remove_hardlink(link_id, delete_file=True)
    return jsonify({'success': success, 'message': message})


@bp.route('/api/links/<int:link_id>/delete-source', methods=['DELETE'])
def delete_link_and_source(link_id):
    """
    删除原始文件和对应的所有硬链接

    Args:
        link_id: 硬链接记录 ID

    Returns:
        JSON: {"success": true/false, "message": "错误信息或成功信息"}
    """
    link = HardLink.query.get(link_id)
    if not link:
        return jsonify({'success': False, 'message': '记录不存在'})

    # 删除原文件和所有硬链接
    success, message = HardLinkService.remove_by_source(link.source_path, delete_source=True)
    return jsonify({'success': success, 'message': message})


@bp.route('/api/stats', methods=['GET'])
def get_stats():
    """
    获取统计信息

    用于仪表盘显示系统状态

    Returns:
        JSON: 包含各项统计数据的字典
    """
    # 统计活跃硬链接总数
    total_links = HardLink.query.filter_by(is_active=True).count()

    # 统计总大小
    total_size = db.session.query(db.func.sum(HardLink.file_size)).filter_by(is_active=True).scalar() or 0

    # 获取监控状态
    watcher = get_watcher()
    watching = watcher.is_running()

    # 获取最近创建的 5 个硬链接
    recent_links = HardLink.query.filter_by(is_active=True).order_by(
        HardLink.created_at.desc()
    ).limit(5).all()

    return jsonify({
        'total_links': total_links,
        'total_size': total_size,
        'total_size_formatted': format_size(total_size),
        'watching': watching,
        'source_folder': config.source_folder,
        'target_folder': config.target_folder,
        'min_duration': config.min_duration,
        'recent_links': [link.to_dict() for link in recent_links]
    })


@bp.route('/api/watcher/status', methods=['GET'])
def watcher_status():
    """
    获取文件监控服务状态

    Returns:
        JSON: {"running": true/false}
    """
    watcher = get_watcher()
    return jsonify({
        'running': watcher.is_running()
    })


@bp.route('/api/watcher/start', methods=['POST'])
def watcher_start():
    """
    启动文件监控服务

    启动后会监控源文件夹，
    新增或删除文件时会自动处理

    Returns:
        JSON: {"success": true, "running": true/false}
    """
    watcher = get_watcher()
    if not watcher.is_running():
        watcher.start()
    return jsonify({'success': True, 'running': watcher.is_running()})


@bp.route('/api/watcher/stop', methods=['POST'])
def watcher_stop():
    """
    停止文件监控服务

    Returns:
        JSON: {"success": true, "running": true/false}
    """
    watcher = get_watcher()
    if watcher.is_running():
        watcher.stop()
    return jsonify({'success': True, 'running': watcher.is_running()})
