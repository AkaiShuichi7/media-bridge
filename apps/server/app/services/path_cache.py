"""
@description 路径 ID 缓存模块（唯一实现）
@responsibility 提供路径规范化、临时目录判定、路径与 115 目录 ID 映射的读写与 TTL 清理；
               通过可注入的 session 工厂解耦持久层，P115Client 与测试均通过同一接口使用
"""

import re
import time
from contextlib import AbstractAsyncContextManager
from typing import Any, Callable, Optional

from loguru import logger
from sqlalchemy import select, text

# 缓存默认过期时间（秒）
CACHE_TTL_SECONDS = 600

# 临时目录（番号目录）判定正则：
# - 前缀为 2~10 个大写字母（如 MUDR、SSIS、ABP）
# - 或 1 个大写字母 + 1~2 位数字（如 FC2 系列的 T28、R18 等）
# - 后缀为 3~5 位数字（如 359、001、12345）
_TEMP_DIR_PATTERN = re.compile(r"^(?:[A-Z]{2,10}|[A-Z]\d{1,2})-\d{3,5}$")


def normalize_path(path: str) -> str:
    """
    规范化路径为缓存 key。

    Args:
        path: 原始路径字符串，可能带有多余的首尾/重复斜杠

    Returns:
        str: 以 / 开头、无空段、无首尾斜杠（根目录除外）的规范化路径
    """
    if not path or path == "/":
        return "/"
    # 去除首尾斜杠后分割，过滤空段再重新拼接
    parts = [p for p in path.strip("/").split("/") if p]
    return "/" + "/".join(parts)


def is_temp_directory(path: str) -> bool:
    """
    判断路径最后一级是否为临时目录（番号目录）。

    番号目录生命周期短（单个任务整理完成后即无意义），
    不应进入路径缓存，否则缓存表会被大量一次性条目污染。

    匹配示例：MUDR-359、ABP-123、SSIS-001、T28-633

    Args:
        path: 完整路径

    Returns:
        bool: True 表示是临时目录，不应缓存
    """
    last_part = path.rsplit("/", 1)[-1]
    is_temp = bool(_TEMP_DIR_PATTERN.match(last_part))
    if is_temp:
        logger.debug(f"检测到临时目录，跳过缓存: {last_part}")
    return is_temp


class PathCache:
    """
    路径 -> 115 目录 ID 的持久化缓存。

    接口只有三个方法（get / set / cleanup），session 工厂在构造时注入：
    - 生产环境传入 app.core.database.get_session
    - 测试传入内存 SQLite 的 session 工厂
    这样 HTTP 客户端（P115Client）不再直接依赖数据库实现细节。
    """

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[Any]],
        ttl_seconds: int = CACHE_TTL_SECONDS,
    ):
        """
        Args:
            session_factory: 返回异步 session 上下文管理器的工厂
                （如 app.core.database.get_session 这类 @asynccontextmanager）
            ttl_seconds: 缓存条目有效期（秒）
        """
        self._session_factory = session_factory
        self._ttl_seconds = ttl_seconds

    async def get(self, library_name: str, path: str) -> Optional[int]:
        """
        读取缓存的路由 ID（读时过滤过期条目）。

        Args:
            library_name: 媒体库名称（同一路径在不同库下可指向不同目录）
            path: 目录路径

        Returns:
            Optional[int]: 缓存的目录 ID；未命中或已过期返回 None
        """
        # 延迟导入 ORM 模型：避免 services 层在模块加载期反向依赖 models 层
        from app.models.path_id_cache import PathIdCache

        normalized = normalize_path(path)
        now = int(time.time())

        async with self._session_factory() as session:
            result = await session.execute(
                select(PathIdCache.path_id).where(
                    PathIdCache.library_name == library_name,
                    PathIdCache.path == normalized,
                    PathIdCache.expires_at > now,  # 读时过滤过期
                )
            )
            row = result.scalar_one_or_none()
            return row if row is not None else None

    async def set(
        self,
        library_name: str,
        path: str,
        path_id: int,
    ) -> None:
        """
        写入缓存（UPSERT，并发安全；番号目录拒绝写入）。

        Args:
            library_name: 媒体库名称
            path: 目录路径
            path_id: 115 目录 ID
        """
        normalized = normalize_path(path)

        # 番号目录不缓存：一次任务后即失效，写入只会污染缓存表
        if is_temp_directory(normalized):
            return

        now = int(time.time())
        expires_at = now + self._ttl_seconds

        async with self._session_factory() as session:
            # 原生 SQL UPSERT：同一 (library_name, path) 冲突时更新而非报错
            await session.execute(
                text("""
                    INSERT INTO path_id_cache
                    (library_name, path, path_id, expires_at, hit_count, created_at, updated_at)
                    VALUES (:library_name, :path, :path_id, :expires_at, 0, :now, :now)
                    ON CONFLICT(library_name, path) DO UPDATE SET
                        path_id = excluded.path_id,
                        expires_at = excluded.expires_at,
                        updated_at = excluded.updated_at
                """),
                {
                    "library_name": library_name,
                    "path": normalized,
                    "path_id": path_id,
                    "expires_at": expires_at,
                    "now": now,
                },
            )
            await session.commit()

    async def cleanup(self, batch_size: int = 1000) -> int:
        """
        批量清理过期条目。

        Args:
            batch_size: 单批删除上限，避免长事务锁表

        Returns:
            int: 实际删除的条目数
        """
        now = int(time.time())

        async with self._session_factory() as session:
            result = await session.execute(
                text("""
                    DELETE FROM path_id_cache
                    WHERE id IN (
                        SELECT id FROM path_id_cache
                        WHERE expires_at <= :now
                        LIMIT :limit
                    )
                """),
                {"now": now, "limit": batch_size},
            )
            await session.commit()
            return result.rowcount or 0
