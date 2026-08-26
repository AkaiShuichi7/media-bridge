# MediaBridge

MediaBridge 是一个 115 网盘离线下载与媒体整理工具，单仓库（monorepo）托管全部组件：Web 管理界面、浏览器扩展、服务端，以及预留的本地 Agent 与共享 API 契约。

核心工作流：**提交磁力链接 → 115 离线下载 → 完成后自动整理（按媒体库规则移动/重命名）→ 记录归档**。

## 功能特性

- **离线任务管理**：提交磁力链接到 115 离线下载，实时查看进度、状态，手动/自动删除任务
- **自动整理**：后台监控任务完成状态，按媒体库规则过滤视频文件（格式 + 最小体积），自动移动到目标目录；`xx-片商` 类型库支持番号提取、文件名规范化与重命名
- **多媒体库**：按名称或下载路径匹配目标库，库级可覆盖最小传输体积等阈值
- **Web 管理界面**：登录认证（HttpOnly 会话 Cookie）、仪表盘、任务列表、整理记录、配置查看
- **浏览器扩展**（Chrome MV3）：在任意网站点击"复制磁力链接"后自动捕获，经 popup 确认后才提交——插件永不自动发送任务
- **个人访问令牌**：扩展等非 Web 客户端使用 `Authorization: Bearer <token>` 认证，令牌创建/吊销走 `/api/auth/tokens`，明文只在创建时展示一次
- **路径缓存**：路径 → 目录 ID 映射持久化到 SQLite（10 分钟 TTL，番号目录不缓存），显著减少 115 API 调用

## 仓库结构

```text
apps/
  server/         FastAPI 服务端（业务核心）
  web/            React + Vite + React Query 管理界面
  extension/      Chrome MV3 浏览器扩展（磁力捕获）
  agent/          本地 Agent（预留）
packages/
  api-contracts/  共享 API 契约与生成客户端（预留）
infra/
  Dockerfile / docker-compose.yml / nginx / supervisor
docs/
  agents/         工程技能配置（issue 跟踪、triage 标签、领域文档规则）
CONTEXT.md        领域词汇表（离线任务/番号/临时目录等术语的唯一定义处）
```

### 服务端模块速览

| 模块 | 职责 |
|------|------|
| `app/services/cloud/` | CloudService 中立契约 + 115 适配器，115 原始响应形状被挡在适配器内 |
| `app/services/path_cache.py` | 路径 ID 缓存（get/set/cleanup，session 工厂注入） |
| `app/services/offline_task_service.py` | 添加离线任务领域服务：库校验 → 目录解析 → 云端建任务 → 本地落库 → 失败补偿回滚 |
| `app/services/file_organizer.py` | 文件整理编排（system 直移 / xx-片商 番号整理） |
| `app/services/file_filter.py` | 视频格式与体积过滤 |
| `app/services/fanhao_parser.py` | 番号提取、文件名规范化、目标路径生成 |
| `app/tasks/monitor.py` | 后台轮询：比对 115 任务状态并触发整理 |
| `app/api/` | 路由层（只做协议转换，业务在 services） |

## 快速部署（Docker）

```bash
cp apps/server/config.example.yaml config.yaml
cp .env.example .env
mkdir -p db logs
# 编辑 config.yaml 填入 115 cookies；在 .env 中设置足够长的 MEDIABRIDGE_ADMIN_PASSWORD
docker compose -f infra/docker-compose.yml up -d
```

打开 `http://<host>:8080`，用 `.env` 中的管理员凭据登录。

注意事项：

- 部署在 HTTPS 反代之后时保持 `MEDIABRIDGE_COOKIE_SECURE=true`；仅本地 HTTP 环境才设 false
- FastAPI 文档端点（`/docs`、`/redoc`、`/openapi.json`）未通过内置 Nginx 暴露，除非确有必要不要加到公网反代
- 使用自定义镜像名：`IMAGE_NAME=your-dockerhub-user/mediabridge:latest docker compose -f infra/docker-compose.yml up -d`

## 本地开发

服务端：

```bash
cd apps/server
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn main:app --reload
```

Web：

```bash
cd apps/web
npm ci
npm run dev
```

浏览器扩展：

```bash
cd apps/extension
npm ci
npm run build
# chrome://extensions → 开发者模式 → 加载已解压 → 选 apps/extension/dist
# 加载前移除旧版解压扩展，只保留一个启用副本（否则 content script 与 popup 存储隔离）
```

## 测试

```bash
cd apps/server
.venv/bin/pip install pytest pytest-asyncio aiosqlite
.venv/bin/python -m pytest tests -v
# 覆盖：API 路由 / 认证 / CloudService 契约 / 离线任务服务（含补偿回滚）
#       / 文件过滤 / 番号解析 / 监控 / 路径缓存（含番号目录拒写与 TTL）
```

## 配置说明

配置真源是 `apps/server/app/core/config.py` 与 `config.example.yaml`，顶层键为 `cloud` 与 `media`：

```yaml
cloud:
  cookies: "你的 115 cookies"        # 可用环境变量 P115_COOKIES 覆盖
  poll_interval_min: 60              # 轮询间隔（秒，随机区间下限）
  poll_interval_max: 80
media:
  min_transfer_size: 200             # 默认最小体积（MB），库级可覆盖
  video_formats: [mp4, mkv, ...]     # 支持的视频格式
  libraries:                         # 媒体库列表
    - name: 电影库
      download_path: /云下载/电影
      target_path: /媒体/电影
      type: system                   # system=直接移动；xx-<片商>=番号整理
  xx:
    remove_keywords: [...]           # xx 库文件名清理关键词
```

旧版 `p115.*` 顶层结构仍会被兼容迁移，但新配置请勿再使用。

## 认证与客户端

- **Web 界面**：HttpOnly 会话 Cookie（登录/登出走 `/api/auth/login` `/api/auth/logout`）
- **浏览器扩展 / 未来 Agent**：个人访问令牌（`mb_` 前缀），`POST /api/auth/tokens` 创建、`GET` 列表、`DELETE /api/auth/tokens/{id}` 吊销；这是所有 MediaBridge 客户端统一的认证边界，与 Emby 用户无关

## 开发约定

- 提交遵循 Conventional Commits（`feat:` / `fix:` / `chore:` / `refactor:` / `docs:`），小步提交
- 领域术语以根目录 `CONTEXT.md` 为准（如"番号"、"临时目录"、"CloudService"）
- 服务端 seam 纪律：CloudService 契约之外不得出现 115 原始字段（`fid`/`n`/`sz`/`cid` 等），字段翻译只发生在适配器内
- 镜像发布：根 Docker workflow 仅在 `apps/server`、`apps/web`、`infra` 或 workflow 自身变更时构建统一镜像；扩展与 Agent 后续使用独立 workflow
