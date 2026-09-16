# platform-common

中台公共基础代码包（非独立服务）。各服务通过 `uv` 以本地路径依赖方式引用固定版本，禁止在此包中放置任何服务的 ORM 模型或业务表结构。

提供内容：

- `platform_common.responses`：统一成功/失败响应包装、分页结构。
- `platform_common.errors`：统一异常基类、错误码枚举、FastAPI 异常处理器注册函数。
- `platform_common.request_context`：请求 ID 中间件与上下文获取。
- `platform_common.logging_setup`：结构化日志初始化与敏感字段脱敏处理器。
- `platform_common.health`：`/health/live`、`/health/ready` 路由构建器。
- `platform_common.outbox`：Outbox 事件写入的基础数据结构与仓储接口（不含具体业务事件类型）。
- `platform_common.auth_client`：JWT 校验与内部 `/internal/v1/authorize` 调用客户端（P2/P3 阶段完善）。

不允许通过本包导入任何服务的数据库模型或业务表。
