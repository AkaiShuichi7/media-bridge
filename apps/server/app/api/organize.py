"""
@description 整理记录查询接口
@responsibility 处理文件整理记录的查询操作；
               分页/筛选 SQL 下沉在 FileOrganizer.list_organize_records，
               本路由只做协议转换
"""

from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, Query

from app.schemas.api import (
    ApiResponse,
    OrganizeRecordItem,
    OrganizeRecordsResponse,
    success_response,
)
from app.core.dependencies import get_file_organizer

if TYPE_CHECKING:
    from app.services.file_organizer import FileOrganizer

router = APIRouter()


@router.get("/organize/records", response_model=ApiResponse[OrganizeRecordsResponse])
async def get_organize_records(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="筛选状态"),
    organizer: "FileOrganizer" = Depends(get_file_organizer),
):
    """
    分页查询文件整理记录。

    支持按状态筛选，按创建时间倒序排列。

    Args:
        page: 页码（从 1 开始）
        page_size: 每页数量（1-100）
        status: 可选筛选状态（如 success/failed）
        organizer: 文件整理服务（DI 注入，查询 SQL 在服务内）

    Returns:
        成功响应，包含总数和整理记录列表
    """
    total, records = await organizer.list_organize_records(
        page=page, page_size=page_size, status=status
    )

    record_items = [
        OrganizeRecordItem(
            id=record.id,
            file_name=record.file_name or "",
            original_name=(record.source_path or "").rsplit("/", 1)[-1] or record.file_name or "",
            organized_name=record.file_name or "",
            source_path=record.source_path or "",
            target_path=record.target_path or "",
            status=record.status or "",
            error_message=record.error_message,
            created_at=record.created_at,
        )
        for record in records
    ]

    return success_response(
        data=OrganizeRecordsResponse(total=total, records=record_items),
        message="获取整理记录成功",
    )
