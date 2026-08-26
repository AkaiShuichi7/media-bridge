"""
@description 文件过滤测试用例
@responsibility 测试文件过滤服务的核心功能
"""
import pytest
from app.schemas.cloud_types import CloudFile
from app.services.file_filter import is_video_file, meets_size_requirement, filter_files


class TestVideoFormat:
    """视频格式过滤测试"""

    @pytest.mark.parametrize(
        "filename,formats,expected",
        [
            # 支持的格式
            ("video.mp4", ["mp4", "mkv", "avi"], True),
            ("movie.mkv", ["mp4", "mkv", "avi"], True),
            ("video.avi", ["mp4", "mkv", "avi"], True),
            # 不支持的格式
            ("document.pdf", ["mp4", "mkv", "avi"], False),
            ("image.jpg", ["mp4", "mkv", "avi"], False),
            ("text.txt", ["mp4", "mkv", "avi"], False),
            # 大小写不敏感
            ("video.MP4", ["mp4", "mkv", "avi"], True),
            ("MOVIE.MKV", ["mp4", "mkv", "avi"], True),
            # 不带扩展名
            ("noextension", ["mp4", "mkv", "avi"], False),
            # 多点文件名
            ("movie.1080p.mp4", ["mp4", "mkv", "avi"], True),
        ],
    )
    def test_video_format_filter(self, filename, formats, expected):
        """测试 is_video_file 函数"""
        result = is_video_file(filename, formats)
        assert result == expected


class TestMinSizeFilter:
    """文件大小过滤测试"""

    @pytest.mark.parametrize(
        "size_bytes,min_size_mb,expected",
        [
            # 恰好达到最小值
            (200 * 1024 * 1024, 200, True),
            # 超过最小值
            (300 * 1024 * 1024, 200, True),
            (1024 * 1024 * 1024, 200, True),
            # 小于最小值
            (100 * 1024 * 1024, 200, False),
            (50 * 1024 * 1024, 200, False),
            # 边界：差 1 字节
            (200 * 1024 * 1024 - 1, 200, False),
            # 零和负数
            (0, 100, False),
            (500, 100, False),
            # 精确值测试
            (1 * 1024 * 1024, 1, True),
            (1 * 1024 * 1024 - 1, 1, False),
        ],
    )
    def test_min_size_filter(self, size_bytes, min_size_mb, expected):
        """测试 meets_size_requirement 函数"""
        result = meets_size_requirement(size_bytes, min_size_mb)
        assert result == expected


class TestCombinedFilter:
    """组合过滤测试"""

    def test_combined_filter_success(self):
        """测试 filter_files 筛选符合条件的文件（115 API 返回格式）"""
        files = [
            CloudFile(file_id="12345", name="movie1.mp4", size=300 * 1024 * 1024, parent_id="1", is_directory=False),  # 符合
            CloudFile(file_id="12346", name="movie2.mkv", size=250 * 1024 * 1024, parent_id="1", is_directory=False),  # 符合
            CloudFile(file_id="12347", name="movie3.avi", size=100 * 1024 * 1024, parent_id="1", is_directory=False),  # 不符合（太小）
            CloudFile(file_id="12348", name="image.jpg", size=500 * 1024 * 1024, parent_id="1", is_directory=False),  # 不符合（格式）
            CloudFile(file_id="12349", name="video.mp4", size=150 * 1024 * 1024, parent_id="1", is_directory=False),  # 不符合（太小）
        ]
        config = {
            "video_formats": ["mp4", "mkv", "avi", "mov"],
            "min_transfer_size": 200,
        }

        result = filter_files(files, config)

        assert len(result) == 2
        assert result[0].name == "movie1.mp4"
        assert result[1].name == "movie2.mkv"

    def test_combined_filter_empty_list(self):
        """测试 filter_files 处理空文件列表"""
        files = []
        config = {
            "video_formats": ["mp4", "mkv", "avi"],
            "min_transfer_size": 200,
        }

        result = filter_files(files, config)

        assert len(result) == 0
        assert result == []

    def test_combined_filter_no_matches(self):
        """测试 filter_files 无匹配结果"""
        files = [
            CloudFile(file_id="12345", name="document.pdf", size=500 * 1024 * 1024, parent_id="1", is_directory=False),
            CloudFile(file_id="12346", name="image.jpg", size=500 * 1024 * 1024, parent_id="1", is_directory=False),
            CloudFile(file_id="12347", name="small.mp4", size=100 * 1024 * 1024, parent_id="1", is_directory=False),
        ]
        config = {
            "video_formats": ["mp4", "mkv", "avi"],
            "min_transfer_size": 200,
        }

        result = filter_files(files, config)

        assert len(result) == 0

    def test_combined_filter_all_match(self):
        """测试 filter_files 全部匹配"""
        files = [
            CloudFile(file_id="12345", name="video1.mp4", size=500 * 1024 * 1024, parent_id="1", is_directory=False),
            CloudFile(file_id="12346", name="video2.mkv", size=600 * 1024 * 1024, parent_id="1", is_directory=False),
            CloudFile(file_id="12347", name="video3.avi", size=700 * 1024 * 1024, parent_id="1", is_directory=False),
        ]
        config = {
            "video_formats": ["mp4", "mkv", "avi"],
            "min_transfer_size": 200,
        }

        result = filter_files(files, config)

        assert len(result) == 3
