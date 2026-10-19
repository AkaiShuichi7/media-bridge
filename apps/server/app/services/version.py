"""@description 应用版本信息服务
@responsibility 从项目元数据中读取应用名称和版本
"""

from pathlib import Path
import tomllib
from typing import Iterable


APP_NAME = "mediabridge"


def _candidate_paths() -> tuple[Path, Path]:
    """返回后端目录及仓库根目录中的项目元数据路径。"""
    service_file = Path(__file__).resolve()
    return (
        service_file.parents[2] / "pyproject.toml",
        service_file.parents[3] / "pyproject.toml",
    )


def _read_version(paths: Iterable[Path]) -> str:
    """按候选顺序读取项目版本；元数据不可用时返回 unknown。"""
    for path in paths:
        try:
            with path.open("rb") as file:
                data = tomllib.load(file)
        except FileNotFoundError:
            continue
        except Exception:
            return "unknown"

        try:
            version = data.get("project", {}).get("version")
            if version is None:
                version = data.get("tool", {}).get("poetry", {}).get("version")
            return version if isinstance(version, str) and version else "unknown"
        except Exception:
            return "unknown"

    return "unknown"


def get_version_info() -> dict[str, str]:
    """返回应用名称和版本信息。"""
    return {"name": APP_NAME, "version": _read_version(_candidate_paths())}
