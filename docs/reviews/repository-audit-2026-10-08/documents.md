# 文档逐项核对清单

基于审查开始时的 31 份 Markdown。配套 4 份 OpenAPI 的差异见 openapi-diff.json。图片、Excel、SQL 为原始资料/历史证据，不作为现行操作文档。

| 文档 | 结论 |
| --- | --- |
| `CLAUDE.md` | 大体一致；租约/档位措辞需修正（D05） |
| `DESIGN.md` | 主体与源码对应；旧模块措辞需清理；未做视觉验收（D04） |
| `README.md` | 需更新：开发入口、业务状态、初始化步骤（D01） |
| `UX-CONTRACT.md` | 主体与源码对应；依赖的 OpenAPI 过期（D02/D04） |
| `docs/README.md` | 需更新：OpenAPI 生成和检查方式（D02） |
| `docs/archive/Cursor公共框架开发计划.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/archive/design-qa.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/archive/ui-review-2026-09-20/IMPLEMENTATION.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/archive/ui-review-2026-09-20/REVIEW.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/archive/ui-review-2026-09-20/column-widths/REVIEW.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/archive/ui-review-2026-09-20/full-width/REVIEW.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/archive/ui-review-2026-09-20/login/README.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/archive/ui-review-2026-09-20/toolbar-revision.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/archive/开发约定.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/design/业务数据运营平台公共基础框架设计.md` | 设计基线；需关联现行配置/权限决策，不作运行手册（D05） |
| `docs/design/业务表主键与导入导出分析.md` | 导入规则大体一致；全表导出说法过期，候选方案保留待确认（D03） |
| `docs/design/实现决策.md` | 历史决策有效；缺后续变更取代索引（D05） |
| `docs/guides/UI开发规范.md` | 需更新：13/26 列、服务器入口（D04） |
| `docs/guides/任务调度.md` | 调度规则大体一致；发布命令和入口过期（D04） |
| `docs/guides/部署与维护.md` | 服务器主入口正确；Redis实际映射、配置变量、业务备份需补正（D07/F06） |
| `docs/guides/配置说明.md` | 参数在 Settings 存在，但 Compose 未全量透传（F06） |
| `docs/reviews/crawler-monitoring-2026-09-22/README.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/reviews/crawler-monitoring-2026-09-23-release/README.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/reviews/system-access-2026-09-24/README.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/reviews/task-scheduler-2026-09-29/README.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/reviews/workspace-direction-2026-09-24/README.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/reviews/workspace-direction-2026-09-24/header-comparison.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/reviews/workspace-direction-2026-09-24/preview-history.md` | 历史记录：保留日期与当时结果，不应用作当前服务器操作步骤（D08） |
| `docs/开发进度.md` | 历史流水；未完整记录服务器迁移和10月发布，不能作当前验收（D05） |
| `frontend/src/assets/brand/README.md` | 本地 SVG 文件和导航使用一致；未重新核验外部来源URL |
| `packages/platform-common/README.md` | 需更新：auth_client 不存在、公共能力缺项（D05） |
