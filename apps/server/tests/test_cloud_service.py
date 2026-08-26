"""
@description CloudService 抽象基类测试
@responsibility 验证 CloudService ABC 的接口约束、P115CloudService 继承关系及基本可实例化性
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from abc import ABC

from app.services.cloud.base import CloudService
from app.services.cloud.p115 import P115CloudService


class TestCloudServiceABC:
    """测试 CloudService 抽象基类的接口约束"""

    def test_cloud_service_is_abstract(self):
        """CloudService 本身不可实例化"""
        with pytest.raises(TypeError):
            CloudService()  # type: ignore

    def test_cloud_service_is_abc(self):
        """CloudService 继承自 ABC"""
        assert issubclass(CloudService, ABC)

    def test_cloud_service_has_list_files(self):
        """CloudService 定义了 list_files 抽象方法"""
        assert hasattr(CloudService, "list_files")

    def test_cloud_service_has_move_file(self):
        """CloudService 定义了 move_file 抽象方法"""
        assert hasattr(CloudService, "move_file")

    def test_cloud_service_has_rename_file(self):
        """CloudService 定义了 rename_file 抽象方法"""
        assert hasattr(CloudService, "rename_file")

    def test_cloud_service_has_get_path_id(self):
        """CloudService 定义了 get_path_id 抽象方法"""
        assert hasattr(CloudService, "get_path_id")

    def test_cloud_service_has_add_offline_task(self):
        """CloudService 定义了 add_offline_task 抽象方法"""
        assert hasattr(CloudService, "add_offline_task")

    def test_cloud_service_has_get_offline_tasks(self):
        """CloudService 定义了 get_offline_tasks 抽象方法"""
        assert hasattr(CloudService, "get_offline_tasks")

    def test_cloud_service_has_get_offline_task(self):
        assert hasattr(CloudService, "get_offline_task")

    def test_cloud_service_has_delete_offline_task(self):
        """CloudService 定义了 delete_offline_task 抽象方法"""
        assert hasattr(CloudService, "delete_offline_task")

    def test_cloud_service_no_raw_list_directory(self):
        """契约不再暴露原始 dict 的 list_directory（原始形状已被适配器挡住）"""
        assert not hasattr(CloudService, "list_directory")

    def test_cloud_service_has_delete_file(self):
        """CloudService 定义了 delete_file 抽象方法"""
        assert hasattr(CloudService, "delete_file")

    def test_incomplete_implementation_raises_type_error(self):
        """未实现所有抽象方法的子类不可实例化"""

        class IncompleteService(CloudService):
            """故意只实现部分方法的不完整子类"""

            async def list_files(self, dir_id: str) -> list:
                return []

        with pytest.raises(TypeError):
            IncompleteService()  # type: ignore


class TestP115CloudServiceInheritance:
    """测试 P115CloudService 与 CloudService 的继承关系"""

    def test_p115_is_subclass_of_cloud_service(self):
        """P115CloudService 是 CloudService 的子类"""
        assert issubclass(P115CloudService, CloudService)

    def test_p115_implements_all_abstract_methods(self):
        """P115CloudService 实现了 CloudService 所有抽象方法"""
        import inspect

        # 获取 CloudService 中所有抽象方法名
        abstract_methods = {
            name
            for name, method in inspect.getmembers(CloudService)
            if getattr(method, "__isabstractmethod__", False)
        }
        # 获取 P115CloudService 实现的方法名
        p115_methods = {
            name
            for name, _ in inspect.getmembers(
                P115CloudService, predicate=inspect.isfunction
            )
        }
        # 所有抽象方法必须已实现
        missing = abstract_methods - p115_methods
        assert not missing, f"P115CloudService 未实现以下方法: {missing}"

    def test_p115_can_be_instantiated_with_mock_client(self):
        """P115CloudService 可以用 mock 客户端实例化"""
        mock_client = MagicMock()
        service = P115CloudService(mock_client)
        assert isinstance(service, CloudService)
        assert isinstance(service, P115CloudService)

    def test_p115_stores_client_reference(self):
        """P115CloudService 正确存储传入的客户端引用"""
        mock_client = MagicMock()
        service = P115CloudService(mock_client)
        # 客户端应被存储为实例属性（允许不同属性名）
        found = any(v is mock_client for v in vars(service).values())
        assert found, "P115CloudService 未存储传入的客户端引用"


class TestP115CloudServiceMethods:
    """测试 P115CloudService 各方法的基本行为"""

    def setup_method(self):
        """每个测试前创建带 mock 客户端的服务实例"""
        self.mock_client = MagicMock()
        self.service = P115CloudService(self.mock_client)

    @pytest.mark.asyncio
    async def test_list_files_calls_client(self):
        """list_files 应调用底层客户端，list_directory 返回 dict 格式"""
        mock_response = {"data": [{"fid": "123", "n": "test.mp4", "s": 1024, "cid": "0", "pid": "abc"}]}
        self.mock_client.list_directory = AsyncMock(return_value=mock_response)
        result = await self.service.list_files("0")
        assert isinstance(result, list)
        self.mock_client.list_directory.assert_called_once_with("0")

    @pytest.mark.asyncio
    async def test_get_offline_tasks_returns_list(self):
        """get_offline_tasks 应返回列表"""
        self.mock_client.get_offline_tasks = AsyncMock(return_value=[])
        result = await self.service.get_offline_tasks()
        assert isinstance(result, list)
