# MediaBridge Agent 接入手册

面向外部 agent（Hermes 各 profile、未来自动化程序）的 MediaBridge 接入说明。
MediaBridge 是「按媒体库规则运行的 115 下载-归档管线」；agent 的角色是
**找到资源并推入管线**，管线本身（下载、整理、归档、追溯）由 MediaBridge 负责。

## 铁律

1. **永不自动提交**：agent 找到的资源只作为「候选」呈现给用户，用户明确确认后才调用提交接口。与浏览器扩展同一哲学——减少操作，但不替用户做不可逆决定。
2. **提交前必查归档**：先调归档查询接口去重，避免重复下载（详见下文）。
3. **域路由**：番号域（JavDB/片商库）资源才属于 MediaBridge；TMDB 域（电影/剧集）走 MoviePilot。判断依据是元数据体系，不是资源类型。

## 认证

所有 `/api` 端点经全局中间件保护，两种方式二选一：

- **个人访问令牌（agent 用这个）**：`Authorization: Bearer <mb_ 令牌>`。令牌在 Web 端 Settings 创建/吊销。
- 会话 Cookie（仅 Web 浏览器场景）。

## 服务地址

- 局域网：`http://10.10.10.20:21101`
- 公网（npm 反代）：`https://mbf.zcore.top`

## 接口清单

### 归档查询（agent 核心，提交前必调）

```
GET /api/agent/archive/query?q=<番号|关键词>&limit=20
```

- 子串匹配整理记录的 `file_name`/`target_path` 与本地任务的 `name`/`info_hash`
- 同一 info_hash 以整理记录为准去重（归档事实优先于生命周期）
- 命中类型：`archived`（已归档）/ `in_flight`（在途）/ `failed`（失败）/ `skipped`（跳过）
- 每条命中含 `title / library_name / path / info_hash / occurred_at`
- 数据库异常时降级为空命中（`total: 0`），不会 500

返回示例：

```json
{
  "code": 0,
  "message": "归档查询成功",
  "data": {
    "query": "MUDR-359",
    "total": 1,
    "hits": [
      {
        "kind": "archived",
        "title": "MUDR-359.mp4",
        "library_name": "xx-MOODYZ",
        "path": "/媒体/xx-MOODYZ/MUDR-359/MUDR-359.mp4",
        "info_hash": "…",
        "occurred_at": "2026-10-18T12:00:00"
      }
    ]
  }
}
```

**解读口径**：`total=0` → 未收录，可以找资源；`archived` 命中 → 已有，报告用户并附路径；`in_flight` → 正在下载，不要重复提交；`failed` → 已尝试过但失败，报告失败历史，由用户决定是否重试。

### 提交下载

```
POST /api/tasks
{"magnet": "magnet:?xt=urn:btih:…", "library_name": "xx-MOODYZ", "name": "MUDR-359"}
```

- `library_name` 必须与媒体库配置完全一致，先 `GET /api/libraries` 获取
- `name` 建议填规范番号——归档查询按它做子串匹配，填写质量直接影响去重效果
- 库不存在返回 404；云端/落库失败返回 500

### 观测（追踪自己提交的任务）

| 接口 | 用途 |
|---|---|
| `GET /api/tasks` | 任务列表（数值状态口径：2=完成、负数=失败、其余=进行中） |
| `GET /api/organize/records` | 整理记录（确认「归档到哪了」的事实来源） |
| `GET /api/libraries` | 媒体库列表（含 system / xx-片商 类型） |
| `GET /api/status` | 服务与监控健康状态（提交前探活） |

## 标准工作流

```
用户给番号 → 归档查询去重 → （未收录）搜索磁链 → 列候选给用户
→ 用户确认 → POST /api/tasks → 轮询 GET /api/tasks 追踪
→ 完成后用归档查询/整理记录回报归档路径
```

搜索环节的已验证做法（可用源、访问方式、注意事项）见
[docs/search-playbook.md](docs/search-playbook.md)。

## 错误处理约定

| HTTP | 含义 | agent 应对 |
|---|---|---|
| 401 | 未认证/令牌无效 | 检查 Bearer 头；令牌可能已被吊销 |
| 403 | CSRF 校验失败 | Bearer 令牌不需要 CSRF；出现即说明误用了会话 Cookie 方式 |
| 404 | 媒体库不存在 | 用 `GET /api/libraries` 核对库名 |
| 422 | 参数校验失败 | 检查必填参数 |
| 500 | 云端/落库失败 | 原样报告 message 给用户，不要自动重试提交 |
