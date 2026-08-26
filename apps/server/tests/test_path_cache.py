"""
@description 路径 ID 缓存与路径规范化单元测试
@responsibility 覆盖真实现（app/services/path_cache.py）：
               纯函数（normalize_path / is_temp_directory）与注入内存 SQLite 的 PathCache 读写
"""

import time

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.database import Base
from app.services.path_cache import (
    PathCache,
    is_temp_directory,
    normalize_path,
)


# ────────────────────────── 纯函数：normalize_path ──────────────────────────


class TestNormalizePath:
    """路径规范化为缓存 key 的规则"""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("", "/"),  # 空路径归一为根
            ("/", "/"),  # 根目录保持不变
            ("/a/b", "/a/b"),  # 已规范路径原样返回
            ("a/b/", "/a/b"),  # 去掉首尾斜杠
            ("//a///b//", "/a/b"),  # 压缩重复斜杠与空段
            ("/云下载/测试", "/云下载/测试"),  # 中文路径
        ],
    )
    def test_normalize(self, raw, expected):
        assert normalize_path(raw) == expected


# ──────────────────────── 纯函数：is_temp_directory ────────────────────────


class TestIsTempDirectory:
    """番号目录（临时目录）判定规则"""

    @pytest.mark.parametrize(
        "path",
        [
            "/云下载/目标/其他/MUDR-359",  # 常规番号：字母 2-10 个
            "/a/ABP-123",  # 3 字母番号
            "/a/SSIS-001",  # 前导零编号
            "/a/T28-633",  # 字母+数字前缀（FC2 系）
            "/a/ABC-12345",  # 5 位编号
        ],
    )
    def test_temp(self, path):
        assert is_temp_directory(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "/云下载/电影",  # 普通目录
            "/a/电影-2024",  # 含中文与连字符但非番号格式
            "/a/abcd-12",  # 编号仅 2 位（过短，非番号）
            "/a/ABC_123",  # 下划线分隔
            "/a/abc-123",  # 小写字母
        ],
    )
    def test_not_temp(self, path):
        assert is_temp_directory(path) is False


# ──────────────────────────── PathCache（内存 SQLite）───────────────────────────


@pytest_asyncio.fixture
async def cache_env():
    """每个测试用独立的内存 SQLite；返回 (PathCache, session_maker) 供篡改时间模拟过期"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    # get_session 风格的工厂：返回异步上下文管理器
    return PathCache(lambda: maker()), maker


@pytest.fixture
def cache(cache_env):
    """只取 PathCache 本体的简写 fixture"""
    return cache_env[0]


@pytest.mark.asyncio
async def test_cache_miss_then_hit(cache):
    """未命中返回 None；写入后命中返回 ID"""
    assert await cache.get("default", "/云下载/电影") is None

    await cache.set("default", "/云下载/电影", 12345)

    assert await cache.get("default", "/云下载/电影") == 12345


@pytest.mark.asyncio
async def test_cache_key_normalization(cache):
    """写入与读取的路径形态不同也能命中（规范化为同一 key）"""
    await cache.set("default", "//云下载///电影/", 111)

    assert await cache.get("default", "/云下载/电影") == 111


@pytest.mark.asyncio
async def test_cache_isolated_by_library(cache):
    """不同媒体库的同名路径互不干扰"""
    await cache.set("lib-a", "/云下载", 1)
    await cache.set("lib-b", "/云下载", 2)

    assert await cache.get("lib-a", "/云下载") == 1
    assert await cache.get("lib-b", "/云下载") == 2


@pytest.mark.asyncio
async def test_cache_ttl_expiry(cache_env):
    """过期条目读不到"""
    cache, maker = cache_env
    await cache.set("default", "/云下载/电影", 12345)
    # 直接篡改数据库时间模拟过期：把 expires_at 改到过去
    from sqlalchemy import text as sql_text

    async with maker() as session:
        await session.execute(
            sql_text("UPDATE path_id_cache SET expires_at = :t"),
            {"t": int(time.time()) - 1},
        )
        await session.commit()

    assert await cache.get("default", "/云下载/电影") is None


@pytest.mark.asyncio
async def test_cache_set_upsert(cache):
    """同一路径重复写入为更新而非报错"""
    await cache.set("default", "/云下载/电影", 1)
    await cache.set("default", "/云下载/电影", 2)

    assert await cache.get("default", "/云下载/电影") == 2


@pytest.mark.asyncio
async def test_cache_rejects_temp_directory(cache):
    """番号目录拒绝写入缓存"""
    await cache.set("default", "/云下载/其他/MUDR-359", 999)

    assert await cache.get("default", "/云下载/其他/MUDR-359") is None


@pytest.mark.asyncio
async def test_cache_cleanup_expired(cache_env):
    """cleanup 只删过期条目"""
    cache, maker = cache_env
    await cache.set("default", "/稳定", 1)
    from sqlalchemy import text as sql_text

    async with maker() as session:
        # 造一条已过期条目
        now = int(time.time())
        await session.execute(
            sql_text("""
                INSERT INTO path_id_cache
                (library_name, path, path_id, expires_at, hit_count, created_at, updated_at)
                VALUES ('default', '/过期', 2, :past, 0, :now, :now)
            """),
            {"past": now - 10, "now": now},
        )
        await session.commit()

    deleted = await cache.cleanup()

    assert deleted == 1
    assert await cache.get("default", "/稳定") == 1  # 未过期保留
