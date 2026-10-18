"""
@description 通用工具函数
@responsibility 提供项目级别的辅助功能
"""

from __future__ import annotations
from typing import Optional
import re
import base64


def parse_info_hash_from_magnet(magnet: str) -> Optional[str]:
    """
    从 magnet 链接中解析 info_hash (BTIH)

    支持两种格式：
    1. 40 位 hex 格式：0123456789abcdef...
    2. 32 位 base32 格式：AAAAAAAAAAAAAAAA...（自动转换为 hex）

    Args:
        magnet: magnet 链接字符串，格式如 magnet:?xt=urn:btih:<hash>

    Returns:
        40 位小写 hex 字符串，解析失败返回 None

    Examples:
        >>> parse_info_hash_from_magnet("magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567")
        '0123456789abcdef0123456789abcdef01234567'

        >>> parse_info_hash_from_magnet("magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAA")
        '0000000000000000000000000000000000000000'

        >>> parse_info_hash_from_magnet("invalid")
        None
    """
    if not magnet or not isinstance(magnet, str):
        return None

    # 提取 xt=urn:btih: 后面的 hash（支持 hex 和 base32）
    # hex: 40 位 0-9a-fA-F
    # base32: 32 位 A-Z2-7
    match = re.search(
        r"xt=urn:btih:([a-fA-F0-9]{40}|[A-Z2-7]{32})", magnet, re.IGNORECASE
    )
    if not match:
        return None

    hash_str = match.group(1)

    # 判断是 hex 还是 base32
    if len(hash_str) == 40:
        # 40 位 hex 格式，直接返回小写
        return hash_str.lower()
    elif len(hash_str) == 32:
        # 32 位 base32 格式，转为 hex
        try:
            # Base32 解码为字节（需要大写）
            hash_bytes = base64.b32decode(hash_str.upper())
            # 转为 hex 字符串并返回小写
            return hash_bytes.hex().lower()
        except Exception:
            return None
    else:
        return None


def find_library_by_name(libraries: list, name: str):
    """
    根据名称从媒体库列表中查找对应的库配置。

    Args:
        libraries: 媒体库配置对象列表
        name: 要查找的库名称

    Returns:
        匹配的媒体库配置对象，未找到返回 None
    """
    for library in libraries:
        if library.name == name:
            return library
    return None


def create_result_dict() -> dict:
    """
    创建标准化的任务结果字典。

    Returns:
        包含 success_count、failed_count、skipped_count 和 errors 的初始字典
    """
    return {
        "success_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "errors": [],
    }


def build_library_item(library) -> dict:
    """
    将媒体库配置对象转换为标准字典格式。

    Args:
        library: 媒体库配置对象，包含 name、download_path、target_path 等属性

    Returns:
        标准化的媒体库字典，包含 name、download_path、target_path、type、min_transfer_size
    """
    return {
        "name": library.name,
        "download_path": library.download_path,
        "target_path": library.target_path,
        "type": getattr(library, "type", ""),
        "min_transfer_size": getattr(library, "min_transfer_size", 0),
    }

