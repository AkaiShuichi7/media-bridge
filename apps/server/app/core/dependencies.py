"""
@description FastAPI 依赖注入提供者模块
@responsibility 通过 Depends() 将 AppContainer 中的服务注入路由，消除对 app.state.xxx 属性名的硬编码
"""

from typing import TYPE_CHECKING
from fastapi import Request

if TYPE_CHECKING:
    from app.core.config import AppConfig
    from app.services.p115_client import P115Client
    from app.services.cloud.p115 import P115CloudService
    from app.services.offline_task_service import OfflineTaskService
    from app.tasks.monitor import TaskMonitor
    from app.services.file_organizer import FileOrganizer


def get_config(request: Request) -> "AppConfig":
    return request.app.state.container.config


def get_p115_client(request: Request) -> "P115Client":
    return request.app.state.container.p115_client


def get_cloud_service(request: Request) -> "P115CloudService":
    return request.app.state.container.cloud_service


def get_offline_task_service(request: Request) -> "OfflineTaskService":
    return request.app.state.container.offline_task_service


def get_task_monitor(request: Request) -> "TaskMonitor":
    return request.app.state.container.task_monitor


def get_file_organizer(request: Request) -> "FileOrganizer":
    return request.app.state.container.file_organizer
