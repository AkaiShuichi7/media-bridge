"""
@description 应用容器
@responsibility 统一创建和持有所有服务实例，收敛 app.state 初始化逻辑
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from app.core.config import Config
    from app.services.p115_client import P115Client
    from app.services.cloud.base import CloudService
    from app.services.cloud.p115 import P115CloudService
    from app.services.file_organizer import FileOrganizer
    from app.tasks.monitor import TaskMonitor


class AppContainer:
    """
    应用服务容器。

    统一管理所有核心服务的创建顺序和生命周期，
    替代 lifespan 中分散的 app.state.xxx = ... 赋值。
    """

    def __init__(self) -> None:
        self.config: Config | None = None
        self.p115_client: P115Client | None = None
        self.cloud_service: P115CloudService | None = None
        self.file_organizer: FileOrganizer | None = None
        self.task_monitor: TaskMonitor | None = None
        self.auth_service = None

    async def init(self, config: Config) -> None:
        """
        按依赖顺序初始化所有服务。

        Args:
            config: 已加载的应用配置
        """
        from app.core.database import init_db
        from app.services.p115_client import P115Client
        from app.services.cloud.p115 import P115CloudService
        from app.services.file_organizer import FileOrganizer
        from app.tasks.monitor import TaskMonitor

        self.config = config
        logger.info("配置加载完成")

        await init_db(config.database.url)
        from app.services.auth import AuthService
        self.auth_service = AuthService()
        await self.auth_service.initialize()
        logger.info("数据库初始化完成")

        # 创建 115 客户端（单例）
        self.p115_client = await P115Client.get_client(config.cloud.p115.cookies)

        # 验证 cookies
        if not await self.p115_client.verify_cookies():
            logger.error("115 Cookies 验证失败，请检查配置")
        else:
            logger.info("115 Cookies 验证成功")

        # CloudService 实现封装 P115Client
        self.cloud_service = P115CloudService(self.p115_client)

        # 路径缓存随应用关闭时清理过期条目（防缓存表无限膨胀）
        self._path_cache = self.p115_client._path_cache

        # 文件整理器和监控器依赖 CloudService 接口
        self.file_organizer = FileOrganizer(self.cloud_service)
        self.task_monitor = TaskMonitor(
            self.cloud_service,
            self.file_organizer,
            config,
        )

        await self.task_monitor.start_monitor()
        logger.info("后台监控任务已启动")

    async def shutdown(self) -> None:
        """停止所有后台服务，并顺手清理已过期的路径缓存条目"""
        if self.task_monitor:
            await self.task_monitor.stop_monitor()
            logger.info("后台监控任务已停止")

        # 关闭前批量清理过期缓存条目（失败不阻断关闭流程）
        if self._path_cache:
            try:
                deleted = await self._path_cache.cleanup()
                logger.info(f"路径缓存清理完成，删除过期条目 {deleted} 条")
            except Exception as e:
                logger.warning(f"路径缓存清理失败（忽略）: {e}")
