"""
@description 数据库模型的单元测试
@responsibility 验证 OrganizeRecord 和 OfflineTask 模型的创建和 CRUD 操作
"""

import pytest
import pytest_asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.database import init_db, get_session, Base
from app.models.organize_record import OrganizeRecord
from app.models.offline_task import OfflineTask


@pytest_asyncio.fixture
async def async_engine():
    """创建测试数据库引擎（使用内存 SQLite）；teardown 时 dispose，
    避免 aiosqlite 连接线程残留到后续测试的事件循环（表现为
    "Event loop is closed" 线程告警）
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
def async_session(async_engine):
    """创建异步会话工厂"""
    return sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_create_tables(async_engine):
    """测试数据库表创建"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_engine.connect() as conn:
        result = await conn.execute(select(1).select_from(OrganizeRecord.__table__))
        assert result.scalar() is None

        result = await conn.execute(select(1).select_from(OfflineTask.__table__))
        assert result.scalar() is None


@pytest.mark.asyncio
async def test_organize_record_crud(async_engine, async_session):
    """测试 OrganizeRecord 的 CRUD 操作"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        record = OrganizeRecord(
            task_id="task-001",
            source_path="/source/path/file.mp4",
            target_path="/target/path/file.mp4",
            file_name="file.mp4",
            file_size=1024000,
            library_name="Library-001",
            status="success",
            error_message=None,
        )
        session.add(record)
        await session.commit()

        stmt = select(OrganizeRecord).where(OrganizeRecord.task_id == "task-001")
        result = await session.execute(stmt)
        fetched_record = result.scalar_one_or_none()

        assert fetched_record is not None
        assert fetched_record.task_id == "task-001"
        assert fetched_record.file_name == "file.mp4"
        assert fetched_record.status == "success"
        assert fetched_record.created_at is not None

        fetched_record.status = "failed"
        fetched_record.error_message = "Test error"
        await session.commit()

        stmt = select(OrganizeRecord).where(OrganizeRecord.task_id == "task-001")
        result = await session.execute(stmt)
        updated_record = result.scalar_one()
        assert updated_record.status == "failed"
        assert updated_record.error_message == "Test error"

        await session.delete(updated_record)
        await session.commit()

        stmt = select(OrganizeRecord).where(OrganizeRecord.task_id == "task-001")
        result = await session.execute(stmt)
        deleted_record = result.scalar_one_or_none()
        assert deleted_record is None


@pytest.mark.asyncio
async def test_offline_task_crud(async_engine, async_session):
    """测试 OfflineTask 的 CRUD 操作"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        task = OfflineTask(
            info_hash="abc123def456ghi789",
            name="Test Torrent",
            library_name="Library-002",
            status="pending",
            add_time=datetime.now(),
        )
        session.add(task)
        await session.commit()

        stmt = select(OfflineTask).where(OfflineTask.info_hash == "abc123def456ghi789")
        result = await session.execute(stmt)
        fetched_task = result.scalar_one_or_none()

        assert fetched_task is not None
        assert fetched_task.info_hash == "abc123def456ghi789"
        assert fetched_task.name == "Test Torrent"
        assert fetched_task.status == "pending"
        assert fetched_task.created_at is not None
        assert fetched_task.updated_at is not None

        fetched_task.status = "downloading"
        await session.commit()

        stmt = select(OfflineTask).where(OfflineTask.info_hash == "abc123def456ghi789")
        result = await session.execute(stmt)
        updated_task = result.scalar_one()
        assert updated_task.status == "downloading"

        fetched_task.status = "completed"
        fetched_task.complete_time = datetime.now()
        await session.commit()

        stmt = select(OfflineTask).where(OfflineTask.info_hash == "abc123def456ghi789")
        result = await session.execute(stmt)
        completed_task = result.scalar_one()
        assert completed_task.status == "completed"
        assert completed_task.complete_time is not None

        await session.delete(completed_task)
        await session.commit()

        stmt = select(OfflineTask).where(OfflineTask.info_hash == "abc123def456ghi789")
        result = await session.execute(stmt)
        deleted_task = result.scalar_one_or_none()
        assert deleted_task is None
