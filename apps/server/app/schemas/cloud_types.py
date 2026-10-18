"""
@description 云盘领域类型定义
@responsibility 定义 CloudFile / CloudTask 数据类、CloudTaskStatus 中立状态枚举
               与 115 字段映射；它们是 CloudService seam 两侧的唯一货币，
               115 原始 dict 形状与状态码语义被关在适配器内
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# 115 原始字段名 → 标准字段名映射表
P115_FIELD_MAP: dict = {
    "fid": "file_id",  # 文件唯一 ID
    "n": "name",  # 文件/目录名称
    "s": "size",  # 文件大小（字节）
    "cid": "parent_id",  # 父目录 ID
    "pid": "pick_code",  # 提取码
}


class CloudTaskStatus(Enum):
    """云盘离线任务的中立状态枚举（与提供商状态码解耦）。

    数值口径的映射约定见 :func:`cloud_task_status_from_code` /
    :func:`cloud_task_status_to_code`：2=完成、负数=失败、1=等待中、0=下载中。
    """

    PENDING = "pending"  # 已提交、未开始下载
    DOWNLOADING = "downloading"  # 下载中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


def cloud_task_status_from_code(code: int) -> CloudTaskStatus:
    """提供商原始状态码 → 中立枚举（仅适配器翻译与 API 入参映射使用）。

    规则：2=完成；负数=失败；1=等待中；0 及其余未知非负值视为下载中
    （非终态的保守处理）。
    """
    if code == 2:
        return CloudTaskStatus.COMPLETED
    if code < 0:
        return CloudTaskStatus.FAILED
    if code == 1:
        return CloudTaskStatus.PENDING
    return CloudTaskStatus.DOWNLOADING


def cloud_task_status_to_code(status: CloudTaskStatus) -> int:
    """中立枚举 → 对外 API 的稳定数值口径。

    前端契约沿用 115 时代的数值语义：2=完成、负数=失败（统一映射为 -1）、
    1=等待中、0=下载中。
    """
    if status is CloudTaskStatus.COMPLETED:
        return 2
    if status is CloudTaskStatus.FAILED:
        return -1
    if status is CloudTaskStatus.PENDING:
        return 1
    return 0


@dataclass
class CloudFile:
    """云盘文件/目录的标准化数据类"""

    file_id: str  # 文件唯一标识
    name: str  # 文件或目录名称
    size: int  # 文件大小（字节），目录为 0
    parent_id: str  # 父目录 ID
    is_directory: bool  # 是否为目录（True=目录，False=文件）
    pick_code: str = ""  # 提取码，目录可能为空

    @classmethod
    def from_p115_dict(cls, raw: dict) -> "CloudFile":
        """
        将 115 原始响应字典转换为标准 CloudFile 对象

        Args:
            raw: 115 API 返回的原始字典，字段为短名如 fid、n、s、cid、pid

        Returns:
            标准化的 CloudFile 实例

        Note:
            通过是否含有 `fid` 字段区分文件与目录：
            - 有 `fid` → 文件（is_directory=False）
            - 无 `fid` → 目录（is_directory=True）
        """
        # fid 存在为文件，缺失为目录
        is_directory = "fid" not in raw

        return cls(
            file_id=str(raw.get("fid", raw.get("cid", ""))),
            name=raw.get("n", ""),
            size=int(raw.get("s", 0)),
            parent_id=str(raw.get("cid", "")),
            is_directory=is_directory,
            pick_code=raw.get("pid", ""),
        )


@dataclass
class CloudTask:
    """云盘离线任务的标准化数据类"""

    info_hash: str  # 任务唯一标识（BT info_hash）
    name: str  # 任务名称
    status: CloudTaskStatus  # 任务中立状态枚举（数值口径映射见 CloudTaskStatus 注释）
    progress: int  # 进度百分比（0-100）
    file_id: str  # 任务产物所在目录的文件 ID（空串表示未知）
    path: str  # 任务产物所在路径（空串表示未知）
    add_time: datetime  # 任务创建时间

    @classmethod
    def from_p115_dict(cls, raw: dict) -> "CloudTask":
        """
        将 115 原始离线任务字典转换为标准 CloudTask 对象

        Args:
            raw: 115 clouddownload_task_list 返回的单条任务字典

        Returns:
            标准化的 CloudTask 实例（status 已翻译为中立枚举）
        """
        return cls(
            info_hash=str(raw.get("info_hash", "")),
            name=raw.get("name", ""),
            status=cloud_task_status_from_code(int(raw.get("status", 0))),
            progress=int(raw.get("percent_done", 0)),
            file_id=str(raw.get("file_id", "") or ""),
            path=raw.get("path", "") or "",
            add_time=datetime.fromtimestamp(raw.get("add_time", 0)),
        )
