"""
@description p115client 异步封装
@responsibility 仅负责 115 API 的调用、重试与限速；
               路径缓存（PathCache）与路径遍历逻辑通过注入协作，不再内联 SQL 与缓存算法
"""

import asyncio
import random
from typing import Any, Optional

from loguru import logger
from p115client import P115Client as P115SyncClient

from app.services.path_cache import PathCache, normalize_path

# 最大重试次数
MAX_RETRY_COUNT = 3
# 指数退避基数（秒）
BACKOFF_BASE = 2


class P115Client:
    """p115 客户端单例封装（HTTP 适配器 + 路径遍历编排）"""

    _instance: Optional["P115Client"] = None
    _lock: asyncio.Lock = asyncio.Lock()
    _client: Optional[P115SyncClient] = None
    _cookies: Optional[str] = None

    def __init__(self, cookies: str, path_cache: Optional[PathCache] = None):
        """
        Args:
            cookies: 115 登录 cookies
            path_cache: 路径缓存；不传时自建（绑定全局数据库 session 工厂）
        """
        self._cookies = cookies
        # p115client 0.0.9.4.9.1 accepts cookies directly; the obsolete
        # check_for_relogin keyword prevents the container from starting.
        self._client = P115SyncClient(cookies)
        # 缓存依赖注入：测试可传内存实现；生产默认绑定全局数据库
        if path_cache is not None:
            self._path_cache = path_cache
        else:
            from app.core.database import get_session

            self._path_cache = PathCache(get_session)

    @classmethod
    async def get_client(cls, cookies: str) -> "P115Client":
        """获取客户端实例（单例模式）"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(cookies)
                    logger.info("p115 客户端实例已创建")
        return cls._instance

    async def _retry_with_backoff(
        self, func, *args, max_retries: int = MAX_RETRY_COUNT, **kwargs
    ) -> Any:
        """执行 API 调用并在失败时自动重试（指数退避）"""
        for attempt in range(max_retries):
            try:
                await self._rate_limit()
                result = await asyncio.to_thread(func, *args, **kwargs)
                return result
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"API 调用失败，已达到最大重试次数: {e}")
                    raise

                backoff_time = BACKOFF_BASE**attempt
                logger.warning(
                    f"API 调用失败（第 {attempt + 1} 次），{backoff_time}秒后重试: {e}"
                )
                await asyncio.sleep(backoff_time)

    async def _rate_limit(self) -> None:
        """API 调用速率限制（随机延迟 0.5-1 秒）"""
        delay = random.uniform(0.5, 1.0)
        await asyncio.sleep(delay)

    async def add_offline_task(self, magnet: str, path_id: str) -> dict:
        """添加离线下载任务"""
        return await self._retry_with_backoff(
            self._client.clouddownload_task_add_url,
            {"url": magnet, "wp_path_id": path_id},
        )

    async def get_offline_tasks(self) -> dict:
        """获取离线任务列表"""
        return await self._retry_with_backoff(
            self._client.clouddownload_task_list,
            {"page": 1, "page_size": 1000},
        )

    async def get_task_status(self, info_hash: str) -> Optional[dict]:
        """获取单个任务状态"""
        tasks_response = await self.get_offline_tasks()

        if not tasks_response.get("state"):
            return None

        tasks = tasks_response.get("tasks") or tasks_response.get("data") or []
        for task in tasks:
            if task.get("info_hash") == info_hash:
                return task

        return None

    async def delete_offline_task(self, info_hash: str) -> dict:
        """删除离线任务"""
        return await self._retry_with_backoff(
            self._client.clouddownload_task_del,
            {"hash[0]": info_hash, "flag": 0},
        )

    async def clear_completed_tasks(self) -> dict:
        """清理已完成的离线任务"""
        return await self._retry_with_backoff(self._client.clouddownload_task_clear, 0)

    async def get_path_id(
        self, path: str, mkdir: bool = True, library_name: str = "default"
    ) -> Optional[str]:
        """
        获取目录 ID（带数据库缓存）
        - 缓存命中：直接返回
        - 缓存未命中：遍历 fs_files，成功后写入缓存
        """
        try:
            # 根目录特殊处理
            if not path or path == "/":
                return "0"

            # 1. 规范化路径
            normalized_path = normalize_path(path)

            # 2. 使用分层缓存查询
            start_id, remaining_path = await self._find_nearest_cached_ancestor(
                library_name, normalized_path
            )

            if not remaining_path:
                # 完全命中缓存
                logger.debug(f"缓存完全命中: {normalized_path} -> {start_id}")
                return start_id

            logger.debug(
                f"缓存部分命中，从 cid={start_id} 开始遍历剩余路径: {remaining_path}"
            )

            # 3. 从缓存位置开始遍历剩余路径
            parts = remaining_path.split("/")
            current_id = start_id

            # 计算已遍历的路径前缀（用于目录创建）
            normalized_parts = normalized_path.strip("/").split("/")
            traversed_count = len(normalized_parts) - len(parts)

            for idx, part in enumerate(parts):
                if not part:
                    continue

                # 使用 fs_files 列出当前目录内容
                result = await self._retry_with_backoff(
                    self._client.fs_files, {"cid": current_id, "limit": 1000}, base_url="https://webapi.115.com"
                )
                # 查找匹配的子目录 (目录没有 fid 字段, n 是名称)
                found = False
                for item in result.get("data", []):
                    is_dir = "fid" not in item  # 目录没有 fid 字段
                    if item.get("n") == part and is_dir:
                        current_id = str(item.get("cid"))  # 目录使用 cid
                        logger.debug(f"找到目录: {part}, cid={current_id}")
                        found = True
                        break

                if not found:
                    if mkdir:
                        # 创建目录（使用完整路径）
                        full_path_to_create = "/" + "/".join(
                            normalized_parts[: traversed_count + idx + 1]
                        )
                        create_result = await self._retry_with_backoff(
                            self._client.fs_makedirs_app, full_path_to_create
                        )
                        if create_result.get("state"):
                            # 优先从创建结果直接取 cid，避免因目录过多 fs_files 分页导致找不到
                            if "cid" in create_result:
                                current_id = str(create_result["cid"])
                                found = True
                            elif "data" in create_result and "cid" in create_result["data"]:
                                current_id = str(create_result["data"]["cid"])
                                found = True
                            elif "id" in create_result:
                                current_id = str(create_result["id"])
                                found = True
                            else:
                                logger.error(f"创建成功但返回结果没有包含 cid: {create_result}")
                                found = False

                            if found:
                                logger.debug(f"通过创建接口获取目录 ID: {part}, cid={current_id}")

                    if not found:
                        logger.error(f"目录不存在且创建失败: {normalized_path}")
                        return None

                # 每级目录遍历成功后缓存中间路径
                # （番号目录在 PathCache.set 内部被拒绝，无需在此重复判断）
                intermediate_path = "/" + "/".join(normalized_parts[:traversed_count + idx + 1])
                if str(current_id) != "0":
                    await self._path_cache.set(library_name, intermediate_path, int(current_id))

            return current_id
        except Exception as e:
            logger.error(f"获取目录 ID 失败: {path}, 错误: {e}")
            raise e

    async def move_file(self, file_id: str, target_id: str) -> dict:
        """移动文件到目标目录"""
        return await self._retry_with_backoff(
            self._client.fs_move, {"fid": file_id, "pid": target_id}
        )

    async def rename_file(self, file_id: str, new_name: str) -> dict:
        """重命名文件"""
        return await self._retry_with_backoff(
            self._client.fs_rename, (int(file_id), new_name)
        )

    async def delete_file(self, file_id: str) -> dict:
        """删除文件"""
        return await self._retry_with_backoff(self._client.fs_delete, file_id)

    async def list_directory(self, path_id: str) -> dict:
        """列出目录内容"""
        return await self._retry_with_backoff(
            self._client.fs_files, {"cid": path_id, "limit": 1000}, base_url="https://webapi.115.com"
        )

    async def verify_cookies(self) -> bool:
        """验证 cookies 有效性"""
        try:
            result = await self._retry_with_backoff(self._client.user_info)
            return result.get("state", False)
        except Exception as e:
            logger.error(f"验证 cookies 失败: {e}")
            return False

    async def _find_nearest_cached_ancestor(
        self, library_name: str, path: str
    ) -> tuple[str | None, str]:
        """
        查找最近的已缓存祖先目录

        Args:
            library_name: 库名称
            path: 目标路径，如 /云下载/测试/目标/其他/MUDR-359

        Returns:
            tuple: (缓存的路径ID, 需要继续遍历的相对路径)
            例如: 如果 /云下载/测试/目标 被缓存，返回 (cid, "其他/MUDR-359")
        """
        parts = path.strip("/").split("/")

        # 从完整路径开始，逐级向上查找缓存
        for i in range(len(parts), 0, -1):
            ancestor_path = "/" + "/".join(parts[:i])
            cached_id = await self._path_cache.get(library_name, ancestor_path)
            if cached_id is not None:
                remaining_path = "/".join(parts[i:]) if i < len(parts) else ""
                logger.debug(
                    f"找到缓存祖先: {ancestor_path} -> {cached_id}, 剩余路径: {remaining_path or '(空)'}"
                )
                return str(cached_id), remaining_path

        # 没有找到任何缓存，从根目录开始
        logger.debug(f"未找到任何缓存祖先，从根目录开始遍历")
        return "0", path.strip("/")
