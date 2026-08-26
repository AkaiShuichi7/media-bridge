"""
@description 云盘服务中立契约
@responsibility 定义应用层对云盘能力的全部抽象操作；
               契约只流通中立类型（CloudFile / CloudTask），
               提供商原始响应形状必须被适配器挡在 seam 之内
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.schemas.cloud_types import CloudFile, CloudTask


class CloudService(ABC):
    """云盘提供商的应用级契约。

    契约只暴露每个受支持提供商都能真正实现的操作。
    目录创建通过 :meth:`get_path_id` 完成（115 API 是基于路径的）。
    """

    @abstractmethod
    async def list_files(self, dir_id: str) -> list[CloudFile]:
        """列出目录内容，返回标准化的 CloudFile 列表。"""

    @abstractmethod
    async def move_file(self, file_id: str, target_dir_id: str) -> bool:
        """移动文件并报告是否成功。"""

    @abstractmethod
    async def rename_file(self, file_id: str, new_name: str) -> bool:
        """重命名文件并报告是否成功。"""

    @abstractmethod
    async def get_path_id(
        self, path: str, mkdir: bool = True, library_name: str = "default"
    ) -> Optional[str]:
        """解析路径到目录 ID，可选地创建缺失目录。"""

    @abstractmethod
    async def add_offline_task(self, url: str, save_dir_id: str) -> tuple[bool, str, Optional[str]]:
        """创建一个离线下载任务。

        Returns:
            (是否成功, 错误信息, 任务 info_hash——提供商未返回时为 None)
        """

    @abstractmethod
    async def get_offline_tasks(self) -> list[CloudTask]:
        """返回当前可见的全部离线任务（标准化 CloudTask 列表）。"""

    @abstractmethod
    async def get_offline_task(self, task_hash: str) -> Optional[CloudTask]:
        """返回单个离线任务，不存在时返回 None。"""

    @abstractmethod
    async def delete_offline_task(self, task_hash: str) -> bool:
        """删除离线任务并报告是否成功。"""

    @abstractmethod
    async def delete_file(self, file_id: str) -> bool:
        """删除文件并报告是否成功。"""
