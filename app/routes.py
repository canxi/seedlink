import os
from flask import Blueprint, render_template, request, jsonify
from app.models import db, HardLink
from app.config import config
from app.services.hardlink import HardLinkService
from app.services.scanner import ScannerService
from app.services.watcher import get_watcher
from app.utils.video import format_duration, format_size


bp = Blueprint('main', __name__)


@bp.route('/logs')
def logs():
    return render_template('logs.html')


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/settings')
def settings():
    return render_template('settings.html')


@bp.route('/links')
def links():
    return render_template('links.html')


@bp.route('/api/settings', methods=['GET'])
def get_settings():
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
    data = request.get_json()

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

    config.save()

    watcher = get_watcher()
    if watcher.is_running():
        watcher.restart()

    return jsonify({'success': True, 'message': '设置已保存'})


@bp.route('/api/settings/scan', methods=['POST'])
def trigger_scan():
    import threading
    from app import create_app

    def run_scan():
        app = create_app()
        with app.app_context():
            scanner = ScannerService()
            scanner.scan_and_create_hardlinks()

    thread = threading.Thread(target=run_scan)
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'message': '扫描已在后台启动'
    })


@bp.route('/api/links', methods=['GET'])
def get_links():
    search = request.args.get('search', '')
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'

    links = HardLinkService.get_all_links(search=search, include_inactive=include_inactive)

    return jsonify({
        'links': [link.to_dict() for link in links],
        'total': len(links)
    })


@bp.route('/api/links/<int:link_id>', methods=['DELETE'])
def delete_link(link_id):
    success, message = HardLinkService.remove_hardlink(link_id, delete_file=True)
    return jsonify({'success': success, 'message': message})


@bp.route('/api/links/<int:link_id>/delete-source', methods=['DELETE'])
def delete_link_and_source(link_id):
    link = HardLink.query.get(link_id)
    if not link:
        return jsonify({'success': False, 'message': '记录不存在'})

    success, message = HardLinkService.remove_by_source(link.source_path, delete_source=True)
    return jsonify({'success': success, 'message': message})


@bp.route('/api/stats', methods=['GET'])
def get_stats():
    total_links = HardLink.query.filter_by(is_active=True).count()
    total_size = db.session.query(db.func.sum(HardLink.file_size)).filter_by(is_active=True).scalar() or 0

    watcher = get_watcher()
    watching = watcher.is_running()

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
    watcher = get_watcher()
    return jsonify({
        'running': watcher.is_running()
    })


@bp.route('/api/watcher/start', methods=['POST'])
def watcher_start():
    watcher = get_watcher()
    if watcher.is_running():
        return jsonify({'success': True, 'running': True, 'message': '监控已在运行'})

    if not os.path.exists(config.source_folder):
        return jsonify({
            'success': False,
            'running': False,
            'message': f'源文件夹不存在: {config.source_folder}'
        }), 400

    watcher.start()
    return jsonify({'success': True, 'running': watcher.is_running()})


@bp.route('/api/watcher/stop', methods=['POST'])
def watcher_stop():
    watcher = get_watcher()
    if watcher.is_running():
        watcher.stop()
    return jsonify({'success': True, 'running': watcher.is_running()})


@bp.route('/api/logs', methods=['GET'])
def get_logs():
    from app.utils.log_buffer import get_log_buffer
    level = request.args.get('level')
    limit = int(request.args.get('limit', 100))
    logs = get_log_buffer().get_logs(level=level, limit=limit)
    return jsonify({
        'logs': logs,
        'total': len(logs)
    })


@bp.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    from app.utils.log_buffer import get_log_buffer
    get_log_buffer().clear()
    return jsonify({'success': True, 'message': '日志已清空'})
