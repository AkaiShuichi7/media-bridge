"""
@description 文件整理服务测试用例
@responsibility 验证整理任务的零结果路径携带可读原因，供监控层区分“全跳过”结局
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.cloud_types import CloudFile
from app.services.file_organizer import FileOrganizer


def _make_configs(library_type="system", min_transfer_size=100):
    """构造整理所需的库配置与媒体配置 mock。

    Returns:
        (library_config, media_config) 二元组
    """
    library_config = MagicMock()
    library_config.name = "测试库"
    library_config.target_path = "/目标/电影"
    library_config.type = library_type
    library_config.min_transfer_size = min_transfer_size

    media_config = MagicMock()
    media_config.video_formats = ["mp4", "mkv"]
    media_config.min_transfer_size = min_transfer_size
    return library_config, media_config


def _make_task_info():
    """构造最小的任务信息字典"""
    return {
        "task_id": "org_test_hash",
        "info_hash": "org_test_hash",
        "name": "整理测试任务",
        "path_id": "88888",
        "download_path_id": "",
    }


class TestOrganizeTaskZeroResultReason:
    """回归测试：0 成功 0 失败的提前返回必须携带可读原因"""

    @pytest.mark.asyncio
    async def test_no_files_returns_zero_with_reason(self):
        """任务目录为空 → 结果全 0 且 message 说明无文件可整理"""
        mock_client = AsyncMock()
        mock_client.list_files = AsyncMock(return_value=[])
        organizer = FileOrganizer(mock_client)

        library_config, media_config = _make_configs()
        result = await organizer.organize_task(
            _make_task_info(), library_config, media_config, None
        )

        assert result["success_count"] == 0
        assert result["failed_count"] == 0
        assert result["skipped_count"] == 0
        assert result["message"]
        assert "没有文件" in result["message"]

    @pytest.mark.asyncio
    async def test_no_video_files_returns_zero_with_reason(self):
        """目录只有非视频文件 → 结果全 0 且 message 说明无符合条件的视频文件"""
        text_file = CloudFile(
            file_id="f1",
            name="说明文档.txt",
            size=1024,
            parent_id="88888",
            is_directory=False,
        )
        mock_client = AsyncMock()
        mock_client.list_files = AsyncMock(return_value=[text_file])
        organizer = FileOrganizer(mock_client)

        library_config, media_config = _make_configs()
        result = await organizer.organize_task(
            _make_task_info(), library_config, media_config, None
        )

        assert result["success_count"] == 0
        assert result["failed_count"] == 0
        assert result["message"]
        assert "无符合条件的视频文件" in result["message"]

    @pytest.mark.asyncio
    async def test_unknown_library_type_returns_zero_with_reason(self):
        """未知媒体库类型 → 结果全 0 且 message 说明类型不支持"""
        video_file = CloudFile(
            file_id="f2",
            name="movie.mp4",
            size=200 * 1024 * 1024,
            parent_id="88888",
            is_directory=False,
        )
        mock_client = AsyncMock()
        mock_client.list_files = AsyncMock(return_value=[video_file])
        organizer = FileOrganizer(mock_client)

        library_config, media_config = _make_configs(library_type="unknown-type")
        result = await organizer.organize_task(
            _make_task_info(), library_config, media_config, None
        )

        assert result["success_count"] == 0
        assert result["failed_count"] == 0
        assert result["message"]
        assert "未知的媒体库类型" in result["message"]
