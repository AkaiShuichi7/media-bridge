"""
@description 后台监控任务核心逻辑
@responsibility 监控115离线任务状态，任务完成时触发文件整理，失败时记录到数据库
"""

import asyncio
import random
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from loguru import logger
from sqlalchemy import select

from app.core.database import get_session
from app.models.offline_task import OfflineTask
from app.utils.helpers import find_library_by_name


# 轮询间隔最小值（秒）
POLL_INTERVAL_MIN = 60
# 轮询间隔最大值（秒）
POLL_INTERVAL_MAX = 80

if TYPE_CHECKING:
    from app.services.cloud.base import CloudService

class TaskMonitor:
    """后台监控任务管理器"""

    def __init__(self, p115_client: "CloudService", file_organizer, config):
        self._client = p115_client
        self._organizer = file_organizer
        self._config = config
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._processed_hashes: set[str] = set()
        self.last_check_time: Optional[datetime] = None

    def _find_library_by_name(self, name: str):
        """通过名称在配置中查找媒体库。"""
        return find_library_by_name(self._config.media.libraries, name)

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
        """检查所有离线任务状态 - 只处理系统添加的任务"""
        try:
            # 1. 查询数据库获取系统任务的 info_hash 列表
            async with get_session() as session:
                result = await session.execute(
                    select(OfflineTask.info_hash).where(
                        OfflineTask.status.in_(["added", "downloading"])
                    )
                )
                system_hashes = set(row[0] for row in result.fetchall())

            if not system_hashes:
                return

            # 2. 获取 115 离线任务列表（CloudService 返回已解析的列表）
            tasks = await self._client.get_offline_tasks()
            if isinstance(tasks, dict):
                tasks = tasks.get("tasks") or tasks.get("data") or []
            if not isinstance(tasks, list):
                logger.error(f"获取离线任务列表返回异常类型: {type(tasks)}")
                return

            # 3. 只处理系统添加的任务
            for task in tasks:
                info_hash = task.get("info_hash")
                if info_hash and info_hash in system_hashes:
                    await self._process_task(task)

        except Exception as e:
            logger.error(f"检查任务时发生错误: {e}")
        finally:
            self.last_check_time = datetime.now()

    async def _process_task(self, task: dict) -> None:
        """处理单个离线任务"""
        info_hash = task.get("info_hash")
        status = task.get("status")
        name = task.get("name", "未知任务")

        if info_hash in self._processed_hashes:
            return

        if status == 2:
            logger.info(f"任务 [{name}] 已完成，开始整理文件")
            if await self._handle_completed_task(task):
                self._processed_hashes.add(info_hash)

        elif status < 0:  # 负数表示失败（如 -1）
            logger.warning(f"任务 [{name}] 下载失败 (status={status})")
            await self._handle_failed_task(task)
            self._processed_hashes.add(info_hash)

    async def _handle_completed_task(self, task: dict) -> bool:
        """处理已完成的任务 - 触发文件整理"""
        info_hash = task.get("info_hash")

        # 通过数据库查询 library_name
        library_config = None
        if info_hash:
            try:
                async with get_session() as session:
                    result = await session.execute(
                        select(OfflineTask.library_name).where(
                            OfflineTask.info_hash == info_hash
                        )
                    )
                    library_name = result.scalar_one_or_none()
                    if library_name:
                        library_config = find_library_by_name(self._config.media.libraries, library_name)
                        logger.debug(f"通过数据库找到 library: {library_name}")
            except Exception as e:
                logger.error(f"查询 library_name 失败: {e}")

        if library_config is None:
            # 路径回退: 当 DB 查询失败或无结果时，尝试通过任务路径匹配媒体库
            task_path = task.get("path", "")
            for lib in self._config.media.libraries:
                if task_path.startswith(lib.download_path):
                    library_config = lib
                    logger.debug(f"通过路径回退找到 library: {lib.name}")
                    break
        if library_config is None:
            logger.error(
                f"无法确定任务 [{task.get('name', 'unknown')}] 的 library 配置，跳过整理"
            )
            return False

        task_path = task.get("path", "")
        download_path_id = ""
        logger.debug(f"任务 [{task.get('name', 'unknown')}] 路径信息: {task_path or '(空)'}")
        if task_path:
            parent_path = "/".join(task_path.rstrip("/").split("/")[:-1])
            if parent_path:
                download_path_id = await self._client.get_path_id(parent_path)
                logger.debug(
                    f"任务 [{task.get('name', 'unknown')}] 下载路径 ID: {parent_path} -> {download_path_id}"
                )

        task_info = {
            "task_id": task.get("info_hash"),
            "info_hash": task.get("info_hash"),
            "name": task.get("name", "未知任务"),
            "path_id": str(task.get("file_id", "")),
            "download_path_id": download_path_id or "",
        }

        # xx 配置可选：未配置时传 None，organizer 内部按空关键词处理
        xx_config = self._config.media.xx if self._config.media.xx else None

        try:
            # 配置对象直接透传，不再手工拍平成裸 dict
            result = await self._organizer.organize_task(
                task_info, library_config, self._config.media, xx_config
            )
            logger.info(
                f"任务整理完成: 成功 {result['success_count']}, "
                f"失败 {result['failed_count']}, 跳过 {result['skipped_count']}"
            )

            if result["failed_count"]:
                await self._update_task_status(
                    info_hash, "organize_failed", "; ".join(result.get("errors", []))
                )
                return False

            await self._update_task_status(info_hash, "completed")
            try:
                await self._client.delete_offline_task(info_hash)
            except Exception as e:
                logger.warning(f"任务 [{task_info['name']}] 清理失败: {e}")
            return True

        except Exception as e:
            logger.error(f"整理任务时发生错误: {e}")
            await self._update_task_status(info_hash, "organize_failed", str(e))
            return False

    async def _handle_failed_task(self, task: dict) -> None:
        """处理失败的任务 - 保存记录到数据库"""
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(OfflineTask).where(OfflineTask.info_hash == task.get("info_hash"))
                )
                offline_task = result.scalar_one_or_none()
                if offline_task is None:
                    offline_task = OfflineTask(info_hash=task.get("info_hash"))
                    session.add(offline_task)
                offline_task.name = task.get("name")
                offline_task.status = "failed"
                offline_task.add_time = datetime.fromtimestamp(task.get("add_time", 0))
                offline_task.error_message = task.get("error_msg", "下载失败")
                await session.commit()
                logger.info(f"失败任务已记录到数据库: {task.get('name')}")
        except Exception as e:
            logger.error(f"保存失败任务记录时出错: {e}")

    async def _update_task_status(
        self, info_hash: str | None, status: str, error_message: str | None = None
    ) -> None:
        if not info_hash:
            return
        async with get_session() as session:
            result = await session.execute(
                select(OfflineTask).where(OfflineTask.info_hash == info_hash)
            )
            offline_task = result.scalar_one_or_none()
            if offline_task is None or not hasattr(offline_task, "status"):
                return
            offline_task.status = status
            offline_task.error_message = error_message
            if status == "completed":
                offline_task.complete_time = datetime.now()
            await session.commit()

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


async def start_monitor(p115_client, file_organizer, config) -> TaskMonitor:
    """创建并启动监控实例的便捷函数"""
    monitor = TaskMonitor(p115_client, file_organizer, config)
    await monitor.start_monitor()
    return monitor


async def stop_monitor(monitor: TaskMonitor) -> None:
    """停止监控实例的便捷函数"""
    await monitor.stop_monitor()
