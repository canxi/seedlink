"""
定时任务调度服务模块

基于 APScheduler 的 BackgroundScheduler,提供可扩展的定时任务调度。
单例模式,通过 get_scheduler() 获取实例。
现有任务:
    - cleanup_deleted_sources: 每天凌晨清理已删除源文件的硬链接记录
"""

import logging
import threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.schedulers import SchedulerAlreadyRunningError
from apscheduler.events import (
    EVENT_JOB_SUBMITTED, EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
)
from app.config import config


logger = logging.getLogger(__name__)


class SchedulerService:
    """
    定时任务调度服务(单例)

    仿照 WatcherService 模式,提供 start/stop/restart/is_running 接口。
    新增任务只需在 _register_jobs() 中 add_job。
    """

    def __init__(self):
        self._scheduler = None
        self._running = False
        self._job_status = {}   # job_id -> 状态 dict
        self._lock = threading.Lock()

    def start(self):
        if self._running:
            logger.warning("调度服务已在运行")
            return

        self._scheduler = BackgroundScheduler(daemon=True)
        self._scheduler.add_listener(
            self._on_job_event,
            EVENT_JOB_SUBMITTED | EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED
        )
        self._register_jobs()

        try:
            self._scheduler.start()
            self._running = True
            logger.info("定时任务调度已启动")
        except SchedulerAlreadyRunningError:
            logger.warning("调度服务已在运行(重复启动被忽略)")
        except Exception as e:
            logger.error(f"启动调度服务失败: {e}")
            self._scheduler = None

    def _register_jobs(self):
        """注册所有定时任务。新增任务在此处 add_job。"""
        cron_expr = config.cleanup_cron
        try:
            trigger = CronTrigger.from_crontab(cron_expr)
        except Exception as e:
            logger.error(f"CLEANUP_CRON 表达式无效 '{cron_expr}',回退默认 '0 3 * * *': {e}")
            trigger = CronTrigger.from_crontab('0 3 * * *')

        self._scheduler.add_job(
            func=self._cleanup_deleted_sources_job,
            trigger=trigger,
            id='cleanup_deleted_sources',
            name='清理已删除源文件',
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600
        )
        logger.info(f"已注册任务 'cleanup_deleted_sources' 触发规则: {cron_expr}")

        # 自动扫描建链任务(interval 触发)
        scan_interval = config.scan_interval
        self._scheduler.add_job(
            func=self._scan_and_create_hardlinks_job,
            trigger=IntervalTrigger(seconds=scan_interval),
            id='scan_and_create_hardlinks',
            name='自动扫描并创建硬链接',
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600
        )
        logger.info(f"已注册任务 'scan_and_create_hardlinks' 触发规则: 每 {scan_interval} 秒")

    def _on_job_event(self, event):
        """APScheduler 事件回调,跟踪任务执行状态"""
        job_id = event.job_id
        with self._lock:
            status = self._job_status.setdefault(job_id, {})
            if event.code == EVENT_JOB_SUBMITTED:
                status['running'] = True
                status['last_run_start'] = datetime.now()
            elif event.code == EVENT_JOB_EXECUTED:
                status['running'] = False
                status['last_run_end'] = datetime.now()
                status['last_run_result'] = 'success'
                status['last_run_error'] = None
                status['run_count'] = status.get('run_count', 0) + 1
                if status.get('last_run_start'):
                    start = status['last_run_start']
                    if isinstance(start, datetime):
                        status['last_run_duration'] = (status['last_run_end'] - start).total_seconds()
            elif event.code == EVENT_JOB_ERROR:
                status['running'] = False
                status['last_run_end'] = datetime.now()
                status['last_run_result'] = 'failed'
                status['last_run_error'] = str(event.exception)
                status['run_count'] = status.get('run_count', 0) + 1
                if status.get('last_run_start'):
                    start = status['last_run_start']
                    if isinstance(start, datetime):
                        status['last_run_duration'] = (status['last_run_end'] - start).total_seconds()
            elif event.code == EVENT_JOB_MISSED:
                status['last_run_result'] = 'missed'
                status['missed_count'] = status.get('missed_count', 0) + 1

    @staticmethod
    def _cleanup_deleted_sources_job():
        """清理已删除源文件的定时任务"""
        from app import create_app
        from app.services.hardlink import HardLinkService
        try:
            app = create_app()
            with app.app_context():
                checked, cleaned, errors = HardLinkService.cleanup_deleted_sources()
                logger.info(
                    f"[调度] 清理已删除源文件任务完成: "
                    f"检查 {checked}, 清理 {cleaned}, 错误 {len(errors)}"
                )
        except Exception as e:
            logger.error(f"[调度] 清理任务执行失败: {e}")

    @staticmethod
    def _scan_and_create_hardlinks_job():
        """自动扫描并创建硬链接的定时任务"""
        from app import create_app
        from app.services.scanner import ScannerService
        try:
            app = create_app()
            with app.app_context():
                scanner = ScannerService()
                processed, created, errors, skipped = scanner.scan_and_create_hardlinks()
                logger.info(
                    f"[调度] 自动扫描任务完成: "
                    f"处理 {processed}, 创建 {created}, 跳过 {len(skipped)}, 错误 {len(errors)}"
                )
        except Exception as e:
            logger.error(f"[调度] 自动扫描任务执行失败: {e}")

    def stop(self):
        if not self._running:
            return
        if self._scheduler:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception as e:
                logger.error(f"停止调度服务失败: {e}")
            self._scheduler = None
        with self._lock:
            for status in self._job_status.values():
                status['running'] = False
        self._running = False
        logger.info("定时任务调度已停止")

    def restart(self):
        self.stop()
        self.start()

    def is_running(self) -> bool:
        return self._running

    def get_jobs(self) -> list:
        """返回所有已注册任务的信息(含实时运行状态)"""
        if not self._scheduler:
            return []
        jobs = []
        with self._lock:
            for j in self._scheduler.get_jobs():
                status = self._job_status.get(j.id, {})
                last_end = status.get('last_run_end')
                jobs.append({
                    'id': j.id,
                    'name': j.name,
                    'trigger': str(j.trigger),
                    'next_run_time': j.next_run_time.isoformat() if j.next_run_time else None,
                    'running': status.get('running', False),
                    'last_run_time': last_end.isoformat() if isinstance(last_end, datetime) else None,
                    'last_run_result': status.get('last_run_result'),
                    'last_run_error': status.get('last_run_error'),
                    'last_run_duration': status.get('last_run_duration'),
                    'run_count': status.get('run_count', 0),
                    'missed_count': status.get('missed_count', 0),
                })
        return jobs


_scheduler_instance = None


def get_scheduler() -> SchedulerService:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SchedulerService()
    return _scheduler_instance
