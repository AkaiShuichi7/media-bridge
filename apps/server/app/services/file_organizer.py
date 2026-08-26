"""
@description 文件整理服务核心逻辑
@responsibility 处理文件整理、重命名、移动及清理操作；
               配置直接消费 LibraryConfig/MediaConfig/XXConfig 类型对象，不再手工拍平成裸 dict
"""

import asyncio
from typing import TYPE_CHECKING, Optional

from loguru import logger

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
class FileOrganizer:
    """文件整理服务"""

    def __init__(self, p115_client: "CloudService"):
        self._client = p115_client
        self._lock = asyncio.Lock()

    async def organize_task(
        self,
        task_info: dict,
        library_config: "LibraryConfig",
        media_config: "MediaConfig",
        xx_config: Optional["XXConfig"] = None,
    ) -> dict:
        """
        整理单个任务的文件

        Args:
            task_info: 任务信息，包含 task_id, info_hash, path_id, name
            library_config: 媒体库配置（LibraryConfig 类型对象）
            media_config: 媒体配置（MediaConfig 类型对象，提供视频格式与默认大小阈值）
            xx_config: 成人片库配置（可选，XXConfig 类型对象）

        Returns:
            整理结果统计 {success_count, failed_count, skipped_count, errors}
        """
        # 初始化结果变量
        result = {
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "errors": [],
        }

        try:
            async with self._lock:
                task_id = task_info["task_id"]
                task_name = task_info.get("name", "")
                download_path_id = task_info.get("download_path_id", "")

                # 获取任务目录的内容（CloudService 返回标准 CloudFile 列表）
                task_path_id = task_info["path_id"]
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
                    return result

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
                    return result

                library_type = library_config.type

                if library_type == "system":
                    organize_result = await self.organize_files_system(
                        video_files,
                        library_config.target_path,
                        task_id,
                        library_config,
                    )
                elif library_type.startswith("xx-"):
                    producer = extract_producer(library_type)
                    organize_result = await self.organize_files_xx(
                        video_files,
                        library_config.target_path,
                        producer,
                        xx_config,
                        task_id,
                        library_config,
                    )
                else:
                    logger.warning(f"未知的媒体库类型: {library_type}")
                    return result

                result["success_count"] = organize_result["success_count"]
                result["failed_count"] = organize_result["failed_count"]
                result["skipped_count"] = organize_result["skipped_count"]
                result["errors"] = organize_result["errors"]

                return result
        except KeyError as e:
            logger.exception(
                f"整理任务缺少必要字段: {e}; task_id={task_info.get('task_id')}, library={library_config.name}"
            )
            raise
        except Exception as e:
            logger.exception(
                f"整理任务失败: {e}; task_id={task_info.get('task_id')}, library={library_config.name}"
            )
            raise

    async def organize_files_system(
        self,
        files: list,
        target_dir: str,
        task_id: str,
        library_config: "LibraryConfig",
    ) -> dict:
        """
        system 类型整理 - 直接移动文件到目标目录

        Args:
            files: 待整理文件列表
            target_dir: 目标目录路径
            task_id: 任务 ID
            library_config: 媒体库配置（LibraryConfig 类型对象）

        Returns:
            整理结果统计
        """
        result = {
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "errors": [],
        }

        target_id = await self._client.get_path_id(target_dir)

        if not target_id:
            logger.error(f"无法获取目标目录 ID: {target_dir}")
            result["failed_count"] = len(files)
            return result

        for file in files:
            file_id = file.file_id
            file_name = file.name
            file_size = file.size

            logger.debug(f"准备移动文件: file_id={file_id}, file_name={file_name}")
            try:
                # CloudService 契约保证 move_file 返回 bool
                move_ok = await self._client.move_file(file_id, target_id)

                if move_ok:
                    result["success_count"] += 1
                    logger.info(f"文件 {file_name} 移动成功")

                    await self.save_organize_record(
                        {
                            "task_id": task_id,
                            "source_path": f"/{file_id}",
                            "target_path": f"{target_dir}/{file_name}",
                            "file_name": file_name,
                            "file_size": file_size,
                            "library_name": library_config.name,
                            "status": "success",
                            "error_message": None,
                        }
                    )
                else:
                    result["skipped_count"] += 1
                    logger.warning(f"文件 {file_name} 跳过: 移动未成功（可能已存在）")

                    await self.save_organize_record(
                        {
                            "task_id": task_id,
                            "source_path": f"/{file_id}",
                            "target_path": f"{target_dir}/{file_name}",
                            "file_name": file_name,
                            "file_size": file_size,
                            "library_name": library_config.name,
                            "status": "skipped",
                            "error_message": "移动未成功（可能已存在）",
                        }
                    )

            except Exception as e:
                result["failed_count"] += 1
                result["errors"].append(str(e))
                logger.error(f"文件 {file_name} 整理失败: {e}")

                await self.save_organize_record(
                    {
                        "task_id": task_id,
                        "source_path": f"/{file_id}",
                        "target_path": f"{target_dir}/{file_name}",
                        "file_name": file_name,
                        "file_size": file_size,
                        "library_name": library_config.name,
                        "status": "failed",
                        "error_message": str(e),
                    }
                )

        return result

    async def organize_files_xx(
        self,
        files: list,
        target_dir: str,
        producer: str,
        xx_config: Optional["XXConfig"],
        task_id: str,
        library_config: "LibraryConfig",
    ) -> dict:
        """
        xx-片商类型整理 - 处理番号提取、重命名和移动

        Args:
            files: 待整理文件列表
            target_dir: 目标目录路径
            producer: 片商名称
            xx_config: 成人片库配置（XXConfig 类型对象，提供 remove_keywords）
            task_id: 任务 ID
            library_config: 媒体库配置（LibraryConfig 类型对象）

        Returns:
            整理结果统计
        """
        result = {
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "errors": [],
        }

        file_count = len(files)
        # xx_config 缺省时视为空关键词列表（与旧 dict 语义保持一致）
        keywords = xx_config.remove_keywords if xx_config else []

        for file in files:
            file_id = file.file_id
            original_name = file.name
            file_size = file.size

            logger.debug(f"准备移动文件: file_id={file_id}, file_name={original_name}")
            try:
                processed_name = remove_keywords(original_name, keywords)
                processed_name = normalize_filename(processed_name)

                fanhao = extract_fanhao(processed_name)
                if not fanhao:
                    result["skipped_count"] += 1
                    logger.warning(f"无法从 {original_name} 提取番号，跳过")
                    continue

                processed_name = normalize_cd_suffix(processed_name, file_count)
                final_target_path = generate_target_path(
                    processed_name, target_dir, producer
                )
                target_dir_path = "/".join(final_target_path.rsplit("/", 1)[:-1])
                target_id = await self._client.get_path_id(target_dir_path)

                if not target_id:
                    result["failed_count"] += 1
                    result["errors"].append(f"无法创建目标目录: {target_dir_path}")
                    continue

                # CloudService 契约保证 rename_file 返回 bool；失败时仅降级用原文件名
                rename_ok = await self._client.rename_file(file_id, processed_name)
                if not rename_ok:
                    logger.warning(f"重命名失败，使用原文件名: {original_name}")

                # CloudService 契约保证 move_file 返回 bool
                move_ok = await self._client.move_file(file_id, target_id)

                if move_ok:
                    result["success_count"] += 1
                    logger.info(f"文件 {original_name} -> {processed_name} 整理成功")

                    await self.save_organize_record(
                        {
                            "task_id": task_id,
                            "source_path": f"/{file_id}/{original_name}",
                            "target_path": final_target_path,
                            "file_name": processed_name,
                            "file_size": file_size,
                            "library_name": library_config.name,
                            "status": "success",
                            "error_message": None,
                        }
                    )
                else:
                    result["skipped_count"] += 1
                    logger.warning(
                        f"文件 {processed_name} 跳过: 移动未成功（可能已存在）"
                    )

            except Exception as e:
                result["failed_count"] += 1
                result["errors"].append(str(e))
                logger.error(f"文件 {original_name} 整理失败: {e}")

        return result

    async def save_organize_record(self, record: dict) -> None:
        """
        保存整理记录到数据库

        Args:
            record: 整理记录字典
        """
        try:
            async with get_session() as session:
                organize_record = OrganizeRecord(
                    task_id=record["task_id"],
                    source_path=record["source_path"],
                    target_path=record["target_path"],
                    file_name=record["file_name"],
                    file_size=record["file_size"],
                    library_name=record["library_name"],
                    status=record["status"],
                    error_message=record.get("error_message"),
                )
                session.add(organize_record)
                await session.commit()
                logger.debug(f"整理记录已保存: {record['file_name']}")
        except Exception as e:
            logger.error(f"保存整理记录失败: {e}")

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
