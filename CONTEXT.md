# MediaBridge

管理 115 网盘离线下载与媒体文件整理的单仓库产品：Web 应用、浏览器扩展、（预留的）本地 Agent 共享同一个服务端。

领域词汇的权威来源是根级 [GLOSSARY.md](GLOSSARY.md)；本文件只保留项目背景与结构，不承载词条。

## 结构

- `apps/server`：FastAPI + SQLAlchemy async + SQLite 服务端
- `apps/web`：React + Vite Web 应用
- `apps/extension`：Chrome MV3 浏览器扩展（磁力捕获）
- `apps/agent`：本地 Agent（预留）
- `packages/api-contracts`：共享 API 契约（预留）
- `infra/`：Docker + nginx + supervisor 部署配置

## 架构主轴

- **CloudService seam**：云盘能力中立契约，115 原始 dict 与状态码不出 `P115CloudService` 适配器
- **OfflineTaskService**：离线任务的添加与生命周期状态迁移唯一所有者；路由与监控器只做协议转换
- **可追溯性**：任务状态准确、文件按预期归档、异常可解释（error_message 落库 + 整理记录）
