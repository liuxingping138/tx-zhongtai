# platform-common

业务数据运营平台公共基础代码包（非独立服务）。各服务通过 `uv` 以本地路径依赖方式引用固定版本，禁止在此包中放置任何服务的 ORM 模型或业务表结构。

提供内容：

- `platform_common.responses`：统一成功/失败响应包装、分页结构。
- `platform_common.errors`：统一异常基类、错误码枚举、FastAPI 异常处理器注册函数。
- `platform_common.request_context`：请求 ID 中间件与上下文获取。
- `platform_common.logging_setup`：结构化日志初始化与敏感字段脱敏处理器。
- `platform_common.health`：`/health/live`、`/health/ready` 路由构建器。
- `platform_common.outbox`：Outbox 仓储、认领和重放。默认租约 5 分钟。IAM 自己的仓储使用 30 秒。
- `platform_common.authz` / `platform_common.service_authz`：业务服务调用 IAM `/internal/v1/authorize`。JWT 校验在 IAM，不在这个包里。
- `platform_common.filters` / `platform_common.options`：列表筛选和筛选项预览。
- `platform_common.excel` / `platform_common.columns`：Excel 读写、表头匹配。解析有解压大小、行列数和并发上限。
- `platform_common.http_utils` / `platform_common.body_limit`：统一响应、上传大小限制。上传在鉴权通过之后才解析。
- `platform_common.xlsx_writer`：不经 openpyxl、直接写只含文本的 xlsx，业务导出走它。
- `platform_common.config` / `platform_common.public_config`：服务配置基类（生产环境拒绝示例密钥）、容器里只打印白名单参数。
- `platform_common.database`：`create_service_engine`，全部服务的连接池与 PostgreSQL 超时只在这里设（见 `docs/design/实现决策.md`「连接预算与超时」）。
- `platform_common.audit_emit`：`AuditEmitter`，审计入队与后台投递。
- `platform_common.internal_calls`：服务间 `/internal/*` 调用的请求头。
- `platform_common.route_audit`：路由安全分级体检（`audit_routes`、`iter_api_routes`、`mark_permission_dependency`；`@classified` 在 `service_authz`）。
- `platform_common.scheduler`：每日定时任务引擎（队列、leader 锁、执行通道、重试、页面接口），见 `docs/guides/任务调度.md`。
- `platform_common.clock` / `orm_base` / `enums` / `actors` / `redaction` / `similarity`：时钟与北京时间、ORM Base、公共枚举、操作者身份、日志脱敏键、名称字面相似度。

不允许通过本包导入任何服务的数据库模型或业务表。
