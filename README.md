# MediaBridge

MediaBridge 是一条「按媒体库规则运行的 115 下载-归档管线」：提交磁力链接 → 115 离线下载 → 完成后按媒体库规则自动整理归档 → 全程可追溯。单仓库（monorepo）托管全部组件。

三个入口共享同一条管线：

- **Web 管理界面**——人直接操作
- **浏览器扩展**——在任意网页捕获磁力链接
- **Agent 接入层**——外部 agent（如 Hermes）找资源后推入管线

## 核心特性

- **离线任务管理**：提交磁力链接到 115 离线下载，实时进度与状态，四态生命周期（completed / organize_failed / organize_skipped / failed）全程可追溯
- **自动整理**：后台监控任务完成，按媒体库规则过滤视频（格式 + 最小体积）并归档；`xx-片商` 类型库支持番号提取、文件名规范化与重命名
- **归档查询 API**：按番号/关键词查询「已归档 / 在途 / 失败 / 跳过」，供 agent 去重与域路由
- **多媒体库**：按名称或下载路径匹配目标库，库级可覆盖体积阈值等配置
- **统一认证**：Web 用会话 Cookie，扩展与 agent 用 `mb_` 个人访问令牌（可创建/吊销）
- **路径缓存**：路径 → 目录 ID 映射持久化 SQLite（10 分钟 TTL，番号目录不缓存），减少 115 API 调用
- **浏览器扩展**（Chrome MV3）：复制磁力链接自动捕获，popup 确认后才提交——永不自动发送

## 仓库结构

```text
apps/
  server/         FastAPI 服务端（业务核心）
  web/            React + Vite + React Query 管理界面
  extension/      Chrome MV3 浏览器扩展（磁力捕获）
  agent/          Agent 接入层：接入手册 + 资源搜索 playbook（非独立服务）
packages/
  api-contracts/  共享 API 契约与生成客户端（预留）
infra/            Docker / nginx / supervisor 部署配置
docs/
  architecture/   项目流程图（HTML 视觉版 + Mermaid 源码版）
  agents/         工程技能配置（issue 跟踪、triage 标签、领域文档规则）
GLOSSARY.md       领域词汇表（离线任务/番号/临时目录等术语的唯一定义处）
```

### 服务端模块速览

| 模块 | 职责 |
|------|------|
| `app/services/cloud/` | CloudService 中立契约 + 115 适配器，115 原始响应形状被挡在适配器内 |
| `app/services/offline_task_service.py` | 离线任务领域服务：添加全流程（含补偿回滚）、生命周期迁移、归档聚合查询 |
| `app/services/file_organizer.py` | 文件整理编排（system 直移 / xx-片商 番号整理）与整理记录 |
| `app/services/path_cache.py` | 路径 ID 缓存（get/set/cleanup，session 工厂注入） |
| `app/services/file_filter.py` | 视频格式与体积过滤 |
| `app/services/fanhao_parser.py` | 番号提取、文件名规范化、目标路径生成 |
| `app/tasks/monitor.py` | 后台轮询：比对 115 任务状态并触发整理 |
| `app/api/` | 路由层（只做协议转换，业务在 services；含 `agent.py` 归档查询） |

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

## Agent 接入

`apps/agent/` 不是需要安装的独立服务，而是**面向外部 agent 的接口层**：API 由服务端提供，目录内只放接入手册与搜索 playbook。外部 agent（如 Hermes 的 media profile）按文档接入即可，无需在 MediaBridge 侧安装任何东西。

启用三步：

1. 部署最新服务端（归档查询 API 在 `0c8d1bf` 及之后版本可用）
2. Web 端 **Settings → 访问令牌** 创建 `mb_` 个人访问令牌（明文只显示一次）
3. 在 agent 侧按 [`apps/agent/AGENTS.md`](apps/agent/AGENTS.md) 配置（认证、接口、铁律），找资源的实操方法见 [`apps/agent/docs/search-playbook.md`](apps/agent/docs/search-playbook.md)

三条铁律（与扩展同一哲学）：**永不自动提交**（候选必须经用户确认）、**提交前必查归档**（`GET /api/agent/archive/query` 去重）、**域路由**（番号域走 MediaBridge，TMDB 电影/剧集域走 MoviePilot）。

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
# 覆盖：API 路由 / 认证 / 归档查询 / CloudService 契约 / 离线任务服务（含补偿回滚）
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
- **浏览器扩展 / Agent**：个人访问令牌（`mb_` 前缀），`POST /api/auth/tokens` 创建、`GET` 列表、`DELETE /api/auth/tokens/{id}` 吊销；这是所有 MediaBridge 客户端统一的认证边界，与 Emby 用户无关

## 开发约定

- 提交遵循 Conventional Commits（`feat:` / `fix:` / `chore:` / `refactor:` / `docs:`），小步提交
- 领域术语以根目录 `GLOSSARY.md` 为准（如"番号"、"临时目录"、"CloudService"）
- 服务端 seam 纪律：CloudService 契约之外不得出现 115 原始字段（`fid`/`n`/`sz`/`cid` 等），字段翻译只发生在适配器内
- 流程变更须同步 `docs/architecture/project-flow.md` 与 HTML 视觉版，以代码实现为准
- 镜像发布：根 Docker workflow 仅在 `apps/server`、`apps/web`、`infra` 或 workflow 自身变更时构建统一镜像；扩展与 Agent 后续使用独立 workflow
