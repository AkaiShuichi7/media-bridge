"""
@description 离线任务领域服务
@responsibility 承载「添加离线任务」与「任务生命周期状态迁移」的完整业务流程：
                添加：库解析 → 目录解析 → 云端建任务 → 本地持久化 → 失败补偿回滚；
                生命周期：轮询集合查询、完成任务的整理编排与四态迁移、失败任务记录；
                路由层与监控器只做协议转换/轮询比对，事务性规则集中在 service 内可测
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from loguru import logger
from sqlalchemy import select

from app.core.database import get_session
from app.models.offline_task import OfflineTask
from app.schemas.cloud_types import CloudTask
from app.services.file_organizer import OfflineTaskRef
from app.utils.helpers import find_library_by_name

if TYPE_CHECKING:
    from app.core.config import Config, LibraryConfig
    from app.services.cloud.base import CloudService


class AddTaskError(Exception):
    """添加离线任务失败的领域异常，message 面向用户可展示"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class OfflineTaskService:
    """离线任务领域服务：添加（含补偿回滚）与生命周期状态迁移"""

    def __init__(self, cloud_service: "CloudService", config: "Config", file_organizer) -> None:
        self._cloud = cloud_service
        self._config = config
        self._organizer = file_organizer

    def _find_library(self, library_name: str) -> Optional["LibraryConfig"]:
        """按名称查找媒体库配置，不存在返回 None"""
        for lib in self._config.media.libraries:
            if lib.name == library_name:
                return lib
        return None

    # ------------------------------------------------------------------
    # 添加流程
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # 生命周期（监控侧）
    # ------------------------------------------------------------------

    async def list_active_hashes(self) -> set[str]:
        """查询监控轮询集合：本地状态为 added/downloading 的系统任务 info_hash。

        终态任务（completed/organize_failed/organize_skipped/failed）自动退出
        轮询集合，这也是跨轮重复处理防护的依据（取代旧的内存去重集合）。
        """
        async with get_session() as session:
            result = await session.execute(
                select(OfflineTask.info_hash).where(
                    OfflineTask.status.in_(["added", "downloading"])
                )
            )
            return {row[0] for row in result.fetchall()}

    async def handle_completed_task(self, task: CloudTask) -> bool:
        """处理云端已完成的任务 - 触发文件整理并迁移本地状态

        结局分为三类，不得混淆：
        - 成功：success_count > 0 且 failed_count == 0 → 标记 completed 并清理云端任务
        - 失败：failed_count > 0 → 标记 organize_failed，保留云端任务
        - 全跳过：success_count == 0 且 failed_count == 0（无文件/无符合条件文件/番号均无法识别）
          → 标记 organize_skipped 并记录可读原因，保留云端任务

        重试与可观察性语义：organize_failed / organize_skipped 均不会进入下一轮
        added/downloading 轮询集合（确定性结局自动重试无意义），云端任务与本地
        error_message 都保留，供 UI 展示与人工排查。

        Returns:
            bool: 整理成功（已标记 completed 并清理云端任务）时为 True
        """
        info_hash = task.info_hash

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
                        library_config = find_library_by_name(
                            self._config.media.libraries, library_name
                        )
                        logger.debug(f"通过数据库找到 library: {library_name}")
            except Exception as e:
                logger.error(f"查询 library_name 失败: {e}")

        if library_config is None:
            # 路径回退: 当 DB 查询失败或无结果时，尝试通过任务路径匹配媒体库
            task_path = task.path
            for lib in self._config.media.libraries:
                if task_path.startswith(lib.download_path):
                    library_config = lib
                    logger.debug(f"通过路径回退找到 library: {lib.name}")
                    break
        if library_config is None:
            logger.error(
                f"无法确定任务 [{task.name}] 的 library 配置，跳过整理"
            )
            return False

        task_path = task.path
        download_path_id = ""
        logger.debug(f"任务 [{task.name}] 路径信息: {task_path or '(空)'}")
        if task_path:
            parent_path = "/".join(task_path.rstrip("/").split("/")[:-1])
            if parent_path:
                download_path_id = await self._cloud.get_path_id(parent_path)
                logger.debug(
                    f"任务 [{task.name}] 下载路径 ID: {parent_path} -> {download_path_id}"
                )

        # 整理入参收敛为 OfflineTaskRef 类型对象（info_hash 即任务唯一标识）
        task_ref = OfflineTaskRef(
            info_hash=task.info_hash,
            name=task.name,
            path_id=task.file_id,
            download_path_id=download_path_id or "",
        )

        # xx 配置可选：未配置时传 None，organizer 内部按空关键词处理
        xx_config = self._config.media.xx if self._config.media.xx else None

        try:
            # 配置对象直接透传，不再手工拍平成裸 dict
            result = await self._organizer.organize_task(
                task_ref, library_config, self._config.media, xx_config
            )
            logger.info(
                f"任务整理完成: 成功 {result.success_count}, "
                f"失败 {result.failed_count}, 跳过 {result.skipped_count}"
            )

            if result.failed_count:
                await self.update_lifecycle(
                    info_hash, "organize_failed", "; ".join(result.errors)
                )
                return False

            if result.success_count == 0:
                # 0 成功 0 失败：全部跳过或无可整理文件，不得虚报成功，也不得清理云端任务
                reason = result.message or (
                    f"所有 {result.skipped_count} 个文件均被跳过"
                    "（番号无法识别或目标文件已存在），没有任何文件被整理"
                )
                logger.warning(
                    f"任务 [{task_ref.name}] 整理后无成功文件，"
                    f"保留云端任务等待人工处理: {reason}"
                )
                await self.update_lifecycle(info_hash, "organize_skipped", reason)
                return False

            await self.update_lifecycle(info_hash, "completed")
            try:
                await self._cloud.delete_offline_task(info_hash)
            except Exception as e:
                logger.warning(f"任务 [{task_ref.name}] 清理失败: {e}")
            return True

        except Exception as e:
            logger.error(f"整理任务时发生错误: {e}")
            await self.update_lifecycle(info_hash, "organize_failed", str(e))
            return False

    async def load_error_messages(self, info_hashes: list[str]) -> dict[str, str]:
        """从本地数据库加载任务的整理失败原因，按 info_hash 建立映射。

        数据库不可用时降级为空映射，保证任务列表接口仍可用。

        Args:
            info_hashes: 当前页任务的 info_hash 列表

        Returns:
            {info_hash: 失败原因} 字典，仅包含有原因的记录
        """
        if not info_hashes:
            return {}
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(OfflineTask.info_hash, OfflineTask.error_message).where(
                        OfflineTask.info_hash.in_(info_hashes)
                    )
                )
                return {row[0]: row[1] for row in result.fetchall() if row[1]}
        except Exception as e:
            logger.warning(f"查询任务本地失败原因失败，列表将不含原因: {e}")
            return {}

    async def load_local_status(self, info_hashes: list[str]) -> dict[str, str]:
        """查询本地任务生命周期状态（completed/organize_failed/organize_skipped/failed）

        供任务列表接口把「云端已完成但本地整理失败」的任务映射为失败口径。

        Returns:
            {info_hash: 本地状态} 字典；数据库不可用时降级为空映射
        """
        if not info_hashes:
            return {}
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(OfflineTask.info_hash, OfflineTask.status).where(
                        OfflineTask.info_hash.in_(info_hashes)
                    )
                )
                return {row[0]: row[1] for row in result.fetchall() if row[1]}
        except Exception as e:
            logger.warning(f"查询任务本地状态失败，列表将按云端口径展示: {e}")
            return {}

    async def mark_download_failed(self, task: CloudTask) -> None:
        """处理云端报失败的任务 - 保存/更新失败记录到数据库"""
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(OfflineTask).where(OfflineTask.info_hash == task.info_hash)
                )
                offline_task = result.scalar_one_or_none()
                if offline_task is None:
                    offline_task = OfflineTask(info_hash=task.info_hash)
                    session.add(offline_task)
                offline_task.name = task.name
                offline_task.status = "failed"
                offline_task.add_time = task.add_time
                offline_task.error_message = "下载失败"
                await session.commit()
                logger.info(f"失败任务已记录到数据库: {task.name}")
        except Exception as e:
            logger.error(f"保存失败任务记录时出错: {e}")

    async def update_lifecycle(
        self, info_hash: str | None, status: str, error_message: str | None = None
    ) -> None:
        """迁移本地任务的生命周期状态。

        四态约定：completed / organize_failed / organize_skipped / failed；
        error_message 随状态一并写入（成功时置空）。
        completed 时补写 complete_time；info_hash 为空或本地记录不存在时
        静默返回（既有行为，保持兼容）。

        Args:
            info_hash: 任务标识
            status: 目标生命周期状态
            error_message: 失败/跳过原因（completed 传 None）
        """
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
