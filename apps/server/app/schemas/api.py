"""
@description API 请求/响应模型
@responsibility 定义所有 API 接口的数据结构
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AddTaskRequest(BaseModel):
    """添加离线下载任务的请求体。"""
    magnet: str = Field(..., description="磁力链接")
    library_name: str = Field(..., description="媒体库名称")
    name: Optional[str] = Field(
        None, description="任务名称（可选，默认为磁力链接前50字符）"
    )


class AddTaskResponse(BaseModel):
    """添加离线任务的响应体，包含最终任务 ID。"""
    task_id: str = Field(..., description="任务 ID（info_hash）")
    message: str = Field(..., description="操作消息")


class TaskItem(BaseModel):
    """任务列表中的单个任务信息项。"""
    task_id: str = Field(..., description="任务 ID")
    name: str = Field(..., description="任务名称")
    status: int = Field(
        ...,
        description="任务状态（对外稳定口径：2=完成，负数=失败（统一映射为 -1），1=等待中，0=下载中；由中立状态枚举映射）",
    )
    progress: int = Field(..., description="下载进度（百分比）")
    add_time: datetime = Field(..., description="添加时间")
    error_message: Optional[str] = Field(
        None, description="本地整理失败原因（合并自数据库记录，可能为空）"
    )


class TaskListResponse(BaseModel):
    """离线任务列表响应体，包含总数和任务列表。"""
    total: int = Field(..., description="任务总数")
    tasks: list[TaskItem] = Field(..., description="任务列表")


class TaskDetailResponse(BaseModel):
    """单个离线任务的详细信息响应体。"""
    task_id: str = Field(..., description="任务 ID")
    name: str = Field(..., description="任务名称")
    status: int = Field(..., description="任务状态（对外稳定口径同任务列表：2=完成，负数=失败，1=等待中，0=下载中）")
    progress: int = Field(..., description="下载进度")
    add_time: datetime = Field(..., description="添加时间")
    file_id: Optional[str] = Field(None, description="文件 ID")
    path: Optional[str] = Field(None, description="下载路径")


class DeleteTaskResponse(BaseModel):
    """删除离线任务的响应体。"""
    message: str = Field(..., description="操作消息")


class OrganizeRecordItem(BaseModel):
    """整理记录列表中的单条记录信息项。"""
    id: int = Field(..., description="记录 ID")
    file_name: str = Field(..., description="文件名")
    original_name: str = Field(..., description="原文件名")
    organized_name: str = Field(..., description="整理后的文件名")
    source_path: str = Field(..., description="源路径")
    target_path: str = Field(..., description="目标路径")
    status: str = Field(..., description="整理状态")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(..., description="创建时间")


class OrganizeRecordsResponse(BaseModel):
    """整理记录列表响应体，包含总数和记录列表。"""
    total: int = Field(..., description="记录总数")
    records: list[OrganizeRecordItem] = Field(..., description="整理记录列表")


class P115ConfigResponse(BaseModel):
    """云盘配置响应体，包含离线任务轮询间隔参数。"""
    poll_interval_min: int = Field(..., description="离线任务轮询间隔最小值（秒）")
    poll_interval_max: int = Field(..., description="离线任务轮询间隔最大值（秒）")

class LibraryItem(BaseModel):
    """媒体库配置信息项，描述单个库的路径和类型。"""
    name: str = Field(..., description="媒体库名称")
    download_path: str = Field(..., description="下载目录路径")
    target_path: str = Field(..., description="目标目录路径")
    type: str = Field(..., description="媒体库类型")
    min_transfer_size: int = Field(0, description="最小传输大小（MB）")


class XXConfigResponse(BaseModel):
    """成人片库（xx）配置响应体，包含关键词过滤列表。"""
    remove_keywords: list[str] = Field(
        default_factory=list, description="移除关键词列表"
    )


class MediaConfigResponse(BaseModel):
    """媒体配置响应体，包含库列表、格式和大小阈值。"""
    min_transfer_size: int = Field(..., description="默认最小传输大小")
    video_formats: list[str] = Field(..., description="支持的视频格式")
    libraries: list[LibraryItem] = Field(..., description="媒体库列表")
    xx: XXConfigResponse = Field(
        default_factory=XXConfigResponse, description="成人片库配置"
    )


class ConfigResponse(BaseModel):
    """完整配置响应体，包含云盘和媒体两部分配置。"""
    p115: P115ConfigResponse = Field(..., description="115 配置")
    media: MediaConfigResponse = Field(..., description="媒体配置")


class P115ConfigUpdate(BaseModel):
    """云盘账户配置更新请求，所有字段均为可选。"""
    poll_interval_min: Optional[int] = Field(None, description="轮询间隔最小值（秒）")
    poll_interval_max: Optional[int] = Field(None, description="轮询间隔最大值（秒）")


class MediaConfigUpdate(BaseModel):
    """媒体配置更新请求，所有字段均为可选。"""
    min_transfer_size: Optional[int] = Field(None, description="默认最小传输大小")
    video_formats: Optional[list[str]] = None
    libraries: Optional[list[LibraryItem]] = None
    xx: Optional[XXConfigResponse] = None


class UpdateConfigRequest(BaseModel):
    """配置更新请求体，支持同时更新云盘和媒体配置。"""
    p115: Optional[P115ConfigUpdate] = Field(None, description="115 配置更新")
    media: Optional[MediaConfigUpdate] = Field(None, description="媒体配置更新")


class UpdateConfigResponse(BaseModel):
    """配置更新操作的响应体。"""
    message: str = Field(..., description="操作消息")


class LibrariesResponse(BaseModel):
    """媒体库列表响应体。"""
    libraries: list[LibraryItem] = Field(..., description="媒体库列表")


class StatusResponse(BaseModel):
    """系统状态响应体，描述监控任务运行情况和上次检查时间。"""
    monitor_running: bool = Field(..., description="监控任务是否运行中")
    active_tasks: int = Field(..., description="活跃任务数量")
    last_check_time: Optional[str] = Field(None, description="上次检查时间")


class ErrorResponse(BaseModel):
    """API 错误响应体，包含错误详情描述。"""
    detail: str = Field(..., description="错误详情")


from typing import TypeVar, Generic

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式"""

    code: int = Field(..., description="响应码（0=成功，非0=错误）")
    message: str = Field(..., description="响应消息")
    data: Optional[T] = Field(None, description="响应数据")


def success_response(data: T, message: str = "操作成功") -> ApiResponse[T]:
    """创建成功响应"""
    return ApiResponse(code=0, message=message, data=data)


def error_response(code: int, message: str, data: Optional[T] = None) -> ApiResponse[T]:
    """创建错误响应"""
    return ApiResponse(code=code, message=message, data=data)
