"""
@description Agent 归档查询接口测试
@responsibility 覆盖 GET /api/agent/archive/query 的聚合查询行为：
               整理记录/本地任务两侧命中、info_hash 去重、四类 kind 映射、
               空库与数据库不可用降级
"""

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import agent as agent_api
from app.core.database import Base
from app.models.offline_task import OfflineTask
from app.models.organize_record import OrganizeRecord
from app.services.file_organizer import FileOrganizer
from app.services.offline_task_service import OfflineTaskService


@pytest.fixture
def db():
    """内存 SQLite 异步引擎 + session 工厂（每测试独立）"""
    engine = create_async_engine("sqlite+aiosqlite://")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    return engine, sessionmaker


@pytest_asyncio.fixture
async def seeded_db(db):
    """建表并预置数据：1 条已归档记录 + 3 条不同生命周期的任务"""
    engine, sessionmaker = db
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with sessionmaker() as session:
        session.add(
            OrganizeRecord(
                task_id="hash_done",
                source_path="/源/MUDR-359.mp4",
                target_path="/媒体/xx-MOODYZ/MUDR-359/MUDR-359.mp4",
                file_name="MUDR-359.mp4",
                file_size=1024,
                library_name="xx-MOODYZ",
                status="success",
                created_at=datetime(2026, 10, 18, 12, 0, 0),
            )
        )
        session.add(
            OfflineTask(
                info_hash="hash_inflight",
                name="MUDR-360合集",
                library_name="xx-MOODYZ",
                status="downloading",
                add_time=datetime(2026, 10, 18, 13, 0, 0),
            )
        )
        session.add(
            OfflineTask(
                info_hash="hash_failed",
                name="MUDR-361",
                library_name="xx-MOODYZ",
                status="organize_failed",
                error_message="移动失败",
                add_time=datetime(2026, 10, 18, 14, 0, 0),
            )
        )
        # 不含关键词的任务（验证不误命中）
        session.add(
            OfflineTask(
                info_hash="hash_other",
                name="其他任务",
                library_name="电影库",
                status="added",
                add_time=datetime(2026, 10, 18, 15, 0, 0),
            )
        )
        await session.commit()

    return engine, sessionmaker


def _patched_session(sessionmaker):
    """构造注入 service/organizer 模块命名空间的 get_session 替身"""

    @asynccontextmanager
    async def _get_session():
        async with sessionmaker() as session:
            yield session

    return _get_session


def _build_app(sessionmaker) -> FastAPI:
    """组装被测应用：真实服务 + 内存库 session 注入"""
    app = FastAPI()
    organizer = FileOrganizer(MagicMock())
    service = OfflineTaskService(MagicMock(), MagicMock(), organizer)
    app.state.container = MagicMock(
        offline_task_service=service, file_organizer=organizer
    )
    app.include_router(agent_api.router, prefix="/api")

    session_dep = _patched_session(sessionmaker)
    patcher_service = patch(
        "app.services.offline_task_service.get_session", session_dep
    )
    patcher_organizer = patch(
        "app.services.file_organizer.get_session", session_dep
    )
    patcher_service.start()
    patcher_organizer.start()
    return app


@pytest_asyncio.fixture
async def client(seeded_db):
    """异步 HTTP 测试客户端"""
    app = _build_app(seeded_db[1])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestArchiveQuery:
    @pytest.mark.asyncio
    async def test_archived_hit_from_record(self, client):
        """整理记录 success → archived 命中，携带目标路径与库"""
        resp = await client.get("/api/agent/archive/query", params={"q": "MUDR-359"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        hit = next(h for h in data["hits"] if h["info_hash"] == "hash_done")
        assert hit["kind"] == "archived"
        assert hit["library_name"] == "xx-MOODYZ"
        assert "MUDR-359" in hit["path"]

    @pytest.mark.asyncio
    async def test_in_flight_and_failed_kinds(self, client):
        """downloading → in_flight；organize_failed → failed"""
        resp = await client.get("/api/agent/archive/query", params={"q": "MUDR"})
        assert resp.status_code == 200
        kinds = {h["info_hash"]: h["kind"] for h in resp.json()["data"]["hits"]}
        assert kinds["hash_inflight"] == "in_flight"
        assert kinds["hash_failed"] == "failed"

    @pytest.mark.asyncio
    async def test_record_dedupes_task_side(self, client):
        """整理记录已覆盖的 info_hash 不再出现任务侧重复命中"""
        engine, sessionmaker = None, None  # 占位避免误用
        resp = await client.get("/api/agent/archive/query", params={"q": "MUDR"})
        hits = resp.json()["data"]["hits"]
        # hash_done 只出现一次（记录侧），任务侧不重复
        done_hits = [h for h in hits if h["info_hash"] == "hash_done"]
        assert len(done_hits) == 1
        assert done_hits[0]["kind"] == "archived"

    @pytest.mark.asyncio
    async def test_no_false_positive(self, client):
        """不含关键词的记录不命中"""
        resp = await client.get("/api/agent/archive/query", params={"q": "MUDR"})
        hashes = {h["info_hash"] for h in resp.json()["data"]["hits"]}
        assert "hash_other" not in hashes

    @pytest.mark.asyncio
    async def test_empty_query_rejected(self, client):
        """空关键词返回 422（q 必填）"""
        resp = await client.get("/api/agent/archive/query")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_database_returns_zero(self, db):
        """空库：查询成功且命中为空"""
        engine, sessionmaker = db
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        app = _build_app(sessionmaker)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/agent/archive/query", params={"q": "NOTHING"}
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_db_broken_degrades_gracefully(self, db):
        """数据库不可用：降级为空命中而非 500（与查询侧其他方法一致）"""
        engine, _ = db

        @asynccontextmanager
        async def broken_session():
            raise RuntimeError("db down")
            yield  # pragma: no cover

        app = FastAPI()
        organizer = FileOrganizer(MagicMock())
        service = OfflineTaskService(MagicMock(), MagicMock(), organizer)
        app.state.container = MagicMock(offline_task_service=service)
        app.include_router(agent_api.router, prefix="/api")

        with patch(
            "app.services.offline_task_service.get_session", broken_session
        ), patch(
            "app.services.file_organizer.get_session", broken_session
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as ac:
                resp = await ac.get(
                    "/api/agent/archive/query", params={"q": "MUDR"}
                )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0
