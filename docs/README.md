# 文档索引

按「要解决什么问题」分目录。根目录的 [CLAUDE.md](../CLAUDE.md)（开发约定与踩坑）、
[DESIGN.md](../DESIGN.md)（视觉规范）、[UX-CONTRACT.md](../UX-CONTRACT.md)（交互契约）是现行规范，
不放进 docs，改前端或改约定时与这里的文档同步更新。

## design/ —— 设计与决策：为什么这样做

| 文档 | 内容 | 何时读 |
| --- | --- | --- |
| [业务数据运营平台公共基础框架设计](design/业务数据运营平台公共基础框架设计.md) | 服务拆分、权限模型、会话、审计的设计基线（V1.1） | 新增服务、改鉴权或会话前 |
| [实现决策](design/实现决策.md) | 设计没固定到具体值的实施细节：端口、库账号、镜像版本、各阶段取舍 | 想知道「为什么是这个值」 |
| [业务表主键与导入导出分析](design/业务表主键与导入导出分析.md) | 六张业务表的主键、导入覆盖规则、待业务确认的调整方案 | 改导入导出或主键规则前 |

## guides/ —— 操作手册：怎么做

| 文档 | 内容 |
| --- | --- |
| [UI 开发与复用指南](guides/UI开发规范.md) | 新页面接入步骤、默认列清单、列宽、验收与文档同步 |
| [配置说明](guides/配置说明.md) | `.env` 字段、会话与导入导出限制、爬虫监测 v1/v2 同步与口径升级 |
| [部署与维护](guides/部署与维护.md) | 本地启动、备份恢复、指标告警、会话清理、客户端 IP 信任前提 |

## 进度与验收记录

- [开发进度](开发进度.md)：各阶段实际改动与验证结果，按时间追加。
- [reviews/](reviews)：按「主题-日期」存放的验收证据（截图、接口与性能实测 JSON），带 README 的有文字结论：
  - [crawler-monitoring-2026-09-22](reviews/crawler-monitoring-2026-09-22/README.md)：爬虫监测首版验收
  - [crawler-monitoring-2026-09-23-release](reviews/crawler-monitoring-2026-09-23-release/README.md)：名称口径升级的发布与真实增量核对
  - `crawler-monitoring-v2-2026-09-23/`、`system-rbac-2026-09-23/`：仅截图

## 资料与生成物

- [openapi/](openapi)：`make export-openapi` 从运行中服务导出，不手改。`scripts/scan_scope.py` 按这里的路径检查。
- [excel/](excel)：用户提供的业务原始 Excel（信源、政策、场景的导入源文件）。
  省市区编码的原始 SQL 在 `services/codebook-service/data/cfg_all_area_code_info.sql`，`make seed-area-codes` 直接读它。

## archive/ —— 已完成或已被取代，只供追溯

- [Cursor 公共框架开发计划](archive/Cursor公共框架开发计划.md)：P0～P6 分阶段计划与提示词，已全部执行完。
- [开发约定](archive/开发约定.md)：已并入 CLAUDE.md。
- [design-qa](archive/design-qa.md)、[ui-review-2026-09-20/](archive/ui-review-2026-09-20)：早期 UI 验收过程，其中部分方案已被用户否定。

## 放置规则

- 长期有效的「为什么」放 `design/`；可照着执行的步骤放 `guides/`；一次性验收证据放 `reviews/<主题>-<日期>/`。
- 文档被取代时移到 `archive/`，在开头注明取代它的文档，不要直接删除。
- 移动或改名后用 `git grep` 查旧路径，代码注释和测试里也有引用。
