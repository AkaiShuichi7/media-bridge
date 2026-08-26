"""
@description 后台监控任务测试用例
@responsibility 验证监控任务的启动、停止、任务检查和优雅关闭功能
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from datetime import datetime

import pytest
from app.schemas.cloud_types import CloudTask


class TestStartStopMonitor:
    """测试监控任务的启动和停止"""

    @pytest.mark.asyncio
    async def test_start_stop_monitor(self):
        """测试启动和停止监控任务"""
        from app.tasks.monitor import TaskMonitor

        # 创建 Mock 依赖
        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[]
                )

        mock_organizer = AsyncMock()
        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.cloud.poll_interval_max = 2
        mock_config.cloud.poll_interval_min = 1

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

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
        from app.tasks.monitor import TaskMonitor

        # 模拟已完成的任务（status == 2）
        completed_task = CloudTask(info_hash="abc123hash", name="测试任务", status=2, progress=0, file_id="12345", path="", add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_lib_check = MagicMock()
        mock_lib_check.name = "测试库"
        mock_lib_check.download_path = "/download"
        mock_lib_check.target_path = "/target"
        mock_lib_check.type = "system"
        mock_lib_check.min_transfer_size = 100
        mock_config.media.libraries = [mock_lib_check]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        # Mock 数据库查询，返回系统任务的 info_hash
        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def mock_context_factory_success():
                call_count[0] += 1
                mock_session = MagicMock()
                if call_count[0] == 1:
                    # 第一次调用：check_tasks 查询系统任务
                    mock_result = MagicMock()
                    mock_result.fetchall = MagicMock(return_value=[("abc123hash",)])
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    # 第二次调用：_handle_completed_task 查询 library_name
                    mock_result2 = MagicMock()
                    mock_result2.scalar_one_or_none = MagicMock(return_value="测试库")
                    mock_session.execute = AsyncMock(return_value=mock_result2)
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

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
        from app.tasks.monitor import TaskMonitor

        # 模拟失败的任务（status == 1）
        failed_task = CloudTask(info_hash="failed123hash", name="失败的任务", status=-1, progress=0, file_id="67890", path="", add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[failed_task]
                )

        mock_organizer = AsyncMock()
        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = []

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
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

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = mock_context_factory

            await monitor.check_tasks()

            mock_session_for_save.add.assert_called_once()
            mock_session_for_save.commit.assert_called_once()


class TestRandomInterval:
    """测试随机轮询间隔"""

    @pytest.mark.asyncio
    async def test_random_interval(self):
        """测试轮询间隔在配置范围内随机"""
        from app.tasks.monitor import TaskMonitor

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[]
                )

        mock_organizer = AsyncMock()
        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 60
        mock_config.cloud.poll_interval_max = 80
        mock_config.cloud.poll_interval_min = 60
        mock_config.cloud.poll_interval_max = 80

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

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
        from app.tasks.monitor import TaskMonitor

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[]
                )

        mock_organizer = AsyncMock()
        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

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
        """测试进行中的任务（status == 0）被继续监控"""
        from app.tasks.monitor import TaskMonitor

        # 模拟进行中的任务
        pending_task = CloudTask(info_hash="pending123hash", name="进行中的任务", status=0, progress=0, file_id="11111", path="", add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[pending_task]
                )

        mock_organizer = AsyncMock()
        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = []

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        await monitor.check_tasks()

        # 验证文件整理未被调用（任务还在进行中）
        mock_organizer.organize_task.assert_not_called()


class TestMultipleLibraries:
    """测试多媒体库匹配"""

    @pytest.mark.asyncio
    async def test_library_matching(self):
        """测试根据下载路径匹配正确的媒体库"""
        from app.tasks.monitor import TaskMonitor

        # 模拟已完成的任务
        completed_task = CloudTask(info_hash="multi123hash", name="多库测试任务", status=2, progress=0, file_id="22222", path="/下载/电影/",  # 匹配第二个库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
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
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_library1, mock_library2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            # Mock 数据库查询返回多库测试任务的 info_hash
            call_count = [0]

            def mock_context_factory_multi():
                call_count[0] += 1
                mock_session = MagicMock()
                if call_count[0] == 1:
                    mock_result = MagicMock()
                    mock_result.fetchall = MagicMock(return_value=[("multi123hash",)])
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    mock_result2 = MagicMock()
                    mock_result2.scalar_one_or_none = MagicMock(return_value="电影库")
                    mock_session.execute = AsyncMock(return_value=mock_result2)
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = mock_context_factory_multi
            await monitor.check_tasks()

            # 验证整理被调用
            mock_organizer.organize_task.assert_called_once()
            # 验证传入了正确的库配置（电影库）
            call_args = mock_organizer.organize_task.call_args
            assert call_args is not None


class TestDatabaseLibraryLookup:
    """测试通过数据库查询 library_name 的逻辑"""

    @pytest.mark.asyncio
    async def test_db_lookup_success_matches_library(self):
        """场景A: 数据库查询成功，library_name 匹配到配置 → 使用正确 library"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash123abc", name="DB查询测试任务", status=2, progress=0, file_id="33333", path="/任意路径/",  # 即使路径不匹配，也应该用数据库中的 library_name
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        # 直接设置 MagicMock 属性（configure() 不适用于 MagicMock）
        mock_lib1 = MagicMock()
        mock_lib1.name = "测试库"
        mock_lib1.download_path = "/下载/测试"
        mock_lib1.target_path = "/目标/测试"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "日韩库"
        mock_lib2.download_path = "/下载/日韩"
        mock_lib2.target_path = "/目标/日韩"
        mock_lib2.type = "日韩"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        # 测试 _find_library_by_name 方法
        result = monitor._find_library_by_name("日韩库")
        assert result is not None
        assert result.name == "日韩库"
        assert result.target_path == "/目标/日韩"

        # 测试数据库查询逻辑 - 直接调用 _handle_completed_task
        with patch("app.tasks.monitor.get_session") as mock_get_session:
            # 模拟数据库返回
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = "日韩库"
            mock_session.execute = AsyncMock(return_value=mock_result)

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_ctx

            await monitor._handle_completed_task(completed_task)

            # 验证整理被调用
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "日韩库"

    @pytest.mark.asyncio
    async def test_db_lookup_library_not_in_config(self):
        """场景B: 数据库查询成功，但 library_name 不在当前配置 → fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash456def", name="配置不存在的库", status=2, progress=0, file_id="44444", path="/下载/日韩/",  # 这个路径匹配第二个库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "测试库"
        mock_lib1.download_path = "/下载/测试"
        mock_lib1.target_path = "/目标/测试"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "日韩库"
        mock_lib2.download_path = "/下载/日韩"
        mock_lib2.target_path = "/目标/日韩"
        mock_lib2.type = "日韩"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        # 测试 _find_library_by_name 返回 None 对于不存在的库
        result = monitor._find_library_by_name("不存在的库")
        assert result is None

        # 测试数据库查询返回不存在的库名，fallback 到路径匹配
        with patch("app.tasks.monitor.get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = "不存在的库"
            mock_session.execute.return_value = mock_result

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_ctx

            await monitor._handle_completed_task(completed_task)

            # 应该 fallback 到路径匹配（日韩库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "日韩库"

    @pytest.mark.asyncio
    async def test_db_lookup_empty_result(self):
        """场景C: 数据库查询返回空记录 → fallback 到路径匹配"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash789ghi", name="无记录任务", status=2, progress=0, file_id="55555", path="/下载/电影/",  # 匹配电影库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.configure(
            name="电影库",
            download_path="/下载/电影",
            target_path="/目标/电影",
            type="system",
            min_transfer_size=200,
        )

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        # 测试数据库返回 None，fallback 到路径匹配
        with patch("app.tasks.monitor.get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_ctx

            await monitor._handle_completed_task(completed_task)

            # 应该 fallback 到路径匹配（电影库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "电影库"

    @pytest.mark.asyncio
    async def test_db_lookup_null_library_name(self):
        """场景D: 数据库查询到记录但 library_name 为 None → fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash000null", name="空库名任务", status=2, progress=0, file_id="66666", path="/下载/动漫/",  # 匹配动漫库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.configure(
            name="动漫库",
            download_path="/下载/动漫",
            target_path="/目标/动漫",
            type="system",
            min_transfer_size=100,
        )

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        # 测试数据库返回 None，fallback 到路径匹配
        with patch("app.tasks.monitor.get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_ctx

            await monitor._handle_completed_task(completed_task)

            # 应该 fallback 到路径匹配（动漫库）
            mock_organizer.organize_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_lookup_exception_fallback(self):
        """场景E: 数据库查询抛出异常 → catch 异常并 fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hij789exception", name="异常测试任务", status=2, progress=0, file_id="77777", path="/下载/音乐/",  # 匹配音乐库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.configure(
            name="音乐库",
            download_path="/下载/音乐",
            target_path="/目标/音乐",
            type="system",
            min_transfer_size=100,
        )

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            mock_session = MagicMock()
            # 数据库查询抛出异常
            mock_session.execute.side_effect = Exception("数据库连接失败")

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_ctx

            await monitor._handle_completed_task(completed_task)

            # 应该 fallback 到路径匹配（音乐库）
            mock_organizer.organize_task.assert_called_once()
            # 验证使用的是日韩库（从数据库查询到的）
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]  # 第二个参数是 LibraryConfig 对象
            assert library_config.name == "日韩库"
            assert library_config.target_path == "/目标/日韩"

    @pytest.mark.asyncio
    async def test_db_lookup_library_not_in_config(self):
        """场景B: 数据库查询成功，但 library_name 不在当前配置 → fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash456def", name="配置不存在的库", status=2, progress=0, file_id="44444", path="/下载/日韩/",  # 这个路径匹配第二个库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "测试库"
        mock_lib1.download_path = "/下载/测试"
        mock_lib1.target_path = "/目标/测试"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "日韩库"
        mock_lib2.download_path = "/下载/日韩"
        mock_lib2.target_path = "/目标/日韩"
        mock_lib2.type = "日韩"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        # 准备多次 get_session 调用的返回值
        session_results = []

        # 第一次调用：check_tasks 查询系统任务
        mock_result1 = MagicMock()
        mock_result1.fetchall.return_value = [("hash456def",)]
        session_results.append(mock_result1)

        # 第二次调用：数据库返回的 library_name 在当前配置中不存在
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = "不存在的库"
        session_results.append(mock_result2)

        def mock_get_session():
            if not session_results:
                return None
            mock_session = MagicMock()
            mock_session.execute.return_value = session_results.pop(0)
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            return mock_ctx

        with patch("app.tasks.monitor.get_session", side_effect=mock_get_session):
            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（日韩库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "日韩库"

    @pytest.mark.asyncio
    async def test_db_lookup_empty_result(self):
        """场景C: 数据库查询返回空记录 → fallback 到路径匹配"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash789ghi", name="无记录任务", status=2, progress=0, file_id="55555", path="/下载/电影/",  # 匹配电影库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "电视剧库"
        mock_lib1.download_path = "/下载/电视剧"
        mock_lib1.target_path = "/目标/电视剧"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "电影库"
        mock_lib2.download_path = "/下载/电影"
        mock_lib2.target_path = "/目标/电影"
        mock_lib2.type = "system"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        # 准备多次 get_session 调用的返回值
        session_results = []

        # 第一次调用：check_tasks 查询系统任务
        mock_result1 = MagicMock()
        mock_result1.fetchall.return_value = [("hash789ghi",)]
        session_results.append(mock_result1)

        # 第二次调用：数据库返回 None（无此记录）
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = None
        session_results.append(mock_result2)

        def mock_get_session():
            if not session_results:
                return None
            mock_session = MagicMock()
            mock_session.execute.return_value = session_results.pop(0)
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            return mock_ctx

        with patch("app.tasks.monitor.get_session", side_effect=mock_get_session):
            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（电影库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "电影库"

    @pytest.mark.asyncio
    async def test_db_lookup_null_library_name(self):
        """场景D: 数据库查询到记录但 library_name 为 None → fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash000null", name="空库名任务", status=2, progress=0, file_id="66666", path="/下载/动漫/",  # 匹配动漫库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "动漫库"
        mock_lib1.download_path = "/下载/动漫"
        mock_lib1.target_path = "/目标/动漫"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        # 准备多次 get_session 调用的返回值
        session_results = []

        # 第一次调用：check_tasks 查询系统任务
        mock_result1 = MagicMock()
        mock_result1.fetchall.return_value = [("hash000null",)]
        session_results.append(mock_result1)

        # 第二次调用：数据库返回的 library_name 为 None
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = None
        session_results.append(mock_result2)

        def mock_get_session():
            if not session_results:
                return None
            mock_session = MagicMock()
            mock_session.execute.return_value = session_results.pop(0)
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            return mock_ctx

        with patch("app.tasks.monitor.get_session", side_effect=mock_get_session):
            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（动漫库）
            mock_organizer.organize_task.assert_called_once()
            # 验证使用的是日韩库（从数据库查询到的）
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]  # 第二个参数是 LibraryConfig 对象
            assert library_config.name == "日韩库"
            assert library_config.target_path == "/目标/日韩"

    @pytest.mark.asyncio
    async def test_db_lookup_library_not_in_config(self):
        """场景B: 数据库查询成功，但 library_name 不在当前配置 → fallback"""
        from app.tasks.monitor import TaskMonitor
        from unittest.mock import PropertyMock

        completed_task = CloudTask(info_hash="hash456def", name="配置不存在的库", status=2, progress=0, file_id="44444", path="/下载/日韩/",  # 这个路径匹配第二个库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "测试库"
        mock_lib1.download_path = "/下载/测试"
        mock_lib1.target_path = "/目标/测试"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "日韩库"
        mock_lib2.download_path = "/下载/日韩"
        mock_lib2.target_path = "/目标/日韩"
        mock_lib2.type = "日韩"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()

                if call_count[0] == 1:
                    # 第一次调用：check_tasks 查询系统任务
                    mock_result1 = MagicMock()
                    type(mock_result1).fetchall = PropertyMock(
                        return_value=[("hash456def",)]
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result1)
                else:
                    # 第二次调用：数据库返回的 library_name 在当前配置中不存在
                    mock_result2 = MagicMock()
                    type(mock_result2).scalar_one_or_none = PropertyMock(
                        return_value="不存在的库"
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result2)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（日韩库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "日韩库"

    @pytest.mark.asyncio
    async def test_db_lookup_empty_result(self):
        """场景C: 数据库查询返回空记录 → fallback 到路径匹配"""
        from app.tasks.monitor import TaskMonitor
        from unittest.mock import PropertyMock

        completed_task = CloudTask(info_hash="hash789ghi", name="无记录任务", status=2, progress=0, file_id="55555", path="/下载/电影/",  # 匹配电影库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "电视剧库"
        mock_lib1.download_path = "/下载/电视剧"
        mock_lib1.target_path = "/目标/电视剧"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "电影库"
        mock_lib2.download_path = "/下载/电影"
        mock_lib2.target_path = "/目标/电影"
        mock_lib2.type = "system"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()

                if call_count[0] == 1:
                    # 第一次调用：check_tasks 查询系统任务
                    mock_result1 = MagicMock()
                    type(mock_result1).fetchall = PropertyMock(
                        return_value=[("hash789ghi",)]
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result1)
                else:
                    # 第二次调用：数据库返回 None（无此记录）
                    mock_result2 = MagicMock()
                    type(mock_result2).scalar_one_or_none = PropertyMock(
                        return_value=None
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result2)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（电影库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "电影库"

    @pytest.mark.asyncio
    async def test_db_lookup_null_library_name(self):
        """场景D: 数据库查询到记录但 library_name 为 None → fallback"""
        from app.tasks.monitor import TaskMonitor
        from unittest.mock import PropertyMock

        completed_task = CloudTask(info_hash="hash000null", name="空库名任务", status=2, progress=0, file_id="66666", path="/下载/动漫/",  # 匹配动漫库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "动漫库"
        mock_lib1.download_path = "/下载/动漫"
        mock_lib1.target_path = "/目标/动漫"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()

                if call_count[0] == 1:
                    # 第一次调用：check_tasks 查询系统任务
                    mock_result1 = MagicMock()
                    type(mock_result1).fetchall = PropertyMock(
                        return_value=[("hash000null",)]
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result1)
                else:
                    # 第二次调用：数据库返回的 library_name 为 None
                    mock_result2 = MagicMock()
                    type(mock_result2).scalar_one_or_none = PropertyMock(
                        return_value=None
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result2)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（动漫库）
            mock_organizer.organize_task.assert_called_once()
            # 验证使用的是日韩库（从数据库查询到的）
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]  # 第二个参数是 LibraryConfig 对象
            assert library_config.name == "日韩库"
            assert library_config.target_path == "/目标/日韩"

    @pytest.mark.asyncio
    async def test_db_lookup_library_not_in_config(self):
        """场景B: 数据库查询成功，但 library_name 不在当前配置 → fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash456def", name="配置不存在的库", status=2, progress=0, file_id="44444", path="/下载/日韩/",  # 这个路径匹配第二个库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "测试库"
        mock_lib1.download_path = "/下载/测试"
        mock_lib1.target_path = "/目标/测试"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "日韩库"
        mock_lib2.download_path = "/下载/日韩"
        mock_lib2.target_path = "/目标/日韩"
        mock_lib2.type = "日韩"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()

                if call_count[0] == 1:
                    # 第一次调用：check_tasks 查询系统任务
                    mock_result1 = MagicMock()
                    mock_result1.fetchall = MagicMock(return_value=[("hash456def",)])
                    mock_session.execute = AsyncMock(return_value=mock_result1)
                else:
                    # 第二次调用：数据库返回的 library_name 在当前配置中不存在
                    mock_result2 = MagicMock()
                    mock_result2.scalar_one_or_none = MagicMock(
                        return_value="不存在的库"
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result2)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（日韩库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "日韩库"

    @pytest.mark.asyncio
    async def test_db_lookup_empty_result(self):
        """场景C: 数据库查询返回空记录 → fallback 到路径匹配"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash789ghi", name="无记录任务", status=2, progress=0, file_id="55555", path="/下载/电影/",  # 匹配电影库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "电视剧库"
        mock_lib1.download_path = "/下载/电视剧"
        mock_lib1.target_path = "/目标/电视剧"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "电影库"
        mock_lib2.download_path = "/下载/电影"
        mock_lib2.target_path = "/目标/电影"
        mock_lib2.type = "system"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()

                if call_count[0] == 1:
                    # 第一次调用：check_tasks 查询系统任务
                    mock_result1 = MagicMock()
                    mock_result1.fetchall = MagicMock(return_value=[("hash789ghi",)])
                    mock_session.execute = AsyncMock(return_value=mock_result1)
                else:
                    # 第二次调用：数据库返回 None（无此记录）
                    mock_result2 = MagicMock()
                    mock_result2.scalar_one_or_none = MagicMock(return_value=None)
                    mock_session.execute = AsyncMock(return_value=mock_result2)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（电影库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "电影库"

    @pytest.mark.asyncio
    async def test_db_lookup_null_library_name(self):
        """场景D: 数据库查询到记录但 library_name 为 None → fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash000null", name="空库名任务", status=2, progress=0, file_id="66666", path="/下载/动漫/",  # 匹配动漫库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "动漫库"
        mock_lib1.download_path = "/下载/动漫"
        mock_lib1.target_path = "/目标/动漫"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()

                if call_count[0] == 1:
                    # 第一次调用：check_tasks 查询系统任务
                    mock_result1 = MagicMock()
                    mock_result1.fetchall = MagicMock(return_value=[("hash000null",)])
                    mock_session.execute = AsyncMock(return_value=mock_result1)
                else:
                    # 第二次调用：数据库返回的 library_name 为 None
                    mock_result2 = MagicMock()
                    mock_result2.scalar_one_or_none = MagicMock(return_value=None)
                    mock_session.execute = AsyncMock(return_value=mock_result2)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（动漫库）
            mock_organizer.organize_task.assert_called_once()
            # 验证使用的是日韩库（从数据库查询到的）
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]  # 第二个参数是 LibraryConfig 对象
            assert library_config.name == "日韩库"
            assert library_config.target_path == "/目标/日韩"

    @pytest.mark.asyncio
    async def test_db_lookup_library_not_in_config(self):
        """场景B: 数据库查询成功，但 library_name 不在当前配置 → fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash456def", name="配置不存在的库", status=2, progress=0, file_id="44444", path="/下载/日韩/",  # 这个路径匹配第二个库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "测试库"
        mock_lib1.download_path = "/下载/测试"
        mock_lib1.target_path = "/目标/测试"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "日韩库"
        mock_lib2.download_path = "/下载/日韩"
        mock_lib2.target_path = "/目标/日韩"
        mock_lib2.type = "日韩"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()

                if call_count[0] == 1:
                    mock_result.fetchall = MagicMock(return_value=[("hash456def",)])
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    # 数据库返回的 library_name 在当前配置中不存在
                    mock_result.scalar_one_or_none = MagicMock(
                        return_value="不存在的库"
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（日韩库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "日韩库"

    @pytest.mark.asyncio
    async def test_db_lookup_empty_result(self):
        """场景C: 数据库查询返回空记录 → fallback 到路径匹配"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash789ghi", name="无记录任务", status=2, progress=0, file_id="55555", path="/下载/电影/",  # 匹配电影库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "电视剧库"
        mock_lib1.download_path = "/下载/电视剧"
        mock_lib1.target_path = "/目标/电视剧"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "电影库"
        mock_lib2.download_path = "/下载/电影"
        mock_lib2.target_path = "/目标/电影"
        mock_lib2.type = "system"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()

                if call_count[0] == 1:
                    mock_result.fetchall = MagicMock(return_value=[("hash789ghi",)])
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    # 数据库返回 None（无此记录）
                    mock_result.scalar_one_or_none = MagicMock(return_value=None)
                    mock_session.execute = AsyncMock(return_value=mock_result)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（电影库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "电影库"

    @pytest.mark.asyncio
    async def test_db_lookup_null_library_name(self):
        """场景D: 数据库查询到记录但 library_name 为 None → fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash000null", name="空库名任务", status=2, progress=0, file_id="66666", path="/下载/动漫/",  # 匹配动漫库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "动漫库"
        mock_lib1.download_path = "/下载/动漫"
        mock_lib1.target_path = "/目标/动漫"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()

                if call_count[0] == 1:
                    mock_result.fetchall = MagicMock(return_value=[("hash000null",)])
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    # 数据库返回的 library_name 为 None
                    mock_result.scalar_one_or_none = MagicMock(return_value=None)
                    mock_session.execute = AsyncMock(return_value=mock_result)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（动漫库）
            mock_organizer.organize_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_lookup_exception_fallback(self):
        """场景E: 数据库查询抛出异常 → catch 异常并 fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hij789exception", name="异常测试任务", status=2, progress=0, file_id="77777", path="/下载/音乐/",  # 匹配音乐库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "音乐库"
        mock_lib1.download_path = "/下载/音乐"
        mock_lib1.target_path = "/目标/音乐"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()

                if call_count[0] == 1:
                    mock_result.fetchall = MagicMock(
                        return_value=[("hij789exception",)]
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    # 第二次调用抛出异常（在 _handle_completed_task 中）
                    mock_result.scalar_one_or_none = MagicMock(
                        side_effect=Exception("数据库连接失败")
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（音乐库）
            mock_organizer.organize_task.assert_called_once()
            # 验证使用的是日韩库（从数据库查询到的）
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]  # 第二个参数是 LibraryConfig 对象
            assert library_config.name == "日韩库"
            assert library_config.target_path == "/目标/日韩"

    @pytest.mark.asyncio
    async def test_db_lookup_library_not_in_config(self):
        """场景B: 数据库查询成功，但 library_name 不在当前配置 → fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash456def", name="配置不存在的库", status=2, progress=0, file_id="44444", path="/下载/日韩/",  # 这个路径匹配第二个库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "测试库"
        mock_lib1.download_path = "/下载/测试"
        mock_lib1.target_path = "/目标/测试"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "日韩库"
        mock_lib2.download_path = "/下载/日韩"
        mock_lib2.target_path = "/目标/日韩"
        mock_lib2.type = "日韩"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()

                if call_count[0] == 1:
                    mock_result.fetchall = MagicMock(return_value=[("hash456def",)])
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    # 数据库返回的 library_name 在当前配置中不存在
                    mock_result.scalar_one_or_none = MagicMock(
                        return_value=MagicMock(library_name="不存在的库")
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（日韩库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "日韩库"

    @pytest.mark.asyncio
    async def test_db_lookup_empty_result(self):
        """场景C: 数据库查询返回空记录 → fallback 到路径匹配"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash789ghi", name="无记录任务", status=2, progress=0, file_id="55555", path="/下载/电影/",  # 匹配电影库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "电视剧库"
        mock_lib1.download_path = "/下载/电视剧"
        mock_lib1.target_path = "/目标/电视剧"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "电影库"
        mock_lib2.download_path = "/下载/电影"
        mock_lib2.target_path = "/目标/电影"
        mock_lib2.type = "system"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()

                if call_count[0] == 1:
                    mock_result.fetchall = MagicMock(return_value=[("hash789ghi",)])
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    # 数据库返回 None（无此记录）
                    mock_result.scalar_one_or_none = MagicMock(return_value=None)
                    mock_session.execute = AsyncMock(return_value=mock_result)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（电影库）
            mock_organizer.organize_task.assert_called_once()
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]
            assert library_config.name == "电影库"

    @pytest.mark.asyncio
    async def test_db_lookup_null_library_name(self):
        """场景D: 数据库查询到记录但 library_name 为 None → fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash000null", name="空库名任务", status=2, progress=0, file_id="66666", path="/下载/动漫/",  # 匹配动漫库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "动漫库"
        mock_lib1.download_path = "/下载/动漫"
        mock_lib1.target_path = "/目标/动漫"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()

                if call_count[0] == 1:
                    mock_result.fetchall = MagicMock(return_value=[("hash000null",)])
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    # 数据库返回的 library_name 为 None
                    mock_result.scalar_one_or_none = MagicMock(
                        return_value=MagicMock(library_name=None)
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result)

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（动漫库）
            mock_organizer.organize_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_lookup_exception_fallback(self):
        """场景E: 数据库查询抛出异常 → catch 异常并 fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hij789exception", name="异常测试任务", status=2, progress=0, file_id="77777", path="/下载/音乐/",  # 匹配音乐库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "音乐库"
        mock_lib1.download_path = "/下载/音乐"
        mock_lib1.target_path = "/目标/音乐"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()

                if call_count[0] == 1:
                    mock_result.fetchall = MagicMock(
                        return_value=[("hij789exception",)]
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result)
                else:
                    # 第二次调用抛出异常
                    mock_session.execute = AsyncMock(
                        side_effect=Exception("数据库连接失败")
                    )

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（音乐库）
            mock_organizer.organize_task.assert_called_once()
            # 验证使用的是日韩库（从数据库查询到的）
            call_args = mock_organizer.organize_task.call_args
            library_config = call_args[0][1]  # 第二个参数是 LibraryConfig 对象
            assert library_config.name == "日韩库"
            assert library_config.target_path == "/目标/日韩"

    @pytest.mark.asyncio
    async def test_db_lookup_library_not_in_config(self):
        """场景B: 数据库查询成功，但 library_name 不在当前配置 → fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash456def", name="配置不存在的库", status=2, progress=0, file_id="44444", path="/下载/日韩/",  # 这个路径匹配第二个库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "测试库"
        mock_lib1.download_path = "/下载/测试"
        mock_lib1.target_path = "/目标/测试"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "日韩库"
        mock_lib2.download_path = "/下载/日韩"
        mock_lib2.target_path = "/目标/日韩"
        mock_lib2.type = "日韩"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = 0

            def create_mock_session_b():
                nonlocal call_count
                call_count += 1
                mock_session = MagicMock()
                mock_result = MagicMock()
                if call_count == 1:
                    # 第1次调用: check_tasks 获取 system_hashes
                    mock_result.fetchall = MagicMock(return_value=[("hash456def",)])
                else:
                    # 第2次调用: _handle_completed_task 查询 library_name
                    mock_result.scalar_one_or_none = MagicMock(
                        return_value=MagicMock(library_name="不存在的库")
                    )
                mock_session.execute = AsyncMock(return_value=mock_result)
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

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
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash789ghi", name="无记录任务", status=2, progress=0, file_id="55555", path="/下载/电影/",  # 匹配电影库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "电视剧库"
        mock_lib1.download_path = "/下载/电视剧"
        mock_lib1.target_path = "/目标/电视剧"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_lib2 = MagicMock()
        mock_lib2.name = "电影库"
        mock_lib2.download_path = "/下载/电影"
        mock_lib2.target_path = "/目标/电影"
        mock_lib2.type = "system"
        mock_lib2.min_transfer_size = 200

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1, mock_lib2]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count_c = [0]

            def create_mock_session_c():
                call_count_c[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()
                if call_count_c[0] == 1:
                    # 第1次调用: check_tasks 获取 system_hashes
                    mock_result.fetchall = MagicMock(return_value=[("hash789ghi",)])
                else:
                    # 第2次调用: _handle_completed_task 查询 library_name，返回 None
                    mock_result.scalar_one_or_none = MagicMock(return_value=None)
                mock_session.execute = AsyncMock(return_value=mock_result)
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

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
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hash000null", name="空库名任务", status=2, progress=0, file_id="66666", path="/下载/动漫/",  # 匹配动漫库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "动漫库"
        mock_lib1.download_path = "/下载/动漫"
        mock_lib1.target_path = "/目标/动漫"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count_d = [0]

            def create_mock_session_d():
                call_count_d[0] += 1
                mock_session = MagicMock()
                mock_result = MagicMock()
                if call_count_d[0] == 1:
                    # 第1次调用: check_tasks 获取 system_hashes
                    mock_result.fetchall = MagicMock(return_value=[("hash000null",)])
                else:
                    # 第2次调用: _handle_completed_task 查询 library_name，返回 library_name=None
                    mock_result.scalar_one_or_none = MagicMock(
                        return_value=MagicMock(library_name=None)
                    )
                mock_session.execute = AsyncMock(return_value=mock_result)
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session_d

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（动漫库）
            mock_organizer.organize_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_lookup_exception_fallback(self):
        """场景E: 数据库查询抛出异常 → catch 异常并 fallback"""
        from app.tasks.monitor import TaskMonitor

        completed_task = CloudTask(info_hash="hij789exception", name="异常测试任务", status=2, progress=0, file_id="77777", path="/下载/音乐/",  # 匹配音乐库
            add_time=datetime.fromtimestamp(1700000000))

        mock_client = AsyncMock()
        mock_client.get_offline_tasks = AsyncMock(
                    return_value=[completed_task]
                )
        mock_client.get_path_id = AsyncMock(return_value="12345")

        mock_organizer = AsyncMock()
        mock_organizer.organize_task = AsyncMock(
            return_value={
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "errors": [],
            }
        )

        mock_lib1 = MagicMock()
        mock_lib1.name = "音乐库"
        mock_lib1.download_path = "/下载/音乐"
        mock_lib1.target_path = "/目标/音乐"
        mock_lib1.type = "system"
        mock_lib1.min_transfer_size = 100

        mock_config = MagicMock()
        mock_config.cloud.poll_interval_min = 1
        mock_config.cloud.poll_interval_max = 2
        mock_config.media.libraries = [mock_lib1]
        mock_config.media.video_formats = ["mp4", "mkv"]
        mock_config.media.min_transfer_size = 100
        mock_config.media.xx = MagicMock(remove_keywords=[])

        monitor = TaskMonitor(
            p115_client=mock_client,
            file_organizer=mock_organizer,
            config=mock_config,
        )

        with patch("app.tasks.monitor.get_session") as mock_get_session:
            call_count = [0]

            def create_mock_session():
                call_count[0] += 1
                mock_session = MagicMock()

                if call_count[0] == 1:
                    # 第一次调用：check_tasks 查询系统任务（正常返回）
                    mock_result1 = MagicMock()
                    mock_result1.fetchall = MagicMock(
                        return_value=[("hij789exception",)]
                    )
                    mock_session.execute = AsyncMock(return_value=mock_result1)
                else:
                    # 第二次调用：_handle_completed_task 查询 library_name（抛出异常）
                    mock_session.execute = AsyncMock(
                        side_effect=Exception("数据库连接失败")
                    )

                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                return mock_ctx

            mock_get_session.side_effect = create_mock_session

            await monitor.check_tasks()

            # 应该 fallback 到路径匹配（音乐库）
            mock_organizer.organize_task.assert_called_once()
