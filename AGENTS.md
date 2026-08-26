# MediaBridge

MediaBridge 单仓库（monorepo）工作区：管理 115 网盘离线下载与媒体文件整理。

## 仓库结构

```text
apps/
  server/       FastAPI 服务端
  web/          React + Vite Web 应用
  extension/    浏览器扩展（磁力捕获）
  agent/        本地 Agent（预留）
packages/
  api-contracts/  共享 API 契约（预留）
infra/           Docker + nginx + supervisor 部署配置
```

## Agent skills

### Issue tracker

工单跟踪在 GitHub Issues（AkaiShuichi7/media-bridge），通过 `gh` CLI 读写。见 `docs/agents/issue-tracker.md`。

### Triage labels

使用默认五标签：needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix。见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文布局：根级 `CONTEXT.md` 词汇表 + `docs/adr/` 决策记录，由 `/domain-modeling` 按需懒创建。见 `docs/agents/domain.md`。

## 约定

- 提交遵循 Conventional Commits（feat/fix/chore...），小步提交
- 子应用各自的详细说明见 `apps/<app>/AGENTS.md`（如 `apps/server/AGENTS.md`）
