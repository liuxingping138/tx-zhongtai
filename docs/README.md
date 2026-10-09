# 文档索引

按「要解决什么问题」分目录。根目录的 [CLAUDE.md](../CLAUDE.md)（开发约定与踩坑）、
[DESIGN.md](../DESIGN.md)（视觉规范）、[UX-CONTRACT.md](../UX-CONTRACT.md)（交互契约）是现行规范，
不放进 docs，改前端或改约定时与这里的文档同步更新。

## design/ —— 设计与决策：为什么这样做

| 文档 | 内容 | 何时读 |
| --- | --- | --- |
| [业务数据运营平台公共基础框架设计](design/业务数据运营平台公共基础框架设计.md) | 服务拆分、权限模型、会话、审计的设计基线（V1.1） | 新增服务、改鉴权或会话前 |
| [实现决策](design/实现决策.md) | 设计没固定到具体值的现行实施细节：端口、库账号、镜像版本、鉴权与审计参数、P6 验收 | 想知道「为什么是这个值」 |
| [业务表主键与导入导出分析](design/业务表主键与导入导出分析.md) | 六张业务表的主键、导入覆盖规则、待业务确认的调整方案 | 改导入导出或主键规则前 |

## guides/ —— 操作手册：怎么做

| 文档 | 内容 |
| --- | --- |
| [UI 开发与复用指南](guides/UI开发规范.md) | 新页面接入步骤、默认列清单、列宽、验收与文档同步 |
| [配置说明](guides/配置说明.md) | `.env` 字段、会话与导入导出限制、爬虫监测 v1/v2 同步与口径升级 |
| [部署与维护](guides/部署与维护.md) | Mac 推送 GitLab，`scripts/sync-to-server.sh` 同步到 `1.119.196.77` 构建；服务器上跑 P6 验收、备份恢复、指标告警、会话清理 |
| [任务调度](guides/任务调度.md) | 每日增量计划、后台执行、重试及部署验证 |

## 验收记录

- [reviews/](reviews)：按「主题-日期」存放的验收证据（截图、接口与性能实测 JSON），带 README 的有文字结论：
  - [system-access-2026-09-24](reviews/system-access-2026-09-24/README.md)：系统管理三模块与个人设置的 UI/UX 复查和调整
  - [crawler-monitoring-2026-09-22](reviews/crawler-monitoring-2026-09-22/README.md)：爬虫监测首版验收
  - [crawler-monitoring-2026-09-23-release](reviews/crawler-monitoring-2026-09-23-release/README.md)：名称口径升级的发布与真实增量核对
  - [task-scheduler-2026-09-29](reviews/task-scheduler-2026-09-29/README.md)：任务调度的空库迁移、并发/重试测试和真实增量结果
  - [repository-release-2026-10-09](reviews/repository-release-2026-10-09/README.md)：审查修复与发布验收
  - `crawler-monitoring-v2-2026-09-23/`、`system-rbac-2026-09-23/`：仅截图

## 资料与生成物

- [openapi/](openapi)：`make export-openapi` 在本地导入 FastAPI 应用后导出，不连接正在运行的服务，也不手改。`make check` 会重新导出并比较差异。
- [excel/](excel)：用户提供的业务原始 Excel（信源、政策、场景的导入源文件）。
  省市区编码的原始 SQL 在 `services/codebook-service/data/cfg_all_area_code_info.sql`，`make seed-area-codes` 直接读它。

`reviews/` 是带日期的一次性验收证据，保留当时的端口、测试数量和界面，不当作现行操作步骤。现行做法以 `guides/` 和根目录规范为准。

## 放置规则

- 长期有效的「为什么」放 `design/`；可照着执行的步骤放 `guides/`；一次性验收证据放 `reviews/<主题>-<日期>/`。
- 文档只写现行做法：被取代或过时的内容直接删除，不另设归档，历史留在 git 里。
- 移动或改名后用 `git grep` 查旧路径，代码注释和测试里也有引用。
