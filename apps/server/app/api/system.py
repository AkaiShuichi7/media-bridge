"""System health and monitor-status endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from app.core.dependencies import get_cloud_service, get_task_monitor
from app.schemas.api import ApiResponse, StatusResponse, success_response

if TYPE_CHECKING:
    from app.services.cloud.base import CloudService
    from app.tasks.monitor import TaskMonitor


router = APIRouter()


@router.get("/status", response_model=ApiResponse[StatusResponse])
async def get_status(
    task_monitor: "TaskMonitor" = Depends(get_task_monitor),
    cloud_service: "CloudService" = Depends(get_cloud_service),
):
    """Return monitor state, its latest poll time, and active task count."""
    monitor_running = False
    if task_monitor is not None:
        task = getattr(task_monitor, "_task", None)
        stop_event = getattr(task_monitor, "_stop_event", None)
        if task is not None:
            monitor_running = not task.done()
        elif stop_event is not None:
            monitor_running = not stop_event.is_set()

    active_tasks = 0
    if cloud_service is not None:
        try:
            tasks = await cloud_service.get_offline_tasks()
            active_tasks = sum(1 for task in tasks if task.status == 0)
        except Exception:
            # Status reporting must remain available when the upstream provider is down.
            pass

    last_check_time = getattr(task_monitor, "last_check_time", None)
    last_check_time_value = (
        last_check_time.isoformat() if isinstance(last_check_time, datetime) else None
    )
    return success_response(
        data=StatusResponse(
            monitor_running=monitor_running,
            active_tasks=active_tasks,
            last_check_time=last_check_time_value,
        ),
        message="获取系统状态成功",
    )
