"""
@description 文件整理服务核心逻辑
@responsibility 处理文件整理、重命名、移动及清理操作；
               接口为 OfflineTaskRef → OrganizeResult 类型对象（不再使用裸 dict 通信）；
               逐文件的「移动 → 计数 → 记录」公共循环收拢在 _move_and_record 内部 seam，
               organize_files_system / organize_files_xx 只保留各自的策略差异
"""

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from loguru import logger

from sqlalchemy import select, func

from app.core.database import get_session
from app.models.organize_record import OrganizeRecord
from app.services.file_filter import filter_files
from app.services.fanhao_parser import (
    remove_keywords,
    normalize_filename,
    extract_fanhao,
    normalize_cd_suffix,
    generate_target_path,
    extract_producer,
)


if TYPE_CHECKING:
    from app.core.config import LibraryConfig, MediaConfig, XXConfig
    from app.services.cloud.base import CloudService


@dataclass(frozen=True)
class OfflineTaskRef:
    """待整理离线任务的任务引用

    取代旧版 5 键裸 dict task_info：info_hash 即任务唯一标识（旧 dict 的
    task_id/info_hash 双字段冗余已删除），download_path_id 为父目录补偿查找用。
    """

    info_hash: str
    name: str
    path_id: str
    download_path_id: str = ""


@dataclass
class OrganizeResult:
    """单次整理任务的结果统计

    errors 汇总失败原因（供领域服务写入 error_message）；
    message 在 0 成功 0 失败的提前返回路径上携带可读原因，
    供监控层区分「全跳过」结局（取代旧版 message 字符串约定）。
    """

    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    errors: list = field(default_factory=list)
    message: Optional[str] = None


class FileOrganizer:
    """文件整理服务"""

    def __init__(self, p115_client: "CloudService"):
        self._client = p115_client
        self._lock = asyncio.Lock()

    async def organize_task(
        self,
        task_ref: OfflineTaskRef,
        library_config: "LibraryConfig",
        media_config: "MediaConfig",
        xx_config: Optional["XXConfig"] = None,
    ) -> OrganizeResult:
        """
        整理单个任务的文件

        Args:
            task_ref: 待整理任务引用（OfflineTaskRef 类型对象）
            library_config: 媒体库配置（LibraryConfig 类型对象）
            media_config: 媒体配置（MediaConfig 类型对象，提供视频格式与默认大小阈值）
            xx_config: 成人片库配置（可选，XXConfig 类型对象）

        Returns:
            OrganizeResult 整理结果统计
        """
        result = OrganizeResult()

        try:
            async with self._lock:
                # 内部 seam：目录定位（含父目录补偿）与视频过滤收拢单点
                collected = await self._collect_video_files(
                    task_ref, library_config, media_config
                )
                if isinstance(collected, str):
                    # 收集阶段提前返回：携带可读原因（无文件 / 过滤后为空）
                    result.message = collected
                    return result

                library_type = library_config.type

                if library_type == "system":
                    await self.organize_files_system(
                        collected,
                        library_config.target_path,
                        task_ref.info_hash,
                        library_config,
                        result,
                    )
                elif library_type.startswith("xx-"):
                    producer = extract_producer(library_type)
                    await self.organize_files_xx(
                        collected,
                        library_config.target_path,
                        producer,
                        xx_config,
                        task_ref.info_hash,
                        library_config,
                        result,
                    )
                else:
                    logger.warning(f"未知的媒体库类型: {library_type}")
                    result.message = f"未知的媒体库类型: {library_type}，无法整理"
                    return result

                return result
        except Exception as e:
            logger.exception(
                f"整理任务失败: {e}; task_id={task_ref.info_hash}, library={library_config.name}"
            )
            raise

    async def _collect_video_files(
        self,
        task_ref: OfflineTaskRef,
        library_config: "LibraryConfig",
        media_config: "MediaConfig",
    ):
        """目录定位与视频过滤（internal seam）

        流程：任务目录列表 → 空目录时按任务名在父目录补偿查找 →
        filter_files 单点过滤（目录跳过、格式与大小判定）。

        Returns:
            过滤后的视频文件列表；收集失败时返回可读原因字符串
            （写入 OrganizeResult.message，供监控层区分「全跳过」结局）。
        """
        task_id = task_ref.info_hash
        task_name = task_ref.name
        download_path_id = task_ref.download_path_id

        # 获取任务目录的内容（CloudService 返回标准 CloudFile 列表）
        task_path_id = task_ref.path_id
        files = await self._client.list_files(task_path_id)
        logger.debug(f"任务 {task_id} 目录下返回 {len(files)} 个条目")

        # 如果任务目录里没有文件，尝试在父目录中查找任务名称对应的目录
        if not files and task_name and download_path_id:
            logger.debug(f"任务 {task_id} 目录为空，尝试在父目录查找 {task_name}")
            parent_files = await self._client.list_files(download_path_id)

            for item in parent_files:
                # 查找与任务同名的目录
                if item.is_directory and item.name == task_name:
                    task_path_id = item.file_id
                    logger.debug(f"任务 {task_id} 找到补偿目录 ID: {task_path_id}")

                    # 重新查询任务目录内容
                    files = await self._client.list_files(task_path_id)
                    break

        if not files:
            logger.warning(f"任务 {task_id} 无文件可整理")
            return "任务目录中没有文件可整理"

        # 库级阈值 <=0 时回落到媒体级默认值
        effective_min_size = (
            library_config.min_transfer_size
            if library_config.min_transfer_size > 0
            else media_config.min_transfer_size
        )
        filter_config = {
            "video_formats": media_config.video_formats,
            "min_transfer_size": effective_min_size,
        }

        # 统一走 filter_files 单点过滤（含目录跳过、格式与大小判定）
        video_files = filter_files(files, filter_config)
        logger.debug(
            f"任务 {task_id} 过滤结果: 保留 {len(video_files)} / 共 {len(files)} 个条目"
        )

        if not video_files:
            logger.warning(
                f"任务 {task_id} 无符合条件的视频文件 (共查询 {len(files)} 个文件)"
            )
            return (
                f"任务目录共 {len(files)} 个文件，无符合条件的视频文件（格式或大小过滤后为空）"
            )

        return video_files

    async def _move_and_record(
        self,
        *,
        file,
        target_id: str,
        target_path: str,
        record_name: str,
        source_display: str,
        task_id: str,
        library_name: str,
        result: OrganizeResult,
        record_non_success: bool = True,
    ) -> None:
        """逐文件公共循环：移动 → 计数 → 写整理记录（internal seam）

        两个 organize_files_* 策略共享同一套「成功 / 跳过 / 失败」三态处理；
        record_non_success 控制非成功结局是否落库（旧版行为：system 三态全记录，
        xx 仅记录成功），保持既有语义不变。
        """
        file_id = file.file_id
        file_size = file.size

        try:
            # CloudService 契约保证 move_file 返回 bool
            move_ok = await self._client.move_file(file_id, target_id)

            if move_ok:
                result.success_count += 1
                logger.info(f"文件 {record_name} 移动成功")
                # 成功结局两种策略都落库
                await self.save_record(
                    task_id=task_id,
                    source_path=source_display,
                    target_path=target_path,
                    file_name=record_name,
                    file_size=file_size,
                    library_name=library_name,
                    status="success",
                )
            else:
                result.skipped_count += 1
                logger.warning(f"文件 {record_name} 跳过: 移动未成功（可能已存在）")
                if record_non_success:
                    await self.save_record(
                        task_id=task_id,
                        source_path=source_display,
                        target_path=target_path,
                        file_name=record_name,
                        file_size=file_size,
                        library_name=library_name,
                        status="skipped",
                        error_message="移动未成功（可能已存在）",
                    )

        except Exception as e:
            result.failed_count += 1
            result.errors.append(str(e))
            logger.error(f"文件 {record_name} 整理失败: {e}")
            if record_non_success:
                await self.save_record(
                    task_id=task_id,
                    source_path=source_display,
                    target_path=target_path,
                    file_name=record_name,
                    file_size=file_size,
                    library_name=library_name,
                    status="failed",
                    error_message=str(e),
                )

    async def organize_files_system(
        self,
        files: list,
        target_dir: str,
        task_id: str,
        library_config: "LibraryConfig",
        result: OrganizeResult,
    ) -> None:
        """system 类型整理策略 - 直接移动文件到目标目录（计数与记录累加进 result）"""
        target_id = await self._client.get_path_id(target_dir)

        if not target_id:
            logger.error(f"无法获取目标目录 ID: {target_dir}")
            result.failed_count += len(files)
            return

        for file in files:
            # system 策略：原样移动，目标路径 = 目标目录 / 原文件名，三态全落库
            await self._move_and_record(
                file=file,
                target_id=target_id,
                target_path=f"{target_dir}/{file.name}",
                record_name=file.name,
                source_display=f"/{file.file_id}",
                task_id=task_id,
                library_name=library_config.name,
                result=result,
                record_non_success=True,
            )

    async def organize_files_xx(
        self,
        files: list,
        target_dir: str,
        producer: str,
        xx_config: Optional["XXConfig"],
        task_id: str,
        library_config: "LibraryConfig",
        result: OrganizeResult,
    ) -> None:
        """xx-片商类型整理策略 - 番号提取、规范重命名后按 片商/番号 路径移动"""
        file_count = len(files)
        # xx_config 缺省时视为空关键词列表（与旧 dict 语义保持一致）
        keywords = xx_config.remove_keywords if xx_config else []

        for file in files:
            file_id = file.file_id
            original_name = file.name

            logger.debug(f"准备移动文件: file_id={file_id}, file_name={original_name}")
            try:
                # 关键词清洗 → 文件名规范化 → 番号提取
                processed_name = remove_keywords(original_name, keywords)
                processed_name = normalize_filename(processed_name)

                fanhao = extract_fanhao(processed_name)
                if not fanhao:
                    result.skipped_count += 1
                    logger.warning(f"无法从 {original_name} 提取番号，跳过")
                    continue

                # 集数后缀规范化并生成 片商/番号 目标路径
                processed_name = normalize_cd_suffix(processed_name, file_count)
                final_target_path = generate_target_path(
                    processed_name, target_dir, producer
                )
                target_dir_path = "/".join(final_target_path.rsplit("/", 1)[:-1])
                target_id = await self._client.get_path_id(target_dir_path)

                if not target_id:
                    result.failed_count += 1
                    result.errors.append(f"无法创建目标目录: {target_dir_path}")
                    continue

                # CloudService 契约保证 rename_file 返回 bool；失败时仅降级用原文件名
                rename_ok = await self._client.rename_file(file_id, processed_name)
                if not rename_ok:
                    logger.warning(f"重命名失败，使用原文件名: {original_name}")

                # xx 策略：源路径展示含原文件名，仅成功结局落库（record_non_success=False）
                await self._move_and_record(
                    file=file,
                    target_id=target_id,
                    target_path=final_target_path,
                    record_name=processed_name,
                    source_display=f"/{file_id}/{original_name}",
                    task_id=task_id,
                    library_name=library_config.name,
                    result=result,
                    record_non_success=False,
                )

            except Exception as e:
                result.failed_count += 1
                result.errors.append(str(e))
                logger.error(f"文件 {original_name} 整理失败: {e}")

    async def save_record(
        self,
        *,
        task_id: str,
        source_path: str,
        target_path: str,
        file_name: str,
        file_size: int,
        library_name: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """保存单条整理记录到数据库（record dict 键名唯一拥有者）"""
        try:
            async with get_session() as session:
                organize_record = OrganizeRecord(
                    task_id=task_id,
                    source_path=source_path,
                    target_path=target_path,
                    file_name=file_name,
                    file_size=file_size,
                    library_name=library_name,
                    status=status,
                    error_message=error_message,
                )
                session.add(organize_record)
                await session.commit()
                logger.debug(f"整理记录已保存: {file_name}")
        except Exception as e:
            logger.error(f"保存整理记录失败: {e}")

    async def list_organize_records(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> tuple[int, list[OrganizeRecord]]:
        """分页查询整理记录（按创建时间倒序，可选按状态筛选）

        查询侧与写侧（save_record）同 seam 收敛在本模块，路由层只做协议转换。

        Returns:
            (总数, 当前页 OrganizeRecord 列表)
        """
        async with get_session() as session:
            count_stmt = select(func.count()).select_from(OrganizeRecord)
            if status:
                count_stmt = count_stmt.where(OrganizeRecord.status == status)
            total = (await session.execute(count_stmt)).scalar()

            stmt = select(OrganizeRecord).order_by(OrganizeRecord.created_at.desc())
            if status:
                stmt = stmt.where(OrganizeRecord.status == status)
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)

            records = (await session.execute(stmt)).scalars().all()
            return total, list(records)

    async def cleanup_source(
        self, task_id: str, info_hash: str, source_files: list
    ) -> None:
        """
        清理源文件和离线任务

        Args:
            task_id: 任务 ID
            info_hash: 离线任务 hash
            source_files: 源文件列表
        """
        for file in source_files:
            file_id = file.file_id
            file_name = file.name
            logger.debug(f"准备删除源文件: file_id={file_id}, file_name={file_name}")
            try:
                await self._client.delete_file(file_id)
                logger.info(f"源文件 {file_name} 已删除")
            except Exception as e:
                logger.error(f"删除源文件 {file_name} 失败: {e}")

        try:
            await self._client.delete_offline_task(info_hash)
            logger.info(f"离线任务 {task_id} 已删除")
        except Exception as e:
            logger.error(f"删除离线任务 {task_id} 失败: {e}")
