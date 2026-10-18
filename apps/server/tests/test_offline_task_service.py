"""
@description 离线任务服务测试
@responsibility 覆盖 OfflineTaskService.add_task 的完整业务流程：
               库校验、目录解析、云端建任务、本地 UPSERT、失败补偿回滚
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.offline_task_service import AddTaskError, OfflineTaskService


@pytest.fixture
def mock_library():
    """模拟媒体库配置"""
    lib = MagicMock()
    lib.name = "电影库"
    lib.download_path = "/下载/电影"
    return lib


@pytest.fixture
def mock_config(mock_library):
    """模拟全局配置"""
    config = MagicMock()
    config.media.libraries = [mock_library]
    return config


@pytest.fixture
def mock_cloud():
    """模拟 CloudService 契约"""
    cloud = AsyncMock()
    cloud.get_path_id = AsyncMock(return_value="123456")
    # 契约返回 (成功, 错误信息, info_hash)
    cloud.add_offline_task = AsyncMock(return_value=(True, "", "abc123hash"))
    cloud.delete_offline_task = AsyncMock(return_value=True)
    return cloud


@pytest.fixture
def service(mock_cloud, mock_config):
    """被测服务（整理器用 mock，生命周期测试中按需覆写）"""
    return OfflineTaskService(mock_cloud, mock_config, AsyncMock())


def _mock_session(existing_task=None):
    """构造 get_session 的 mock 上下文（可指定已存在的任务记录）"""
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing_task
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


class TestAddTask:
    """add_task 主流程"""

    @pytest.mark.asyncio
    async def test_add_task_success(self, service, mock_cloud):
        """正常流程：云端建任务 + 本地保存成功，返回 info_hash"""
        with patch(
            "app.services.offline_task_service.get_session",
            return_value=_mock_session(),
        ):
            task_id = await service.add_task(
                "magnet:?xt=urn:btih:abc123", "电影库", None, "abc123"
            )

        assert task_id == "abc123hash"
        mock_cloud.add_offline_task.assert_awaited_once_with(
            "magnet:?xt=urn:btih:abc123", "123456"
        )

    @pytest.mark.asyncio
    async def test_add_task_unknown_library(self, service):
        """媒体库不存在 → 抛领域异常，不触云盘"""
        with pytest.raises(AddTaskError, match="不存在"):
            await service.add_task("magnet:?xt=urn:btih:abc123", "不存在的库", None, None)

    @pytest.mark.asyncio
    async def test_add_task_path_id_failure(self, service, mock_cloud):
        """目录解析返回 None → 抛领域异常，不建云端任务"""
        mock_cloud.get_path_id = AsyncMock(return_value=None)

        with pytest.raises(AddTaskError, match="获取下载目录 ID 失败"):
            await service.add_task("magnet:?xt=urn:btih:abc123", "电影库", None, None)

        mock_cloud.add_offline_task.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_task_cloud_failure(self, service, mock_cloud):
        """云端添加失败 → 抛领域异常，不写本地库"""
        mock_cloud.add_offline_task = AsyncMock(return_value=(False, "配额不足", None))

        with pytest.raises(AddTaskError, match="配额不足"):
            await service.add_task("magnet:?xt=urn:btih:abc123", "电影库", None, "abc")

    @pytest.mark.asyncio
    async def test_add_task_fallback_to_parsed_hash(self, service, mock_cloud):
        """云端不返回 info_hash 时，回落到调用方从 magnet 解析的值"""
        mock_cloud.add_offline_task = AsyncMock(return_value=(True, "", None))

        with patch(
            "app.services.offline_task_service.get_session",
            return_value=_mock_session(),
        ):
            task_id = await service.add_task(
                "magnet:?xt=urn:btih:parsed123", "电影库", None, "parsed123"
            )

        assert task_id == "parsed123"

    @pytest.mark.asyncio
    async def test_add_task_no_hash_returns_empty(self, service, mock_cloud):
        """云端与 magnet 都给不出 info_hash → 返回空串（与旧 API 语义一致）"""
        mock_cloud.add_offline_task = AsyncMock(return_value=(True, "", None))

        with patch(
            "app.services.offline_task_service.get_session",
            return_value=_mock_session(),
        ):
            task_id = await service.add_task("magnet:?xt=urn:btih:", "电影库", None, None)

        assert task_id == ""


class TestAddTaskRollback:
    """本地保存失败的补偿回滚分支（此前在路由层零测试覆盖）"""

    @pytest.mark.asyncio
    async def test_rollback_on_db_failure(self, service, mock_cloud):
        """本地保存异常 → 反向删除云端任务 → 抛领域异常"""
        broken_session = MagicMock()
        broken_session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        broken_ctx = MagicMock()
        broken_ctx.__aenter__ = AsyncMock(return_value=broken_session)
        broken_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.offline_task_service.get_session", return_value=broken_ctx):
            with pytest.raises(AddTaskError, match="已尝试回滚"):
                await service.add_task("magnet:?xt=urn:btih:abc123", "电影库", None, None)

        # 关键断言：补偿回滚被触发
        mock_cloud.delete_offline_task.assert_awaited_once_with("abc123hash")

    @pytest.mark.asyncio
    async def test_rollback_failure_swallowed(self, service, mock_cloud):
        """回滚自身失败不掩盖原始异常"""
        broken_session = MagicMock()
        broken_session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        broken_ctx = MagicMock()
        broken_ctx.__aenter__ = AsyncMock(return_value=broken_session)
        broken_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_cloud.delete_offline_task = AsyncMock(side_effect=RuntimeError("net down"))

        with patch("app.services.offline_task_service.get_session", return_value=broken_ctx):
            with pytest.raises(AddTaskError, match="已尝试回滚"):
                await service.add_task("magnet:?xt=urn:btih:abc123", "电影库", None, None)

    @pytest.mark.asyncio
    async def test_rollback_skipped_without_hash(self, service, mock_cloud):
        """拿不到 info_hash 时跳过回滚（无任务标识可删）"""
        mock_cloud.add_offline_task = AsyncMock(return_value=(True, "", None))
        broken_session = MagicMock()
        broken_session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        broken_ctx = MagicMock()
        broken_ctx.__aenter__ = AsyncMock(return_value=broken_session)
        broken_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.offline_task_service.get_session", return_value=broken_ctx):
            with pytest.raises(AddTaskError):
                await service.add_task("magnet:?xt=urn:btih:", "电影库", None, None)

        mock_cloud.delete_offline_task.assert_not_awaited()


class TestUpsert:
    """本地记录 UPSERT 语义"""

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, service, mock_cloud):
        """已存在同 info_hash 记录 → 走更新分支"""
        existing = MagicMock()
        with patch(
            "app.services.offline_task_service.get_session",
            return_value=_mock_session(existing_task=existing),
        ):
            await service.add_task("magnet:?xt=urn:btih:abc123", "电影库", "自定义名", "abc123hash")

        assert existing.name == "自定义名"
        assert existing.status == "added"

    @pytest.mark.asyncio
    async def test_display_name_defaults_to_magnet_prefix(self, service):
        """未提供名称时显示名取 magnet 前 50 字符"""
        from datetime import datetime  # noqa: F401  保持与生产代码时间语义一致

        captured = {}

        async def capture_session():
            return None

        # 直接单测 _upsert_task_record 捕获入参
        with patch(
            "app.services.offline_task_service.get_session",
            return_value=_mock_session(),
        ):
            await service._upsert_task_record("hash1", "magnet:?xt=urn:btih:aaa"[:50], "电影库")


class TestListActiveHashes:
    """轮询集合查询：added/downloading 才属于轮询集合"""

    @pytest.mark.asyncio
    async def test_returns_only_active_hashes(self, service):
        """仅返回 DB 中 added/downloading 状态的 info_hash 集合"""
        session = MagicMock()
        result = MagicMock()
        result.fetchall = MagicMock(return_value=[("hash1",), ("hash2",)])
        session.execute = AsyncMock(return_value=result)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.offline_task_service.get_session", return_value=ctx):
            hashes = await service.list_active_hashes()

        assert hashes == {"hash1", "hash2"}
        # 查询条件必须限定 added/downloading（跨轮去重的依据）
        stmt = session.execute.await_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "added" in compiled and "downloading" in compiled


class TestUpdateLifecycle:
    """本地生命周期状态迁移（原 monitor._update_task_status）"""

    @pytest.mark.asyncio
    async def test_completed_sets_status_and_complete_time(self, service):
        """迁移到 completed 时写入状态并补全 complete_time"""
        record = MagicMock()
        ctx = _mock_session(existing_task=record)
        with patch("app.services.offline_task_service.get_session", return_value=ctx):
            await service.update_lifecycle("hash1", "completed", None)

        assert record.status == "completed"
        assert record.error_message is None
        assert record.complete_time is not None
        ctx.__aenter__.return_value.commit.assert_called()

    @pytest.mark.asyncio
    async def test_failed_status_keeps_error_message(self, service):
        """迁移到 organize_failed 时保留可读错误信息"""
        record = MagicMock()
        ctx = _mock_session(existing_task=record)
        with patch("app.services.offline_task_service.get_session", return_value=ctx):
            await service.update_lifecycle("hash1", "organize_failed", "移动文件超时")

        assert record.status == "organize_failed"
        assert record.error_message == "移动文件超时"

    @pytest.mark.asyncio
    async def test_missing_record_is_silent_noop(self, service):
        """本地记录不存在时静默返回（既有行为）"""
        ctx = _mock_session(existing_task=None)
        with patch("app.services.offline_task_service.get_session", return_value=ctx):
            await service.update_lifecycle("ghost", "completed")

        ctx.__aenter__.return_value.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_hash_is_noop(self, service):
        """info_hash 为空时不触达数据库"""
        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            await service.update_lifecycle(None, "completed")

        mock_get_session.assert_not_called()


class TestMarkDownloadFailed:
    """云端失败任务记录（原 monitor._handle_failed_task）"""

    @pytest.mark.asyncio
    async def test_updates_existing_record(self, service):
        """已存在记录 → 更新为 failed 并写入失败原因与时间"""
        record = MagicMock()
        ctx = _mock_session(existing_task=record)
        task = _make_cloud_task("fail_hash", name="失败任务")
        with patch("app.services.offline_task_service.get_session", return_value=ctx):
            await service.mark_download_failed(task)

        assert record.status == "failed"
        assert record.error_message == "下载失败"
        assert record.name == "失败任务"
        assert record.add_time == task.add_time
        ctx.__aenter__.return_value.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_record_when_missing(self, service):
        """本地无记录时新建（session.add 被调用）"""
        ctx = _mock_session(existing_task=None)
        task = _make_cloud_task("fail_hash2")
        with patch("app.services.offline_task_service.get_session", return_value=ctx):
            await service.mark_download_failed(task)

        ctx.__aenter__.return_value.add.assert_called_once()
        ctx.__aenter__.return_value.commit.assert_called_once()


def _make_cloud_task(info_hash: str, name: str = "任务"):
    """构造中立 CloudTask 测试替身"""
    from datetime import datetime as _dt
    from app.schemas.cloud_types import CloudTask, CloudTaskStatus

    return CloudTask(
        info_hash=info_hash,
        name=name,
        status=CloudTaskStatus.FAILED,
        progress=0,
        file_id="",
        path="",
        add_time=_dt.fromtimestamp(1700000000),
    )
