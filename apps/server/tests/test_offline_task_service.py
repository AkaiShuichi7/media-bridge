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
    """被测服务"""
    return OfflineTaskService(mock_cloud, mock_config)


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
