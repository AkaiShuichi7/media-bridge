"""
@description 后台离线任务轮询器
@responsibility 只负责轮询循环：取任务列表 → 比对中立状态 → 调用 OfflineTaskService；
                状态迁移与整理编排全部收敛在领域服务内，本模块不再直接触达数据库
"""

import asyncio
import random
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from loguru import logger

from app.services.cloud.base import CloudTaskStatus


# 轮询间隔最小值（秒）
POLL_INTERVAL_MIN = 60
# 轮询间隔最大值（秒）
POLL_INTERVAL_MAX = 80

if TYPE_CHECKING:
    from app.core.config import Config
    from app.services.cloud.base import CloudService
    from app.services.offline_task_service import OfflineTaskService

class TaskMonitor:
    """后台监控任务管理器

    纯轮询器：不持有任何业务状态。跨轮的重复处理防护由 DB 生命周期状态推导
    （任务迁移到终态后自动退出 added/downloading 轮询集合），无需内存去重集合。
    """

    def __init__(
        self,
        cloud_service: "CloudService",
        offline_task_service: "OfflineTaskService",
        config: "Config",
    ):
        self._cloud = cloud_service
        self._task_service = offline_task_service
        self._config = config
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self.last_check_time: Optional[datetime] = None

    async def start_monitor(self) -> None:
        """启动监控任务"""
        if self._task is not None and not self._task.done():
            logger.warning("监控任务已在运行中")
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("后台监控任务已启动")

    async def stop_monitor(self) -> None:
        """停止监控任务"""
        if self._task is None:
            return

        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("等待监控任务停止超时，强制取消")
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("后台监控任务已停止")

    async def check_tasks(self) -> None:
        """单轮检查：拉取轮询集合与云端任务列表，比对中立状态后交由领域服务处理"""
        try:
            # 1. 查询数据库获取系统任务的 info_hash 轮询集合（added/downloading）
            active_hashes = await self._task_service.list_active_hashes()
            if not active_hashes:
                return

            # 2. 获取离线任务列表（CloudService 已翻译为标准 CloudTask 列表）
            tasks = await self._cloud.get_offline_tasks()

            # 3. 只处理系统添加的任务，按中立状态分派给领域服务
            # 单轮内的去重集合；跨轮去重由 DB 生命周期状态推导：
            # 任务一旦迁移到终态便退出 added/downloading 轮询集合，不会重复整理
            seen: set[str] = set()
            for task in tasks:
                if not task.info_hash or task.info_hash not in active_hashes:
                    continue
                if task.info_hash in seen:
                    continue
                seen.add(task.info_hash)

                if task.status is CloudTaskStatus.COMPLETED:
                    await self._task_service.handle_completed_task(task)
                elif task.status is CloudTaskStatus.FAILED:
                    await self._task_service.mark_download_failed(task)

        except Exception as e:
            logger.error(f"检查任务时发生错误: {e}")
        finally:
            self.last_check_time = datetime.now()

    def _get_random_interval(self) -> float:
        """获取随机轮询间隔（秒），配置缺失时使用默认常量"""
        cloud_cfg = getattr(self._config, 'cloud', None)
        min_interval = getattr(cloud_cfg, 'poll_interval_min', POLL_INTERVAL_MIN)
        max_interval = getattr(cloud_cfg, 'poll_interval_max', POLL_INTERVAL_MAX)
        return random.uniform(min_interval, max_interval)

    async def _monitor_loop(self) -> None:
        """监控主循环"""
        while not self._stop_event.is_set():
            try:
                await self.check_tasks()
            except Exception as e:
                logger.error(f"监控循环出错: {e}")

            interval = self._get_random_interval()
            # 等待下次轮询，如果中途收到 stop_event 就会提前结束 wait
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                # wait 返回 true，说明 stop_event 被 set，准备退出循环
                break
            except asyncio.TimeoutError:
                # 超时说明没有收到退出信号，继续下一轮循环
                pass
