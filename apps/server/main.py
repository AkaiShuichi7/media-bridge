"""
@description FastAPI 应用入口
@responsibility 初始化应用、集成路由、启动监控任务、验证 cookies
"""

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import agent, auth, config, organize, system, tasks
from app.core.config import load_config
from app.core.container import AppContainer
from app.schemas.api import ApiResponse, success_response


def _configure_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.remove()
    logger.add(sys.stderr, level=log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    logger.info("应用启动中...")

    container = AppContainer()
    await container.init(load_config())
    app.state.container = container

    yield

    await container.shutdown()
    logger.info("应用已关闭")


app = FastAPI(
    title="115 离线任务管理器",
    description="管理 115 网盘离线下载任务并自动整理文件",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def require_authentication(request: Request, call_next):
    """Require a browser session or Bearer token for every API endpoint."""
    if not request.url.path.startswith("/api/") or request.url.path == "/api/auth/login":
        return await call_next(request)

    service = getattr(getattr(request.app.state, "container", None), "auth_service", None)
    if service is None:
        return JSONResponse(status_code=503, content={"code": 503, "message": "Authentication is initializing", "data": None})

    authorization = request.headers.get("Authorization", "")
    token_user = await service.user_from_token(authorization.removeprefix("Bearer ").strip()) if authorization.startswith("Bearer ") else None
    session_user = None if token_user else await service.user_from_session(request.cookies.get("mediabridge_session"))
    if token_user is not None:
        request.state.auth_user = token_user
    elif session_user is not None:
        request.state.auth_user, request.state.csrf_token = session_user
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("X-CSRF-Token") != request.state.csrf_token:
            return JSONResponse(status_code=403, content={"code": 403, "message": "Invalid CSRF token", "data": None})
    else:
        return JSONResponse(status_code=401, content={"code": 401, "message": "Authentication required", "data": None})
    return await call_next(request)


# 全局异常处理器
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """处理 HTTP 异常"""
    logger.info(f"HTTP 异常处理器被调用: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(
            code=exc.status_code, message=exc.detail, data=None
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求参数验证错误"""
    logger.info(f"验证错误处理器被调用: {len(exc.errors())} 个错误")
    errors = [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=ApiResponse(
            code=422, message="请求参数验证失败", data={"errors": errors}
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """处理通用异常"""
    logger.info(f"通用异常处理器被调用: {type(exc).__name__}")
    logger.exception(f"服务器内部错误: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content=ApiResponse(code=500, message="服务器内部错误", data=None).model_dump(),
    )


app.include_router(tasks.router, prefix="/api", tags=["tasks"])
app.include_router(organize.router, prefix="/api", tags=["organize"])
app.include_router(agent.router, prefix="/api", tags=["agent"])
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(system.router, prefix="/api", tags=["system"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])


@app.get("/")
async def root():
    return success_response(
        data={"message": "115 离线任务管理器 API", "version": "1.0.0"},
        message="服务运行中",
    )


@app.get("/health")
async def health_check():
    return success_response(data={"status": "healthy"}, message="健康检查通过")
