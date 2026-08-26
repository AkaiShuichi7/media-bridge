"""
@description 离线任务服务
@responsibility 承载「添加离线任务」的完整业务流程：
               库解析 → 目录解析 → 云端建任务 → 本地持久化 → 失败补偿回滚；
               路由层只做协议转换，事务性规则集中在 service 内可测
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from loguru import logger
from sqlalchemy import select

from app.core.database import get_session
from app.models.offline_task import OfflineTask

if TYPE_CHECKING:
    from app.core.config import Config, LibraryConfig
    from app.services.cloud.base import CloudService


class AddTaskError(Exception):
    """添加离线任务失败的领域异常，message 面向用户可展示"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class OfflineTaskService:
    """离线任务领域服务：添加（含补偿回滚）等事务性操作"""

    def __init__(self, cloud_service: "CloudService", config: "Config"):
        self._cloud = cloud_service
        self._config = config

    def _find_library(self, library_name: str) -> Optional["LibraryConfig"]:
        """按名称查找媒体库配置，不存在返回 None"""
        for lib in self._config.media.libraries:
            if lib.name == library_name:
                return lib
        return None

    async def add_task(
        self,
        magnet: str,
        library_name: str,
        name: Optional[str],
        parsed_info_hash: Optional[str],
    ) -> str:
        """
        添加离线下载任务并持久化本地记录。

        完整流程：库校验 → 解析下载目录 → 云端建任务 → 本地 UPSERT；
        本地持久化失败时反向删除云端任务做补偿回滚。

        Args:
            magnet: 磁力链接
            library_name: 目标媒体库名称
            name: 任务显示名（空则截取 magnet 前 50 字符）
            parsed_info_hash: 调用方从 magnet 解析出的 info_hash（云端不返回时兜底）

        Returns:
            str: 最终任务 ID（info_hash；解析不出时为空字符串）

        Raises:
            AddTaskError: 媒体库不存在 / 目录解析失败 / 云端添加失败 / 本地保存失败（已回滚）
        """
        library = self._find_library(library_name)
        if library is None:
            raise AddTaskError(f"媒体库 '{library_name}' 不存在")

        # 解析下载目录 ID（115 路径式 API）
        try:
            path_id = await self._cloud.get_path_id(
                library.download_path, library_name=library.name
            )
        except Exception as e:
            logger.error(f"[add_task] 获取下载目录 ID 报错: {e}")
            raise AddTaskError(f"获取下载目录 ID 报错: {e}") from e

        if path_id is None:
            logger.error(f"[add_task] 获取下载目录 ID 失败: {library.download_path}")
            raise AddTaskError(f"获取下载目录 ID 失败: {library.download_path}")

        # 云端创建任务；适配器保证返回 (成功, 错误信息, info_hash)
        add_ok, add_error, api_info_hash = await self._cloud.add_offline_task(
            magnet, path_id
        )
        if not add_ok:
            logger.error(f"[add_task] 添加离线任务失败: {add_error}")
            raise AddTaskError(f"添加离线任务失败: {add_error}")

        # 优先级：云端返回的 info_hash > magnet 解析的 > None
        final_info_hash = api_info_hash or parsed_info_hash
        display_name = name if name else magnet[:50]
        logger.debug(f"[add_task] 最终 info_hash: {final_info_hash}")

        # 本地持久化；失败时补偿回滚云端任务
        try:
            await self._upsert_task_record(final_info_hash, display_name, library.name)
        except Exception as e:
            logger.error(f"保存离线任务失败: {e}")
            await self._rollback_cloud_task(final_info_hash)
            raise AddTaskError(
                "任务已提交至 115，但本地记录保存失败；已尝试回滚，请检查日志后重试"
            ) from e

        return final_info_hash or ""

    async def _upsert_task_record(
        self, info_hash: Optional[str], name: str, library_name: str
    ) -> None:
        """
        按 info_hash UPSERT 本地离线任务记录（存在则更新，不存在则创建）。

        Args:
            info_hash: 任务标识（可能为 None，此时必然走插入分支）
            name: 任务显示名
            library_name: 所属媒体库名称
        """
        async with get_session() as session:
            existing = None
            if info_hash:
                result = await session.execute(
                    select(OfflineTask).where(OfflineTask.info_hash == info_hash)
                )
                existing = result.scalar_one_or_none()

            if existing:
                # 已存在则更新归属与显示信息
                existing.library_name = library_name
                existing.name = name
                existing.status = "added"
                logger.info(f"离线任务已更新: info_hash={info_hash}")
            else:
                session.add(
                    OfflineTask(
                        info_hash=info_hash,
                        name=name,
                        library_name=library_name,
                        status="added",
                    )
                )
                logger.info(f"离线任务已保存到数据库: info_hash={info_hash}")

            await session.commit()

    async def _rollback_cloud_task(self, info_hash: Optional[str]) -> None:
        """
        补偿回滚：本地保存失败时删除已创建的云端任务（尽力而为）。

        Args:
            info_hash: 要回滚的任务标识；无标识时跳过
        """
        if not info_hash:
            return
        try:
            await self._cloud.delete_offline_task(info_hash)
            logger.info(f"已回滚云端离线任务: {info_hash}")
        except Exception as cleanup_error:
            logger.error(f"回滚 115 离线任务失败: {cleanup_error}")
