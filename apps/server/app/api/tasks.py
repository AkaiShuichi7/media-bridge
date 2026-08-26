"""
@description 离线任务管理接口
@responsibility 处理离线任务的添加、查询、删除操作
"""

from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Depends, Query
from app.schemas.api import (
    AddTaskRequest,
    AddTaskResponse,
    TaskItem,
    TaskListResponse,
    TaskDetailResponse,
    DeleteTaskResponse,
    success_response,
)
from app.core.dependencies import get_cloud_service, get_config
from app.services.offline_task_service import AddTaskError, OfflineTaskService
from app.utils.helpers import parse_info_hash_from_magnet

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

    业务流程（库校验 → 目录解析 → 云端建任务 → 本地持久化 → 失败补偿回滚）
    全部下沉到 OfflineTaskService；本函数只做协议转换。

    Args:
        request: 包含 magnet、library_name、可选 name 的请求体
        cloud_service: 云盘服务（DI 注入）
        config: 全局配置（DI 注入）

    Returns:
        成功响应，包含最终任务 ID（info_hash）

    Raises:
        HTTPException 404: 媒体库不存在
        HTTPException 500: 目录解析失败 / 云端添加失败 / 本地保存失败
    """
    # 先从 magnet 解析 info_hash 作为备用（云端可能不返回）
    parsed_info_hash = parse_info_hash_from_magnet(request.magnet)

    service = OfflineTaskService(cloud_service, config)
    try:
        task_id = await service.add_task(
            magnet=request.magnet,
            library_name=request.library_name,
            name=request.name,
            parsed_info_hash=parsed_info_hash,
        )
    except AddTaskError as e:
        # 库不存在映射 404，其余业务失败映射 500
        status = 404 if "不存在" in e.message else 500
        raise HTTPException(status_code=status, detail=e.message) from e

    return success_response(
        data=AddTaskResponse(task_id=task_id, message="离线任务添加成功"),
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
