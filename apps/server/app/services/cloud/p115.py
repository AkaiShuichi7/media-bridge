"""
@description CloudService 契约的 115 实现（适配器）
@responsibility 把 P115Client 的 115 原始响应翻译成中立类型（CloudFile/CloudTask），
               115 的 dict 形状被关在本模块内，不向 seam 之外泄漏
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from loguru import logger

from app.schemas.cloud_types import CloudFile, CloudTask
from app.services.cloud.base import CloudService

if TYPE_CHECKING:
    from app.services.p115_client import P115Client


class P115CloudService(CloudService):
    """把 115 SDK 封装规范化为应用级契约。"""

    def __init__(self, client: "P115Client") -> None:
        self._client = client

    async def list_files(self, dir_id: str) -> list[CloudFile]:
        """列出目录内容，逐条翻译为 CloudFile（目录/文件判定收敛在此）"""
        result = await self._client.list_directory(dir_id)
        if not result.get("state"):
            logger.error(f"列出目录失败: dir_id={dir_id}")
            return []
        return [CloudFile.from_p115_dict(item) for item in result.get("data", [])]

    async def move_file(self, file_id: str, target_dir_id: str) -> bool:
        """移动文件，按 state 字段翻译为 bool"""
        result = await self._client.move_file(file_id, target_dir_id)
        return bool(result.get("state", False))

    async def rename_file(self, file_id: str, new_name: str) -> bool:
        """重命名文件，按 state 字段翻译为 bool"""
        result = await self._client.rename_file(file_id, new_name)
        return bool(result.get("state", False))

    async def get_path_id(
        self, path: str, mkdir: bool = True, library_name: str = "default"
    ) -> Optional[str]:
        """路径解析直接透传（P115Client 内部已含缓存与遍历）"""
        return await self._client.get_path_id(
            path, mkdir=mkdir, library_name=library_name
        )

    async def add_offline_task(self, url: str, save_dir_id: str) -> tuple[bool, str, Optional[str]]:
        """添加离线任务，翻译响应为 (成功, 错误信息, info_hash)

        115 可能不返回 info_hash，此时返回 None 由调用方用 magnet 解析结果兜底。
        """
        result = await self._client.add_offline_task(url, save_dir_id)
        ok = bool(result.get("state"))
        error_msg = result.get("error_msg", "未知错误") if not ok else ""
        # 不同接口版本可能用不同 key 返回任务标识
        info_hash = (
            result.get("info_hash") or result.get("hash") or result.get("task_id")
        )
        return ok, error_msg, info_hash

    async def get_offline_tasks(self) -> list[CloudTask]:
        """获取离线任务列表并逐条翻译为 CloudTask（解包逻辑只在此处存在一份）"""
        result = await self._client.get_offline_tasks()
        if not isinstance(result, dict):
            logger.warning("115 任务列表返回了非 dict 响应")
            return []
        if not result.get("state"):
            logger.warning(f"获取 115 任务列表失败: {result.get('error_msg', '')}")
            return []
        tasks = result.get("tasks") or result.get("data") or []
        return [CloudTask.from_p115_dict(t) for t in tasks]

    async def get_offline_task(self, task_hash: str) -> Optional[CloudTask]:
        """按 info_hash 查找单个任务"""
        for task in await self.get_offline_tasks():
            if task.info_hash == task_hash:
                return task
        return None

    async def delete_offline_task(self, task_hash: str) -> bool:
        """删除离线任务，按 state 字段翻译为 bool"""
        result = await self._client.delete_offline_task(task_hash)
        return bool(result.get("state", False))

    async def delete_file(self, file_id: str) -> bool:
        """删除文件，按 state 字段翻译为 bool"""
        result = await self._client.delete_file(file_id)
        return bool(result.get("state", False)) if isinstance(result, dict) else bool(result)
