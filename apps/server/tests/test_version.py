"""@description 应用版本信息服务和接口测试
@responsibility 验证版本元数据读取及版本接口响应契约
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import system
from app.services import version


def test_reads_project_version(tmp_path):
    """优先读取标准 project.version。"""
    metadata = tmp_path / "pyproject.toml"
    metadata.write_text('[project]\nversion = "2.3.4"\n', encoding="utf-8")

    assert version._read_version([metadata]) == "2.3.4"


def test_reads_poetry_version_as_fallback(tmp_path):
    """标准版本缺失时读取 Poetry 元数据。"""
    metadata = tmp_path / "pyproject.toml"
    metadata.write_text('[tool.poetry]\nversion = "3.2.1"\n', encoding="utf-8")

    assert version._read_version([metadata]) == "3.2.1"


def test_missing_metadata_returns_unknown(tmp_path):
    """候选文件不存在时返回未知版本。"""
    assert version._read_version([tmp_path / "missing.toml"]) == "unknown"


def test_invalid_metadata_returns_unknown(tmp_path):
    """TOML 格式非法时返回未知版本。"""
    metadata = tmp_path / "pyproject.toml"
    metadata.write_text("[project\nversion =", encoding="utf-8")

    assert version._read_version([metadata]) == "unknown"


@pytest.mark.asyncio
async def test_version_endpoint_returns_exact_payload(monkeypatch):
    """版本接口直接返回精简的名称与版本 JSON。"""
    monkeypatch.setattr(
        system,
        "get_version_info",
        lambda: {"name": "mediabridge", "version": "9.8.7"},
    )
    app = FastAPI()
    app.include_router(system.router, prefix="/api")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/version")

    assert response.status_code == 200
    assert response.json() == {"name": "mediabridge", "version": "9.8.7"}
