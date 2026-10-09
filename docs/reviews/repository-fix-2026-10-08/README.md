# 2026-10-08 审查修复记录

审查原文留在 [repository-audit-2026-10-08](../repository-audit-2026-10-08/README.md)，没有改写。下面只记录这次修复、验证和还没做完的事。

验证时间：2026-10-08。本地 `make test-unit` 与 `make check` 已通过。服务器发布在写这份记录时尚未完成，不能把下面任何一项说成已经在服务器上生效。

## 测试

| 检查 | 结果 |
| --- | --- |
| `make test-unit` | 公共包 60、IAM 55、审计 18、码表 50、政策 127，共 310 passed、11 skipped；前端 vitest 12 个文件、68 passed |
| `make check` | ruff、mypy、前端类型检查、生产构建、lint、密钥扫描、OpenAPI 对比均通过 |
| 属主脚本 | 一次性 Postgres 17.2 容器中，表和序列属主改为 `app_user` 后，`SET ROLE app_user` 可以 `ALTER TABLE`。容器已删除，没有连接业务库 |
| P6 / Playwright | 未运行 |

11 个 skipped 仍是原有集成用例，不算通过。Element Plus 包体积告警仍在，构建没有失败。

## 逐项

| 编号 | 修改 | 验证 | 剩余 |
| --- | --- | --- | --- |
| F01 | 宽限期外重放先 `commit` 撤销和 `auth.refresh.replayed`，再返回 401 | `services/iam-service/tests/test_refresh_replay_persist.py`：另一个会话能看到 `revoked_at` 和审计事件，新刷新令牌也不能继续使用。宽限期内重复使用返回成功且不撤销 | 未在服务器上重放 |
| F02 | 上传路由在权限依赖之后才解析文件；无 Bearer 或 Content-Length 超限的请求在中间件直接拒绝；网关 `request-limit` 为 21233664 字节；Excel 限制解压 64MB、10 万行、128 列、同时 2 个解析 | `test_upload_before_auth.py`、`test_body_limit.py`、`test_excel_limits.py` | 未对服务器发送大文件 |
| F03 | 六张表 PATCH 使用独立模型和 `exclude_unset=True`。空字符串仍表示清空；政策类型、网站名称、政策名称、政策原文名称清空时返回 422 | 政策、码表 HTTP 测试确认只把提交的字段交给更新函数 | 未在浏览器里逐表点保存 |
| F04 | 增加文件 Provider 的 HTTPS 配置、8443 端口和续期脚本。Cookie Secure 只在叠加 `docker-compose.https.yml` 后打开 | 配置文件已通过 Compose 语法检查。证书尚未签发，线上入口仍是 HTTP | 要在服务器上完成 HTTP-01 和证书续期后才能切换。PostgreSQL `5433` 绑定未改 |
| F05 | 四个 Dockerfile 复制 `uv.lock`，使用 uv 0.12.13 和 `uv sync --frozen`，并导出 `/opt/requirements.frozen.txt` | 本机 `uv export --frozen` 可以读政策服务锁文件。镜像尚未在服务器重建 | 构建时才能确认镜像内清单 |
| F06 | Compose 显式传入登录限流、会话保留、导入导出、爬虫阈值、Cookie、Token 时长和各服务 `ENVIRONMENT`。政策 API 与 worker 使用同一组阈值。Redis 不再映射宿主机 | `public_settings` 测试确认输出不含数据库地址和密钥。容器内白名单要等发布后执行 | 发布前看不到容器内实际值 |
| F07 | `scripts/migrate_check.sh` 使用 `set -euo pipefail`，不再把 `alembic check` 送进 `tail` | `scripts/test_migrate_check.sh`：假命令退出 42 时脚本也退出 42 | 未对线上四库再跑 `alembic check` |
| F08 | `git ls-files -z` 按 NUL 切分，空项丢弃 | `scripts/test_scan_scope.py` 确认中文路径会被扫描，临时仓库里的中文文件名密钥会被报出。`make check` 的扫描通过 | 正则仍只覆盖少数形式，不是完整凭据审计 |
| F09 | P6 把刷新宽限期设为 0，验收在 401 之后再使用新令牌，期望仍然 401。宽限期内成功由 F01 单测覆盖 | 单测通过。整套 P6 未跑 | 隔离栈验收未执行 |
| F10 | 恢复后只改当前库 public 的表、序列、视图和函数属主，再 GRANT。继续拒绝业务库名。审计清理改为 `.venv/bin/python` | 一次性容器验证属主和 `ALTER`。没有对业务库或隔离库执行 `pg_restore` | 未做“恢复后应用账号跑下一次迁移”的整库演练 |
| D01 | README 改为以部署手册为日常入口，并写明政策、码表、爬虫和调度已经接入 | 文档审阅 | 无 |
| D02 | 四份 OpenAPI 已按本地应用重新导出。`make check` 会再导出并比较 | `openapi_matches_apps`；IAM 26、审计 7、码表 21、政策 35 条路径 | 无 |
| D03 | 导入导出分析改为：下载带已生效筛选，最多 10 万行。候选主键方案仍标为未确认 | 文档审阅 | 无 |
| D04 | UI 规范改为信源 13 列、解读 26 列，发布步骤改指向部署手册。任务调度去掉本机 8080 命令。DESIGN 不再把爬虫写成未完成 | 对照 `SourceList.vue`、`InterpretationList.vue` 的静态列 | 未做视觉验收 |
| D05 | 公共包说明、CLAUDE 的 NONE/租约、实现决策第 20 节、框架设计的现行指针、开发进度追加 | 文档审阅 | 历史章节保留原表述 |
| D06 | 新增 `traefik.https.yml`、`dynamic.https.yml`、`docker-compose.https.yml`。旧 Docker Provider 模板标明不要直接替换 | Compose 语法检查通过 | 未在服务器加载 |
| D07 | `scripts/backup_business.sh` 只导出业务四库。恢复白名单未删除 | 脚本审阅。尚未在服务器执行导出 | 还没有恢复演练记录 |
| D08 | `docs/README.md` 写明 archive 和带日期的 reviews 只供追溯 | 未修改那些历史文件 | 无 |

## 发布前状态

代码和文档在本机工作区，尚未提交 Git，也尚未同步到服务器。回滚准备是：发布前导出四库，并为当时的服务镜像打标签。没有新增数据库迁移。
