# MediaBridge

管理 115 网盘离线下载与媒体文件整理的单仓库产品：Web 应用、浏览器扩展、（预留的）本地 Agent 共享同一个服务端。

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
115 HTTP API 的异步适配器（app/services/p115_client.py）：重试/退避/限速 + 路径遍历编排。路径解析的纯函数（normalize_path / is_temp_directory）由 PathCache 模块提供，数据库只经 PathCache 触达。
_Avoid_: p115_client（指模块文件时可用，指类时用规范名）

**CloudService**:
云盘能力的中立契约（app/services/cloud/base.py）。seam 两侧只流通 CloudFile / CloudTask 中立类型，115 原始 dict 形状被 P115CloudService 适配器挡在 seam 之内；调用方不得出现 fid/n/sz/cid 等短名字段。

**OfflineTaskService**:
「添加离线任务」的领域服务（app/services/offline_task_service.py）：库校验 → 目录解析 → 云端建任务 → 本地 UPSERT → 失败补偿回滚。路由层只做协议转换。

### 扩展（apps/extension）

**磁力捕获（Magnet Capture）**:
从任意网页的用户复制行为中提取 magnet 链接的管线：page-hook（MAIN world）→ capture（isolated）→ service worker → popup。判定规则唯一实现于 magnet.js，待发送状态与 badge 同步唯一拥有者是 captured-state.js。
