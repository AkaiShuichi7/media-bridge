"""
@description Agent 归档查询接口
@responsibility 面向外部 agent（Hermes 等）的归档状态查询；
               聚合查询 SQL 下沉在 OfflineTaskService.query_archive
               （整理记录检索委托 FileOrganizer.search_records），本路由只做协议转换
"""

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from app.schemas.api import (
    ApiResponse,
    ArchiveHit,
    ArchiveQueryResponse,
    success_response,
)
from app.core.dependencies import get_offline_task_service

if TYPE_CHECKING:
    from app.services.offline_task_service import OfflineTaskService

router = APIRouter()


@router.get(
    "/agent/archive/query",
    response_model=ApiResponse[ArchiveQueryResponse],
)
async def query_archive(
    q: str = Query(..., min_length=1, description="番号或关键词（子串匹配）"),
    limit: int = Query(20, ge=1, le=100, description="最多返回条数"),
    offline_task_service: "OfflineTaskService" = Depends(get_offline_task_service),
):
    """
    按番号/关键词查询归档状态。

    供外部 agent 在找资源前做去重与域路由判断：返回 已归档 / 在途 /
    失败 / 跳过 四类命中，汇总整理记录与本地任务两侧信号。

    Args:
        q: 查询关键词
        limit: 最多返回条数
        offline_task_service: 离线任务领域服务（DI 注入，聚合查询在服务内）

    Returns:
        成功响应，包含查询关键词与命中列表
    """
    hits = await offline_task_service.query_archive(q, limit=limit)

    return success_response(
        data=ArchiveQueryResponse(
            query=q,
            total=len(hits),
            hits=[ArchiveHit(**hit) for hit in hits],
        ),
        message="归档查询成功",
    )
