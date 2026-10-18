"""
@description p115_client 模块测试
@responsibility 验证 p115client 异步封装的核心功能
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.p115_client import P115Client


@pytest.mark.asyncio
async def test_client_direct_construction():
    """测试客户端直接构造（生命周期由 AppContainer 独占持有，无类级单例）"""
    with patch("app.services.p115_client.P115SyncClient") as mock_client_class:
        # 两次构造互不影响，各自持有独立实例
        client1 = P115Client("test_cookies_1")
        client2 = P115Client("test_cookies_1")

        assert client1 is not client2
        assert mock_client_class.call_count == 2


@pytest.mark.asyncio
async def test_add_offline_task():
    """测试添加离线任务成功"""
    with patch("app.services.p115_client.P115SyncClient") as mock_client_class:
        # 模拟 p115client 实例和方法
        mock_instance = MagicMock()
        mock_instance.clouddownload_task_add_url = MagicMock(
            return_value={"state": True, "info_hash": "abc123"}
        )
        mock_client_class.return_value = mock_instance

        client = P115Client("test_cookies")

        # 测试添加离线任务
        result = await client.add_offline_task("magnet:?xt=urn:btih:test", "dir_id_123")

        # 验证调用参数
        mock_instance.clouddownload_task_add_url.assert_called_once_with(
            {"url": "magnet:?xt=urn:btih:test", "wp_path_id": "dir_id_123"}
        )

        # 验证返回结果
        assert result["state"] is True
        assert result["info_hash"] == "abc123"


@pytest.mark.asyncio
async def test_retry_on_failure():
    """测试 API 调用失败自动重试"""
    with patch("app.services.p115_client.P115SyncClient") as mock_client_class:
        # 模拟 p115client 实例
        mock_instance = MagicMock()

        # 模拟前 2 次失败,第 3 次成功
        mock_instance.clouddownload_task_list = MagicMock(
            side_effect=[
                Exception("Network error"),
                Exception("Timeout"),
                {"state": True, "tasks": []},
            ]
        )
        mock_client_class.return_value = mock_instance

        client = P115Client("test_cookies")

        # 测试获取任务列表（应自动重试）
        result = await client.get_offline_tasks()

        # 验证调用 3 次
        assert mock_instance.clouddownload_task_list.call_count == 3

        # 验证最终返回成功结果
        assert result["state"] is True


@pytest.mark.asyncio
async def test_cookies_invalid():
    """测试 Cookies 无效检测"""
    with patch("app.services.p115_client.P115SyncClient") as mock_client_class:
        # 模拟 p115client 实例
        mock_instance = MagicMock()

        # 模拟 verify_cookies 返回失败
        mock_instance.user_info = MagicMock(
            return_value={"state": False, "error": "Invalid cookies"}
        )
        mock_client_class.return_value = mock_instance

        client = P115Client("test_cookies")

        # 测试验证 cookies
        result = await client.verify_cookies()

        # 验证返回失败
        assert result is False


# 清理单例状态（避免测试间干扰）
@pytest.fixture(autouse=True)
def reset_singleton():
    """每个测试后重置单例"""
    yield
    # 清理单例缓存
    if hasattr(P115Client, "_instance"):
        P115Client._instance = None
        P115Client._lock = asyncio.Lock()
