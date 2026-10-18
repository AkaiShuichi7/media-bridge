# MediaBridge 领域词汇表（GLOSSARY）

> 本文件是领域词汇的权威来源；项目背景与结构见 `CONTEXT.md`，架构决策见 `docs/adr/`（按需懒创建）。
> `_Avoid_` 列出不应再使用的同义/废弃写法。

## Language

### 云盘与任务

**离线任务（Offline Task）**:
提交给 115 云盘的下载任务，以 info_hash 标识，经历 added → downloading → completed 的生命周期。
_Avoid_: 下载任务、BT 任务

**番号（Fanhao）**:
媒体资源编号（如 MUDR-359），是目标路径生成与文件名规范化的核心依据。
_Avoid_: 编号、序列号

**临时目录（Temp Directory）**:
路径最后一级为番号的目录；生命周期与单个任务绑定，不进入路径缓存。
_Avoid_: 番号目录（口语可用，文档用规范词）

### 服务端模块

**PathCache**:
路径 → 115 目录 ID 的持久化缓存（app/services/path_cache.py），get/set/cleanup 三方法接口，session 工厂注入。番号目录的拒写规则收敛在 set 内部。
_Avoid_: PathIdCacheService（已删除的旧死模块名，勿再用）

**P115Client**:
115 HTTP API 的异步适配器（app/services/p115_client.py）：重试/退避/限速 + 路径遍历编排。路径解析的纯函数（normalize_path / is_temp_directory）由 PathCache 模块提供，数据库只经 PathCache 触达。实例由 AppContainer 独占创建持有（无类级单例）。
_Avoid_: p115_client（指模块文件时可用，指类时用规范名）；get_client 单例入口（已删除）

**CloudService**:
云盘能力的中立契约（app/services/cloud/base.py）。seam 两侧只流通 CloudFile / CloudTask 中立类型，115 原始 dict 形状与原生状态码被 P115CloudService 适配器挡在 seam 之内；调用方不得出现 fid/n/sz/cid 等短名字段或 `status == 2` 之类裸数值比较。

**CloudTaskStatus**:
云任务的中立状态枚举（PENDING / DOWNLOADING / COMPLETED / FAILED），由适配器从 115 原生状态码翻译而来。对外 API 数值口径（2=完成、负数=失败）由 schemas/api.py 映射层统一换算。
_Avoid_: 直接读写 115 原生状态 int

**OfflineTaskService**:
离线任务领域服务（app/services/offline_task_service.py）。添加流程：库校验 → 目录解析 → 云端建任务 → 本地 UPSERT → 失败补偿回滚；生命周期流程：轮询集合查询、整理编排与四态迁移（completed / organize_failed / organize_skipped / failed）、失败任务记录、查询侧（失败原因与本地状态）。路由层与监控器只做协议转换/轮询比对。
_Avoid_: 把状态迁移 SQL 写回 monitor 或路由层

**TaskMonitor**:
后台轮询器（app/tasks/monitor.py）：拉取轮询集合 → 比对中立状态 → 调用 OfflineTaskService。不持有业务状态，不直接触达数据库。

**OfflineTaskRef**:
待整理任务引用类型（app/services/file_organizer.py）：info_hash / name / path_id / download_path_id 四字段，取代旧的 5 键裸 dict task_info。
_Avoid_: task_info dict

**OrganizeResult**:
单次整理结果统计类型（success/failed/skipped 计数 + errors + message）；message 仅在 0 成功 0 失败路径携带可读原因，供领域服务区分「全跳过」结局。
_Avoid_: message 字符串约定的裸 dict 返回

### 扩展（apps/extension）

**磁力捕获（Magnet Capture）**:
从任意网页的用户复制行为中提取 magnet 链接的管线：page-hook（MAIN world）→ capture（isolated）→ service worker → popup。判定规则唯一实现于 magnet.js，待发送状态与 badge 同步唯一拥有者是 captured-state.js。
