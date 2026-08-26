"""
@description 离线任务管理接口
@responsibility 处理离线任务的添加、查询、删除操作
"""

from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Depends, Query
from loguru import logger
from sqlalchemy import select

from app.schemas.api import (
    AddTaskRequest,
    AddTaskResponse,
    TaskItem,
    TaskListResponse,
    TaskDetailResponse,
    DeleteTaskResponse,
    success_response,
)
from app.models.offline_task import OfflineTask
from app.core.database import get_session
from app.core.dependencies import get_cloud_service, get_config
from app.utils.helpers import parse_info_hash_from_magnet, find_library_by_name

if TYPE_CHECKING:
    from app.services.cloud.base import CloudService
    from app.core.config import Config

router = APIRouter()


@router.post("/tasks")
async def add_task(
    request: AddTaskRequest,
    cloud_service: "CloudService" = Depends(get_cloud_service),
    config: "Config" = Depends(get_config),
):
    """
    添加离线下载任务。

    先解析 magnet 中的 info_hash，再获取媒体库下载目录 ID，
    调用 115 接口添加任务并将记录持久化到数据库。

    Args:
        request: 包含 magnet、library_name、可选 name 的请求体
        p115_client: 115 客户端实例（DI 注入）
        config: 全局配置（DI 注入）

    Returns:
        成功响应，包含最终任务 ID（info_hash）

    Raises:
        HTTPException 404: 媒体库不存在
        HTTPException 500: 获取目录 ID 失败或 115 接口返回错误
    """
    library = find_library_by_name(config.media.libraries, request.library_name)
    if library is None:
        raise HTTPException(
            status_code=404, detail=f"媒体库 '{request.library_name}' 不存在"
        )

    # 先从 magnet 解析 info_hash 作为备用（API 可能不返回）
    parsed_info_hash = parse_info_hash_from_magnet(request.magnet)
    logger.debug(f"从 magnet 解析 info_hash: {parsed_info_hash}")

    try:
        path_id = await cloud_service.get_path_id(
            library.download_path, library_name=library.name
        )
    except Exception as e:
        logger.error(f"[add_task] get_path_id throw exception: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取下载目录 ID 报错: {str(e)}")

    logger.debug(f"[add_task] 获取下载目录 ID: {library.download_path} -> {path_id}")
    if path_id is None:
        logger.error(f"[add_task] 获取下载目录 ID 失败: {library.download_path}")
        raise HTTPException(
            status_code=500, detail=f"获取下载目录 ID 失败: {library.download_path}"
        )

    # 适配器翻译为 (成功, 错误信息, info_hash)；115 可能不返回 info_hash
    add_ok, add_error, api_info_hash = await cloud_service.add_offline_task(
        request.magnet, path_id
    )
    if not add_ok:
        logger.error(f"[add_task] 添加离线任务失败: {add_error}")
        raise HTTPException(status_code=500, detail=f"添加离线任务失败: {add_error}")

    # 优先级：API 返回的 info_hash > magnet 解析的 > None
    final_info_hash = api_info_hash or parsed_info_hash

    logger.debug(f"API info_hash: {api_info_hash}")
    logger.debug(f"最终 info_hash: {final_info_hash}")

    # 保存到数据库（info_hash 可能为 None）
    try:
        async with get_session() as session:
            # 查询是否存在相同 info_hash 的任务
            db_result = await session.execute(
                select(OfflineTask).where(OfflineTask.info_hash == final_info_hash)
            )
            existing_task = db_result.scalar_one_or_none()

            if existing_task:
                # 存在则更新字段
                existing_task.library_name = library.name
                existing_task.name = (
                    request.name if request.name else request.magnet[:50]
                )
                existing_task.status = "added"
                logger.info(f"离线任务已更新: info_hash={final_info_hash}")
            else:
                # 不存在则创建新记录
                offline_task = OfflineTask(
                    info_hash=final_info_hash,
                    name=request.name if request.name else request.magnet[:50],
                    library_name=library.name,
                    status="added",
                )
                session.add(offline_task)
                logger.info(f"离线任务已保存到数据库: info_hash={final_info_hash}")

            await session.commit()
    except Exception as e:
        logger.error(f"保存离线任务失败: {e}")
        if final_info_hash:
            try:
                await cloud_service.delete_offline_task(final_info_hash)
            except Exception as cleanup_error:
                logger.error(f"回滚 115 离线任务失败: {cleanup_error}")
        raise HTTPException(
            status_code=500,
            detail="任务已提交至 115，但本地记录保存失败；已尝试回滚，请检查日志后重试",
        ) from e

    # 返回最终的 info_hash（None 时返回空字符串避免 API 响应为 null）
    return success_response(
        data=AddTaskResponse(task_id=final_info_hash or "", message="离线任务添加成功"),
        message="离线任务添加成功",
    )


@router.get("/tasks")
async def get_tasks(
    cloud_service: "CloudService" = Depends(get_cloud_service),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
    status: int | None = Query(None),
):
    """
    获取115离线任务列表。

    Returns:
        成功响应，包含任务总数和任务列表

    Raises:
        HTTPException 500: 115 接口调用失败
    """
    tasks = await cloud_service.get_offline_tasks()
    if status is not None:
        tasks = [task for task in tasks if task.status == status]
    total = len(tasks)
    tasks = tasks[(page - 1) * page_size : page * page_size]
    task_items = [
        TaskItem(
            task_id=task.info_hash,
            name=task.name,
            status=task.status,
            progress=task.progress,
            add_time=task.add_time,
        )
        for task in tasks
    ]

    return success_response(
        data=TaskListResponse(total=total, tasks=task_items),
        message="获取任务列表成功",
    )


@router.get("/tasks/{task_id}")
async def get_task_detail(
    task_id: str,
    cloud_service: "CloudService" = Depends(get_cloud_service),
):
    """
    获取指定任务的详细信息。

    Args:
        task_id: 任务 ID（info_hash）
        p115_client: 115 客户端实例（DI 注入）

    Returns:
        成功响应，包含任务详情

    Raises:
        HTTPException 404: 任务不存在
    """
    task = await cloud_service.get_offline_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 '{task_id}' 不存在")

    return success_response(
        data=TaskDetailResponse(
            task_id=task.info_hash,
            name=task.name,
            status=task.status,
            progress=task.progress,
            add_time=task.add_time,
            file_id=task.file_id or None,
            path=task.path or None,
        ),
        message="获取任务详情成功",
    )


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    cloud_service: "CloudService" = Depends(get_cloud_service),
):
    """
    删除指定离线任务。

    Args:
        task_id: 要删除的任务 ID（info_hash）
        p115_client: 115 客户端实例（DI 注入）

    Returns:
        成功响应，包含操作消息

    Raises:
        HTTPException 500: 115 接口调用失败
    """
    if not await cloud_service.delete_offline_task(task_id):
        raise HTTPException(status_code=500, detail="删除任务失败")

    return success_response(
        data=DeleteTaskResponse(message="任务删除成功"), message="任务删除成功"
    )
