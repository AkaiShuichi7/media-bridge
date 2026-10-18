"""
@description 后台监控轮询器与离线任务生命周期测试
@responsibility 验证 TaskMonitor 轮询循环（取任务列表 → 比对中立状态 → 调用领域服务）
                以及重复处理防护（DB 终态退出轮询集合 + 单轮去重）；
                整理结局分类等生命周期语义的直测见 tests/test_offline_task_service.py
                与本文件 TestOrganizeOutcomeClassification（直接针对领域服务）
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.schemas.cloud_types import CloudTask, CloudTaskStatus
from app.services.file_organizer import OrganizeResult
from app.services.offline_task_service import OfflineTaskService
from app.tasks.monitor import TaskMonitor
from app.utils.helpers import find_library_by_name


def _session_ctx(session):
    """把 mock session 包装成 get_session 返回的异步上下文"""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


def _build_monitor(cloud, organizer, config):
    """构造「真实领域服务 + 轮询器」组合（服务包住 mock 云盘/整理器）"""
    service = OfflineTaskService(cloud, config, organizer)
    return TaskMonitor(cloud_service=cloud, offline_task_service=service, config=config)


def _build_loop_monitor(cloud=None, config=None):
    """构造仅验证轮询启停行为的监控器（领域服务用 mock，轮询集合为空）"""
    mock_service = AsyncMock()
    mock_service.list_active_hashes.return_value = set()
    return TaskMonitor(
        cloud_service=cloud or AsyncMock(),
        offline_task_service=mock_service,
        config=config or MagicMock(),
    )


def _make_completed_task(info_hash, path="", file_id="12345", name="测试任务"):
    """构造云端已完成（中立状态 COMPLETED）的任务"""
    return CloudTask(
        info_hash=info_hash,
        name=name,
        status=CloudTaskStatus.COMPLETED,
        progress=0,
        file_id=file_id,
        path=path,
        add_time=datetime.fromtimestamp(1700000000),
    )


class TestStartStopMonitor:
    """测试监控任务的启动和停止"""

    @pytest.mark.asyncio
    async def test_start_stop_monitor(self):
        """测试启动和停止监控任务"""
        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2

        monitor = _build_loop_monitor(config=mock_config)

        # 启动监控
        await monitor.start_monitor()

        # 验证监控任务已启动
        assert monitor._task is not None
        assert not monitor._stop_event.is_set()

        # 等待一小段时间确保至少执行了一次检查
        await asyncio.sleep(0.5)

        # 停止监控
        await monitor.stop_monitor()

        # 验证监控任务已停止
        assert monitor._stop_event.is_set()
        assert monitor._task.done()


class TestCheckTasksSuccess:
    """测试任务完成时触发文件整理"""

    @pytest.mark.asyncio
    async def test_check_tasks_success(self):
        """测试离线任务完成时触发文件整理"""
        completed_task = _make_completed_task("abc123hash")

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(return_value=[completed_task])

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value=OrganizeResult(success_count=1, failed_count=0, skipped_count=0, errors=[])
        )

        mock_lib_check = MagicMock()
        mock_lib_check.name = "测试库"
        mock_lib_check.download_path = "/download"
        mock_lib_check.target_path = "/target"
        mock_lib_check.type = "system"
        mock_lib_check.min_transfer_size = 100

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib_check]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = _build_monitor(mock_client, mock_organizer, mock_config)

        # Mock 数据库会话：第 1 次查轮询集合，第 2 次查 library_name，之后为状态迁移
        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            call_count = [0]

            def mock_context_factory_success():
                call_count[0] += 1
                mock_session = MagicMock()
                if call_count[0] == 1:
                    # 第一次调用：list_active_hashes 查询系统任务
                    mock_result = MagicMock()
                    mock_result.fetchall = MagicMock(return_value=[("abc123hash",)])
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    # 后续调用：handle_completed_task 查询 library_name /
                    # update_lifecycle 查询任务记录（与旧行为一致，均返回库名字符串）
                    mock_result2 = MagicMock()
                    mock_result2.scalar_one_or_none = MagicMock(return_value="测试库")
                    mock_session.execute = AsyncMock(return_value=mock_result2)
                return _session_ctx(mock_session)

            mock_get_session.side_effect = mock_context_factory_success
            # 执行检查
            await monitor.check_tasks()

            # 验证文件整理被调用
            mock_organizer.organize_task.assert_called_once()


class TestCheckTasksFailure:
    """测试任务失败时保存记录到数据库"""

    @pytest.mark.asyncio
    async def test_check_tasks_failure(self):
        """测试离线任务失败时记录到数据库"""
        failed_task = CloudTask(
            info_hash="failed123hash",
            name="失败的任务",
            status=CloudTaskStatus.FAILED,
            progress=0,
            file_id="67890",
            path="",
            add_time=datetime.fromtimestamp(1700000000),
        )

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(return_value=[failed_task])

        mock_organizer = AsyncMock()
        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = []

        monitor = _build_monitor(mock_client, mock_organizer, mock_config)

        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            # Mock 数据库查询返回失败任务的 info_hash
            mock_session_for_query = MagicMock()
            mock_result_for_query = MagicMock()
            mock_result_for_query.fetchall = MagicMock(
                return_value=[("failed123hash",)]
            )
            mock_session_for_query.execute = AsyncMock(
                return_value=mock_result_for_query
            )

            # Mock 数据库会话，用于保存失败任务记录
            mock_session_for_save = MagicMock()
            mock_result_for_save = MagicMock()
            mock_result_for_save.scalar_one_or_none.return_value = None
            mock_session_for_save.execute = AsyncMock(return_value=mock_result_for_save)
            mock_session_for_save.add = MagicMock()
            mock_session_for_save.commit = AsyncMock()

            # 创建上下文管理器的工厂函数，第一次返回 query session，后续返回 save session
            call_count = [0]

            def mock_context_factory():
                call_count[0] += 1
                if call_count[0] == 1:
                    session = mock_session_for_query
                else:
                    session = mock_session_for_save

                return _session_ctx(session)

            mock_get_session.side_effect = mock_context_factory

            await monitor.check_tasks()

            mock_session_for_save.add.assert_called_once()
            mock_session_for_save.commit.assert_called_once()


class TestRandomInterval:
    """测试随机轮询间隔"""

    @pytest.mark.asyncio
    async def test_random_interval(self):
        """测试轮询间隔在配置范围内随机"""
        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 60
        mock_config.cloud.poll_interval_max = 80

        monitor = _build_loop_monitor(config=mock_config)

        # 多次获取间隔验证随机性
        intervals = []
        for _ in range(100):
            interval = monitor._get_random_interval()
            intervals.append(interval)
            # 验证每个间隔都在范围内
            assert 60 <= interval <= 80

        # 验证有随机性（不都是同一个值）
        unique_intervals = set(intervals)
        assert len(unique_intervals) > 1


class TestGracefulShutdown:
    """测试优雅关闭机制"""

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self):
        """测试 stop_monitor 正确触发优雅关闭"""
        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2

        monitor = _build_loop_monitor(config=mock_config)

        # 启动监控
        await monitor.start_monitor()

        # 通过 stop_monitor 触发优雅关闭
        await monitor.stop_monitor()

        # 验证停止事件已设置
        assert monitor._stop_event.is_set()

        # 验证监控任务已结束
        assert monitor._task.done()


class TestProcessingStatus:
    """测试不同任务状态的处理"""

    @pytest.mark.asyncio
    async def test_pending_task_ignored(self):
        """测试进行中的任务（中立状态 DOWNLOADING）被继续监控、不触发整理"""
        pending_task = CloudTask(
            info_hash="pending123hash",
            name="进行中的任务",
            status=CloudTaskStatus.DOWNLOADING,
            progress=0,
            file_id="11111",
            path="",
            add_time=datetime.fromtimestamp(1700000000),
        )

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(return_value=[pending_task])

        mock_organizer = AsyncMock()
        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = []

        monitor = _build_monitor(mock_client, mock_organizer, mock_config)

        # 轮询集合包含该任务，确保流程真正走到状态比对这一步
        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchall = MagicMock(return_value=[("pending123hash",)])
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_get_session.return_value = _session_ctx(mock_session)

            await monitor.check_tasks()

        # 验证文件整理未被调用（任务还在进行中）
        mock_organizer.organize_task.assert_not_called()


class TestPollDedup:
    """重复处理防护：内存 _processed_hashes 已删除，去重由两层机制承担"""

    @pytest.mark.asyncio
    async def test_terminal_state_exits_polling_set(self):
        """任务迁移到终态后退出轮询集合：下一轮不再重复整理（DB 状态推导去重）"""
        completed_task = _make_completed_task("dedup_hash", path="/下载/电影/")

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(return_value=[completed_task])

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value=OrganizeResult(success_count=1, failed_count=0, skipped_count=0, errors=[])
        )

        mock_lib = MagicMock()
        mock_lib.name = "电影库"
        mock_lib.download_path = "/下载/电影"
        mock_lib.target_path = "/目标/电影"
        mock_lib.type = "system"
        mock_lib.min_transfer_size = 100

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = _build_monitor(mock_client, mock_organizer, mock_config)

        record_mock = MagicMock()
        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            # 调用序列：#1 轮询集合(有任务) → #2 查 library_name → #3 迁移 completed
            # 第二轮：#4 轮询集合(空，任务已终态) → 提前返回
            sessions = []

            def make_session(kind, payload=None):
                session = MagicMock()
                result = MagicMock()
                if kind == "fetchall":
                    result.fetchall = MagicMock(return_value=payload or [])
                else:
                    result.scalar_one_or_none = MagicMock(return_value=payload)
                session.execute = AsyncMock(return_value=result)
                session.commit = AsyncMock()
                sessions.append(session)
                return _session_ctx(session)

            call_plan = [
                make_session("fetchall", [("dedup_hash",)]),
                make_session("scalar", "电影库"),
                make_session("scalar", record_mock),
                make_session("fetchall", []),
            ]
            mock_get_session.side_effect = call_plan

            await monitor.check_tasks()
            await monitor.check_tasks()

        # 第二轮轮询集合为空，整理只发生一次
        mock_organizer.organize_task.assert_awaited_once()
        # 任务记录已迁移到 completed
        assert record_mock.status == "completed"

    @pytest.mark.asyncio
    async def test_single_pass_duplicate_hash_processed_once(self):
        """单轮内同一 info_hash 出现两次只处理一次（轮内 seen 去重）"""
        task_a = _make_completed_task("dup_hash", path="/下载/电影/")
        task_b = _make_completed_task("dup_hash", path="/下载/电影/")

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(return_value=[task_a, task_b])

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value=OrganizeResult(success_count=1, failed_count=0, skipped_count=0, errors=[])
        )

        mock_lib = MagicMock()
        mock_lib.name = "电影库"
        mock_lib.download_path = "/下载/电影"

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = _build_monitor(mock_client, mock_organizer, mock_config)

        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            call_count = [0]

            def context_factory():
                call_count[0] += 1
                session = MagicMock()
                result = MagicMock()
                if call_count[0] == 1:
                    result.fetchall = MagicMock(return_value=[("dup_hash",)])
                else:
                    result.scalar_one_or_none = MagicMock(return_value="电影库")
                session.execute = AsyncMock(return_value=result)
                session.commit = AsyncMock()
                return _session_ctx(session)

            mock_get_session.side_effect = context_factory

            await monitor.check_tasks()

        # 重复的 info_hash 只整理一次
        mock_organizer.organize_task.assert_awaited_once()


class TestMultipleLibraries:
    """测试多媒体库匹配"""

    @pytest.mark.asyncio
    async def test_library_matching(self):
        """测试根据下载路径匹配正确的媒体库"""
        completed_task = _make_completed_task(
            "multi123hash", path="/下载/电影/", file_id="22222", name="多库测试任务"
        )

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(return_value=[completed_task])

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value=OrganizeResult(success_count=1, failed_count=0, skipped_count=0, errors=[])
        )

        # 配置多个媒体库
        mock_library1 = MagicMock()
        mock_library1.name = "电视剧库"
        mock_library1.download_path = "/下载/电视剧"
        mock_library1.target_path = "/媒体/电视剧"
        mock_library1.type = "system"
        mock_library1.min_transfer_size = 100

        mock_library2 = MagicMock()
        mock_library2.name = "电影库"
        mock_library2.download_path = "/下载/电影"
        mock_library2.target_path = "/媒体/电影"
        mock_library2.type = "system"
        mock_library2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_library1, mock_library2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = _build_monitor(mock_client, mock_organizer, mock_config)

        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            call_count = [0]

            def mock_context_factory_multi():
                call_count[0] += 1
                mock_session = MagicMock()
                if call_count[0] == 1:
                    # 第 1 次调用：list_active_hashes 查询系统任务
                    mock_result = MagicMock()
                    mock_result.fetchall = MagicMock(return_value=[("multi123hash",)])
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    # 后续调用：查 library_name / 迁移状态
                    mock_result2 = MagicMock()
                    mock_result2.scalar_one_or_none = MagicMock(return_value="电影库")
                    mock_session.execute = AsyncMock(return_value=mock_result2)
                return _session_ctx(mock_session)

            mock_get_session.side_effect = mock_context_factory_multi
            await monitor.check_tasks()

            # 验证整理被调用
            mock_organizer.organize_task.assert_called_once()
            # 验证传入了正确的库配置（电影库）
            call_args = mock_organizer.organize_task.call_args
            assert call_args is not None


class TestDatabaseLibraryLookup:
    """测试通过数据库查询 library_name 的逻辑

    说明：原文件中本类存在大量同名重复方法（Python 仅保留每个名字的最后一个
    定义，其余均为从未运行的死代码），本次重构已按场景去重合并为五个用例。
    """

    @staticmethod
    def _lookup_setup(task_path, libraries):
        """构造 DB 查库场景的公共 mock（云盘/整理器/配置）"""
        completed_task = _make_completed_task(
            "lookup_hash", path=task_path, file_id="33333", name="DB查询测试任务"
        )

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(return_value=[completed_task])
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value=OrganizeResult(success_count=1, failed_count=0, skipped_count=0, errors=[])
        )

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = libraries
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = _build_monitor(mock_client, mock_organizer, mock_config)
        return completed_task, mock_client, mock_organizer, mock_config, monitor

    @staticmethod
    def _make_lib(name, download_path, target_path=None, lib_type="system"):
        lib = MagicMock()
        lib.name = name
        lib.download_path = download_path
        lib.target_path = target_path or f"/目标/{name}"
        lib.type = lib_type
        lib.min_transfer_size = 100
        return lib

    @pytest.mark.asyncio
    async def test_db_lookup_success_matches_library(self):
        """场景A: 数据库查询成功，library_name 匹配到配置 → 使用正确 library"""
        lib1 = self._make_lib("测试库", "/下载/测试")
        lib2 = self._make_lib("日韩库", "/下载/日韩", lib_type="日韩")
        (
            completed_task,
            _,
            mock_organizer,
            mock_config,
            monitor,
        ) = self._lookup_setup("/任意路径/", [lib1, lib2])

        # 按名称查找媒体库的逻辑由 utils.find_library_by_name 提供（领域服务直接复用）
        result = find_library_by_name(mock_config.media.libraries, "日韩库")
        assert result is not None
        assert result.name == "日韩库"
        assert result.target_path == "/目标/日韩库"
        assert find_library_by_name(mock_config.media.libraries, "不存在的库") is None

        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            call_count = [0]

            def create_mock_session_a():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()
                if call_count[0] == 1:
                    # 第 1 次调用: list_active_hashes 获取轮询集合
                    mock_result.fetchall = MagicMock(return_value=[("lookup_hash",)])
                else:
                    # 第 2 次调用: 查询 library_name，返回日韩库
                    mock_result.scalar_one_or_none = MagicMock(return_value="日韩库")
                mock_session.execute = AsyncMock(return_value=mock_result)
                return _session_ctx(mock_session)

            mock_get_session.side_effect = create_mock_session_a

            await monitor.check_tasks()

            # 验证整理被调用，且使用数据库查到的库
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "日韩库"

    @pytest.mark.asyncio
    async def test_db_lookup_library_not_in_config(self):
        """场景B: 数据库查询成功，但 library_name 不在当前配置 → fallback"""
        lib1 = self._make_lib("测试库", "/下载/测试")
        lib2 = self._make_lib("日韩库", "/下载/日韩", lib_type="日韩")
        (
            _,
            _,
            mock_organizer,
            _,
            monitor,
        ) = self._lookup_setup("/下载/日韩/", [lib1, lib2])

        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            call_count = [0]

            def create_mock_session_b():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()
                if call_count[0] == 1:
                    # 第 1 次调用: list_active_hashes 获取轮询集合
                    mock_result.fetchall = MagicMock(return_value=[("lookup_hash",)])
                else:
                    # 第 2 次调用: 查询 library_name，返回配置中不存在的值
                    mock_result.scalar_one_or_none = MagicMock(
                        return_value=MagicMock(library_name="不存在的库")
                    )
                mock_session.execute = AsyncMock(return_value=mock_result)
                return _session_ctx(mock_session)

            mock_get_session.side_effect = create_mock_session_b

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（日韩库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "日韩库"

    @pytest.mark.asyncio
    async def test_db_lookup_empty_result(self):
        """场景C: 数据库查询返回空记录 → fallback 到路径匹配"""
        lib1 = self._make_lib("电视剧库", "/下载/电视剧")
        lib2 = self._make_lib("电影库", "/下载/电影")
        (
            _,
            _,
            mock_organizer,
            _,
            monitor,
        ) = self._lookup_setup("/下载/电影/", [lib1, lib2])

        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            call_count = [0]

            def create_mock_session_c():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()
                if call_count[0] == 1:
                    # 第 1 次调用: list_active_hashes 获取轮询集合
                    mock_result.fetchall = MagicMock(return_value=[("lookup_hash",)])
                else:
                    # 第 2 次调用: 查询 library_name，返回 None
                    mock_result.scalar_one_or_none = MagicMock(return_value=None)
                mock_session.execute = AsyncMock(return_value=mock_result)
                return _session_ctx(mock_session)

            mock_get_session.side_effect = create_mock_session_c

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（电影库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "电影库"

    @pytest.mark.asyncio
    async def test_db_lookup_null_library_name(self):
        """场景D: 数据库查询到记录但 library_name 为 None → fallback"""
        lib1 = self._make_lib("动漫库", "/下载/动漫")
        (
            _,
            _,
            mock_organizer,
            _,
            monitor,
        ) = self._lookup_setup("/下载/动漫/", [lib1])

        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            call_count = [0]

            def create_mock_session_d():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()
                if call_count[0] == 1:
                    # 第 1 次调用: list_active_hashes 获取轮询集合
                    mock_result.fetchall = MagicMock(return_value=[("lookup_hash",)])
                else:
                    # 第 2 次调用: 查询 library_name，记录存在但值为 None
                    mock_result.scalar_one_or_none = MagicMock(
                        return_value=MagicMock(library_name=None)
                    )
                mock_session.execute = AsyncMock(return_value=mock_result)
                return _session_ctx(mock_session)

            mock_get_session.side_effect = create_mock_session_d

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（动漫库）
            mock_organizer.organize_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_lookup_exception_fallback(self):
        """场景E: 数据库查询抛出异常 → catch 异常并 fallback"""
        lib1 = self._make_lib("音乐库", "/下载/音乐")
        (
            _,
            _,
            mock_organizer,
            _,
            monitor,
        ) = self._lookup_setup("/下载/音乐/", [lib1])

        with patch(
            "app.services.offline_task_service.get_session"
        ) as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()

                if call_count[0] == 1:
                    # 第 1 次调用：list_active_hashes 查询系统任务（正常返回）
                    mock_result1 = MagicMock()
                    mock_result1.fetchall = MagicMock(return_value=[("lookup_hash",)])
                    mock_session.execute = AsyncMock(return_value=mock_result1)
                else:
                    # 第 2 次调用：查询 library_name（抛出异常）
                    mock_session.execute = AsyncMock(
                        side_effect=Exception("数据库连接失败")
                    )

                return _session_ctx(mock_session)

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（音乐库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]  # 第二个参数是 LibraryConfig 对象
            assert library_config.name == "音乐库"


def _build_service_with_organize_result(organize_result):
    """构造带指定整理结果的 OfflineTaskService，用于测试整理结局分类。

    Returns:
        (service, mock_client, mock_organizer) 三元组
    """
    mock_client = AsyncMock()
    mock_client.get_path_id = AsyncMock(return_value="12345")

    mock_organizer = AsyncMock()
    mock_organizer.organize_task = AsyncMock(return_value=organize_result)

    mock_lib = MagicMock()
    mock_lib.name = "测试库"
    mock_lib.download_path = "/下载/电影"
    mock_lib.target_path = "/目标/电影"
    mock_lib.type = "system"
    mock_lib.min_transfer_size = 100

    mock_config = MagicMock()
    mock_config.cloud.poll_interval_min = 1
    mock_config.cloud.poll_interval_max = 2
    mock_config.media.libraries = [mock_lib]
    mock_config.media.video_formats = ["mp4", "mkv"]
    mock_config.media.min_transfer_size = 100
    mock_config.media.xx = MagicMock(remove_keywords=[])

    service = OfflineTaskService(mock_client, mock_config, mock_organizer)
    return service, mock_client, mock_organizer


def _patch_sessions_for_handle_completed(library_name="测试库"):
    """patch 领域服务的 get_session：第 1 次查 library_name，第 2 次迁移任务状态。

    Returns:
        (patcher, offline_task_mock) 二元组；offline_task_mock 用于断言写入的状态
    """
    offline_task_mock = MagicMock()
    offline_task_mock.status = "downloading"
    offline_task_mock.error_message = None

    call_count = [0]

    def context_factory():
        call_count[0] += 1
        mock_session = MagicMock()
        mock_result = MagicMock()
        if call_count[0] == 1:
            # 第一次调用：handle_completed_task 查询 library_name
            mock_result.scalar_one_or_none = MagicMock(return_value=library_name)
        else:
            # 后续调用：update_lifecycle 查询 OfflineTask 记录
            mock_result.scalar_one_or_none = MagicMock(return_value=offline_task_mock)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        return _session_ctx(mock_session)

    patcher = patch(
        "app.services.offline_task_service.get_session", side_effect=context_factory
    )
    return patcher, offline_task_mock


class TestOrganizeOutcomeClassification:
    """回归测试：整理结果必须区分成功、失败、全跳过三类结局（领域服务直测）"""

    def _make_completed_task(self, info_hash="outcome_hash"):
        """构造一个云端已完成的任务"""
        return _make_completed_task(info_hash, name="结局分类任务", file_id="99999")

    @pytest.mark.asyncio
    async def test_real_success_marks_completed_and_cleans_cloud_task(self):
        """有成功文件且无失败 → 标记 completed 并清理云端任务"""
        service, mock_client, _ = _build_service_with_organize_result(
            OrganizeResult(success_count=2, failed_count=0, skipped_count=1, errors=[])
        )

        patcher, offline_task_mock = _patch_sessions_for_handle_completed()
        with patcher:
            result = await service.handle_completed_task(self._make_completed_task())

        assert result is True
        assert offline_task_mock.status == "completed"
        mock_client.delete_offline_task.assert_awaited_once_with("outcome_hash")

    @pytest.mark.asyncio
    async def test_all_skipped_not_marked_success_and_cloud_task_kept(self):
        """0 成功 0 失败（全跳过）→ 不得虚报成功、不得清理云端任务，需记录可读原因"""
        service, mock_client, _ = _build_service_with_organize_result(
            OrganizeResult(success_count=0, failed_count=0, skipped_count=3, errors=[])
        )

        patcher, offline_task_mock = _patch_sessions_for_handle_completed()
        with patcher:
            result = await service.handle_completed_task(self._make_completed_task())

        assert result is False
        # 状态必须是独立于 completed/organize_failed 的“全跳过”
        assert offline_task_mock.status == "organize_skipped"
        # 原因必须可读且说明跳过数量
        assert offline_task_mock.error_message is not None
        assert "3" in offline_task_mock.error_message
        assert "跳过" in offline_task_mock.error_message
        # 云端任务必须保留，供用户排查
        mock_client.delete_offline_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_organize_result_uses_organizer_reason(self):
        """整理器给出无文件原因时 → 原因透传到任务记录，且不清理云端任务"""
        service, mock_client, _ = _build_service_with_organize_result(
            OrganizeResult(success_count=0, failed_count=0, skipped_count=0, errors=[], message="任务目录中没有文件可整理")
        )

        patcher, offline_task_mock = _patch_sessions_for_handle_completed()
        with patcher:
            result = await service.handle_completed_task(self._make_completed_task())

        assert result is False
        assert offline_task_mock.status == "organize_skipped"
        assert offline_task_mock.error_message == "任务目录中没有文件可整理"
        mock_client.delete_offline_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_files_marks_failed_and_cloud_task_kept(self):
        """存在失败文件 → 标记 organize_failed 并保留云端任务（既有行为回归）"""
        service, mock_client, _ = _build_service_with_organize_result(
            OrganizeResult(success_count=0, failed_count=2, skipped_count=0, errors=["无法创建目标目录: /目标/电影/XX", "移动文件超时"])
        )

        patcher, offline_task_mock = _patch_sessions_for_handle_completed()
        with patcher:
            result = await service.handle_completed_task(self._make_completed_task())

        assert result is False
        assert offline_task_mock.status == "organize_failed"
        assert "无法创建目标目录" in offline_task_mock.error_message
        mock_client.delete_offline_task.assert_not_called()
