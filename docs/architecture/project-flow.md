# MediaBridge 项目流程图（Mermaid 源文件）

> 本文件是供 GitHub、Markdown 渲染器及其他模型/Agent 使用的文本版流程图。Mermaid 源码保留节点、分支和连线语义；视觉版见 [project-flow.html](./project-flow.html)。
>
> 基线：`b1839c4`。图示描述以代码实现为准；代码变更涉及流程时，应同步更新本文件和 HTML 视觉版。

## 1. 系统架构与数据流

```mermaid
flowchart LR
    User[用户]
    Web[Web 管理台]
    Extension[Chrome 扩展]
    Agent[外部 Agent：Hermes 等]
    Nginx[Nginx：静态 Web 与 API 反向代理]
    API[FastAPI：认证、CSRF 与 API 路由]
    TaskService[OfflineTaskService]
    Monitor[TaskMonitor：后台轮询]
    Organizer[FileOrganizer：媒体库整理]
    CloudContract[CloudService 契约]
    P115Adapter[P115CloudService 适配器]
    Drive[115 云盘：离线任务与文件]
    DB[(SQLite：用户、令牌、任务、整理记录)]
    Config[(config.yaml：云盘、媒体库与规则)]

    User --> Web
    Web -->|HttpOnly 会话 Cookie；写操作含 CSRF| Nginx
    Extension -->|用户确认后以 Bearer Token 提交| Nginx
    Agent -->|归档查询去重；用户确认后以 Bearer Token 提交| Nginx
    Nginx --> API
    API --> TaskService
    API --> DB
    TaskService -->|读取服务配置| Config
    TaskService --> CloudContract
    TaskService --> DB
    Monitor --> DB
    Monitor --> CloudContract
    Monitor --> Organizer
    Organizer -->|读取媒体库规则| Config
    Organizer --> DB
    Organizer --> CloudContract
    CloudContract --> P115Adapter
    P115Adapter --> Drive
```

## 2. 离线任务生命周期

```mermaid
flowchart TD
    Submit[用户从 Web 或扩展提交磁力链接]
    Auth[认证与 CSRF 校验]
    Validate[解析 magnet、校验名称与媒体库]
    Resolve[解析下载目录 ID]
    Create[向 115 创建离线任务]
    Save[保存本地任务记录：info_hash 与 added 状态]
    Rollback[本地保存失败：尽力回滚云端任务]
    Monitor[TaskMonitor 查询本地活动任务]
    Poll[经 CloudService 查询 115 状态]
    State{115 任务状态？}
    Wait[进行中：等待下一轮轮询]
    DownloadFailed[负状态：本地标记 failed]
    ListFiles[下载完成：列出任务文件；必要时回查父目录]
    Filter[筛选视频格式与最小体积]
    HasVideo{有符合条件的视频？}
    NoVideo[返回 0 成功并附无可整理文件原因]
    Library{判断媒体库类型}
    System[system：直接移动文件]
    Parse[xx-片商：清理文件名并提取番号]
    HasCode{番号可识别？}
    FileSkipped[文件级跳过并继续处理其他文件]
    Target[生成目标路径：建目录与重命名]
    Move[移动文件]
    Aggregate[汇总成功数、失败数、跳过数与说明]
    HasFailure{failed_count 大于 0？}
    OrganizeFailed[organize_failed：保留 115 任务与错误原因]
    HasSuccess{success_count 大于 0？}
    OrganizeSkipped[organize_skipped：保留任务与可读原因]
    Completed[completed：清理 115 离线任务]

    Submit --> Auth --> Validate --> Resolve --> Create --> Save
    Save -. 本地保存失败 .-> Rollback
    Save --> Monitor --> Poll --> State
    State -->|进行中| Wait
    Wait --> Monitor
    State -->|status 小于 0| DownloadFailed
    State -->|status 等于 2：下载完成| ListFiles --> Filter --> HasVideo
    HasVideo -->|否：success=0| NoVideo --> Aggregate
    HasVideo -->|是| Library
    Library -->|system| System --> Move
    Library -->|xx-片商| Parse --> HasCode
    HasCode -->|否| FileSkipped --> Aggregate
    HasCode -->|是| Target --> Move
    Move --> Aggregate
    Aggregate --> HasFailure
    HasFailure -->|是| OrganizeFailed
    HasFailure -->|否| HasSuccess
    HasSuccess -->|否| OrganizeSkipped
    HasSuccess -->|是| Completed
```

### 终态语义

- `failed`：115 下载任务本身返回负状态。
- `organize_failed`：整理过程中至少一项失败；保留 115 任务和错误原因。
- `organize_skipped`：整理后成功数为 0（包括没有符合条件的视频或所有文件均被跳过）；保留任务与说明。
- `completed`：至少一项整理成功且没有失败；随后清理 115 离线任务。部分文件被跳过不阻止其他文件成功归档。

## 3. 浏览器扩展捕获流程

```mermaid
flowchart LR
    Page[资源网页]
    Copy[用户触发复制]
    Capture[capture 管线：page-hook 与 isolated 层]
    Valid{剪贴板内容是有效 magnet？}
    Ignore[忽略：不保存]
    Store[保存待处理状态到 chrome.storage.local]
    Popup[Popup：配置服务地址、Token 并选择媒体库]
    Confirm{用户确认提交？}
    Clear[取消：清除捕获，不创建任务]
    Send[以 Bearer Token 提交 /api/tasks]
    Result{API 提交成功？}
    Done[成功：清空捕获]
    KeepError[失败：保留错误原因]

    Page --> Copy --> Capture --> Valid
    Valid -->|否| Ignore
    Valid -->|是| Store --> Popup --> Confirm
    Confirm -->|否| Clear
    Confirm -->|是| Send --> Result
    Result -->|是| Done
    Result -->|否| KeepError
```

> 捕获不等于提交：扩展只暂存链接，必须由用户在 Popup 明确确认后才创建任务。

## 4. Agent 找资源接入流程

```mermaid
flowchart TD
    Ask[用户给出番号或关键词]
    Query[归档查询 GET /api/agent/archive/query]
    Verdict{归档查询结果？}
    Archived[archived 命中：已有，回报归档路径]
    InFlight[in_flight：在途，不重复提交]
    Failed[failed：报告失败历史，用户决定是否重试]
    Search[搜索磁链：javdb 元数据 + torrentkitty 磁链]
    Candidates[列出候选：标题 / 体积 / 日期]
    Confirm{用户确认？}
    Submit[POST /api/tasks 提交]
    Track[轮询 GET /api/tasks 追踪]
    Report[归档查询 / 整理记录回报归档路径]

    Ask --> Query --> Verdict
    Verdict -->|archived| Archived
    Verdict -->|in_flight| InFlight
    Verdict -->|failed| Failed
    Verdict -->|未收录| Search --> Candidates --> Confirm
    Confirm -->|否| Candidates
    Confirm -->|是| Submit --> Track --> Report
```

> Agent 铁律：永不自动提交（候选必须经用户确认）、提交前必查归档、域路由（番号域走 MediaBridge，TMDB 域走 MoviePilot）。
> 接入细节见 `apps/agent/AGENTS.md`；源可用性与搜索实操见 `apps/agent/docs/search-playbook.md`。

## 5. 构建、配置与服务启动

```mermaid
flowchart TD
    Source[Web 源码：React 与 Vite]
    NodeBuild[Node 20 构建阶段：npm ci 与 build]
    PythonBuild[Python 3.12 阶段：安装 requirements 锁定依赖]
    Image[单一 Docker 镜像：Nginx、Uvicorn 与静态 Web]
    Compose[Docker Compose：宿主机 8080 映射到容器 80]
    Config[读取 CONFIG_PATH 指定的 YAML 配置]
    Database[初始化 SQLite 与认证数据]
    Client[创建 115 Client 并校验 cookies]
    Services[创建 CloudService 适配器与整理服务]
    Monitor[启动 TaskMonitor 后台轮询]
    Supervisor[Supervisor 管理 Nginx 与 Uvicorn]
    Nginx[Nginx：对外提供 Web 并反向代理 /api]
    Uvicorn[Uvicorn：FastAPI API 服务]
    Volumes[(持久化挂载：db、config.yaml、logs)]

    Source --> NodeBuild --> Image
    PythonBuild --> Image
    Image --> Compose
    Compose --> Supervisor
    Supervisor --> Nginx
    Supervisor --> Uvicorn
    Nginx -->|/api 反向代理| Uvicorn
    Uvicorn --> Config --> Database --> Client --> Services --> Monitor
    Compose --- Volumes
    Database --- Volumes
    Config --- Volumes
```

- Compose 将数据库、配置文件与日志目录挂载到宿主机；Supervisor 管理 Nginx 和 Uvicorn。
- 设置保存会校验配置、写回 YAML 并更新运行配置。
- 当前代码中 115 cookies 校验失败会记录错误，但不会因此中止应用初始化。
