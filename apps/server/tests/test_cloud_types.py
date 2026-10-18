"""
@description CloudFile 数据类测试
@responsibility 验证 CloudFile dataclass 和 P115_FIELD_MAP 字段映射的正确性
"""

import pytest
from app.schemas.cloud_types import (
    CloudFile,
    CloudTask,
    CloudTaskStatus,
    P115_FIELD_MAP,
    cloud_task_status_from_code,
    cloud_task_status_to_code,
)


class TestCloudFile:
    """测试 CloudFile dataclass 的构造和字段映射"""

    def test_from_p115_dict_file(self):
        """测试从 115 API 文件记录创建 CloudFile"""
        raw = {
            "fid": "987654321",
            "n": "测试视频.mp4",
            "s": 1073741824,
            "cid": "111222333",
            "pid": "abc123pickcode",
        }
        cf = CloudFile.from_p115_dict(raw)

        assert cf.file_id == "987654321"
        assert cf.name == "测试视频.mp4"
        assert cf.size == 1073741824
        assert cf.parent_id == "111222333"
        assert cf.pick_code == "abc123pickcode"
        assert cf.is_directory is False

    def test_from_p115_dict_directory(self):
        """测试从 115 API 目录记录创建 CloudFile（无 fid 字段）"""
        raw = {
            "cid": "555666777",
            "n": "电影文件夹",
            "s": 0,
        }
        cf = CloudFile.from_p115_dict(raw)

        assert cf.file_id == "555666777"  # 目录时 file_id 来自 cid
        assert cf.name == "电影文件夹"
        assert cf.is_directory is True

    def test_from_p115_dict_missing_optional_fields(self):
        """测试缺少可选字段时使用默认值"""
        raw = {
            "fid": "111",
            "n": "文件.mkv",
        }
        cf = CloudFile.from_p115_dict(raw)

        assert cf.file_id == "111"
        assert cf.name == "文件.mkv"
        assert cf.size == 0  # 默认值
        assert cf.parent_id == ""  # 默认值
        assert cf.pick_code == ""  # 默认值
        assert cf.is_directory is False

    def test_from_p115_dict_size_conversion(self):
        """测试 size 字段进行整数转换"""
        raw = {"fid": "1", "n": "a.mp4", "s": "2048"}
        cf = CloudFile.from_p115_dict(raw)
        assert cf.size == 2048
        assert isinstance(cf.size, int)

    def test_p115_field_map_keys(self):
        """验证 P115_FIELD_MAP 包含所有必要的字段映射"""
        required_keys = {"fid", "n", "s", "cid", "pid"}
        assert required_keys.issubset(set(P115_FIELD_MAP.keys()))

    def test_p115_field_map_values(self):
        """验证 P115_FIELD_MAP 映射到正确的标准字段名"""
        assert P115_FIELD_MAP["fid"] == "file_id"
        assert P115_FIELD_MAP["n"] == "name"
        assert P115_FIELD_MAP["s"] == "size"
        assert P115_FIELD_MAP["cid"] == "parent_id"
        assert P115_FIELD_MAP["pid"] == "pick_code"

    def test_cloud_file_is_dataclass(self):
        """验证 CloudFile 是 dataclass，支持直接构造"""
        cf = CloudFile(
            file_id="100",
            name="test.mp4",
            size=500,
            parent_id="200",
            is_directory=False,
            pick_code="xyz",
        )
        assert cf.file_id == "100"
        assert cf.name == "test.mp4"

    def test_cloud_file_equality(self):
        """验证相同内容的 CloudFile 相等（dataclass 默认行为）"""
        cf1 = CloudFile.from_p115_dict(
            {"fid": "1", "n": "a.mp4", "s": 100, "cid": "2", "pid": "p1"}
        )
        cf2 = CloudFile.from_p115_dict(
            {"fid": "1", "n": "a.mp4", "s": 100, "cid": "2", "pid": "p1"}
        )
        assert cf1 == cf2

    def test_cloud_file_inequality(self):
        """验证不同 file_id 的 CloudFile 不相等"""
        cf1 = CloudFile.from_p115_dict({"fid": "1", "n": "a.mp4", "s": 0})
        cf2 = CloudFile.from_p115_dict({"fid": "2", "n": "a.mp4", "s": 0})
        assert cf1 != cf2

    def test_multiple_files_from_api_response(self):
        """测试批量转换 API 响应列表（模拟真实场景）"""
        raw_items = [
            {"fid": "1", "n": "电影1.mp4", "s": 1000, "cid": "100", "pid": "pc1"},
            {"cid": "200", "n": "子文件夹"},  # 目录，无 fid
            {"fid": "3", "n": "电影3.mkv", "s": 2000, "cid": "100", "pid": "pc3"},
        ]
        files = [CloudFile.from_p115_dict(item) for item in raw_items]

        assert len(files) == 3
        assert files[0].is_directory is False
        assert files[1].is_directory is True
        assert files[2].is_directory is False


class TestCloudTaskStatus:
    """测试 CloudTask 中立状态枚举与数值口径映射"""

    def test_from_p115_dict_translates_status(self):
        """115 原始状态码在 from_p115_dict 内翻译为中立枚举"""
        base = {"info_hash": "h1", "name": "任务", "percent_done": 50, "add_time": 1700000000}
        assert CloudTask.from_p115_dict({**base, "status": 2}).status is CloudTaskStatus.COMPLETED
        assert CloudTask.from_p115_dict({**base, "status": 0}).status is CloudTaskStatus.DOWNLOADING
        assert CloudTask.from_p115_dict({**base, "status": 1}).status is CloudTaskStatus.PENDING
        assert CloudTask.from_p115_dict({**base, "status": -1}).status is CloudTaskStatus.FAILED
        # 缺省状态码按 0 处理
        assert CloudTask.from_p115_dict(dict(base)).status is CloudTaskStatus.DOWNLOADING

    def test_from_code_mapping_rules(self):
        """from_code：2=完成、负数=失败、1=等待中、0 及未知非负值=下载中"""
        assert cloud_task_status_from_code(2) is CloudTaskStatus.COMPLETED
        assert cloud_task_status_from_code(0) is CloudTaskStatus.DOWNLOADING
        assert cloud_task_status_from_code(1) is CloudTaskStatus.PENDING
        assert cloud_task_status_from_code(-1) is CloudTaskStatus.FAILED
        assert cloud_task_status_from_code(-3) is CloudTaskStatus.FAILED
        assert cloud_task_status_from_code(3) is CloudTaskStatus.DOWNLOADING

    def test_to_code_contract(self):
        """to_code：对外数值口径 2/-1/1/0"""
        assert cloud_task_status_to_code(CloudTaskStatus.COMPLETED) == 2
        assert cloud_task_status_to_code(CloudTaskStatus.FAILED) == -1
        assert cloud_task_status_to_code(CloudTaskStatus.PENDING) == 1
        assert cloud_task_status_to_code(CloudTaskStatus.DOWNLOADING) == 0

    @pytest.mark.parametrize("code", [2, 1, 0, -1])
    def test_round_trip_preserves_known_codes(self, code):
        """已知口径数值 round-trip 后保持不变（API 契约不回归）"""
        assert cloud_task_status_to_code(cloud_task_status_from_code(code)) == code
