# tx-zhongtai 全仓审查与优化建议报告

- 审查日期：2026-11-18
- 审查基线：`main` @ `2f828d2`
- 范围：`packages/platform-common`、`services/*`（iam / audit / codebook / policy / ai / tender / thinktank）、`frontend/`、`deploy/`、`scripts/`、`.githooks/`、`tests/`、`docs/`
- 方法：只读审查代码与配置，没有在服务器上运行，也没有改动任何代码。每条结论都注明文件与行号。需要在环境里再确认的条目标了「待验证」。

---

## 一、执行摘要

### 1.1 总体健康度

整体工程成熟度**较高**。这个仓库没有 CI，但用 git 钩子、`make check`、路由安全分级体检、筛选条件一致性测试和迁移漂移检查，把大部分约定固化成了自动检查，同规模项目里少见。后端分层和服务边界清晰，鉴权依赖不可用时一律返回 503，Outbox 带租约和退避，几个只读外部源都有明确的只读边界。

主要风险不在业务代码，而在三处：

1. **部署暴露面**：数据库对公网开放；
2. **新加的智库服务（thinktank-service）没跟上周边配套**：备份、文档、钩子、CSP 都还没覆盖到它；
3. **合规缺口**：招中标导出不留审计。

| 维度 | 评价 | 说明 |
| --- | --- | --- |
| 架构与边界 | 良 | 每个服务一个库、公共能力下沉 platform-common、import-linter 强制分层；thinktank 的 Outbox 在 API 进程里跑，和其他服务不一致 |
| 后端质量与性能 | 良 | 大表分天聚合、部分索引、`literal_execute` 等细节到位；连接池没有统一预算，也没有语句超时 |
| 前端 | 良 | `strict` + `noUncheckedIndexedAccess`、路由懒加载、分块缓存、单测覆盖率下限 93%；智库 PDF 预览可能被 CSP 拦截 |
| 安全与合规 | 中 | 鉴权、CSRF、Cookie、请求头清洗都做得扎实；但 Postgres 超级用户经公网 5433 可达，招中标导出无审计 |
| 测试与质量门 | 良 | 覆盖率下限只升不降、路由体检、OpenAPI 契约测试；tender 和 thinktank 的测试偏薄，pre-commit 漏了 thinktank |
| 运维与可维护性 | 中 | 镜像全部锁版本、依赖装时校验哈希、设了内存上限；备份漏掉 thinktank，没有指标体系，容器没做最小权限加固 |

### 1.2 主要优点

- **公共能力集中**：鉴权、Outbox、审计入队、Excel、筛选、调度器都在 `packages/platform-common/platform_common/`，新服务直接复用（thinktank 的 `app/common/security.py`、`app/common/audit_emit.py` 就是这么接入的）。
- **鉴权不会放行**：`platform_common/authz.py:85-102` 把网络错误、凭据被拒、响应异常统一转成 `DependencyUnavailableError`（503）。`route_audit` 体检强制每条路由声明安全分级。
- **生产拒绝示例密钥**：`platform_common/config.py:43-56` 会检查所有 secret / key / password 字段和连接串里的口令，带 secret 的字段还不能为空。
- **网关加固**：`deploy/gateway/traefik.https.yml` 设了 `aliasHeadersStrategy: delete`，防止客户端伪造来源 IP；Traefik 锁在 3.7.14，注释写明了不能回退的 CVE 原因。
- **镜像可复现**：Python 依赖用 `uv export --frozen` 加 `--require-hashes` 安装（如 `services/thinktank-service/Dockerfile`），容器以非 root 的 `appuser` 运行。
- **审计库防篡改**：审计库归超级用户所有，应用账号只有 SELECT / INSERT，清理账号单独隔离（见 `Makefile` 中的 `migrate_audit` 宏）。

### 1.3 主要风险（Top 5）

| # | 级别 | 风险 |
| --- | --- | --- |
| 1 | P0 | PostgreSQL 5433 对公网开放，超级用户可从公网登录，能进全部业务库 |
| 2 | P0 | 业务备份与恢复脚本漏掉 `thinktank_db` 和 `thinktank-data` 卷，智库数据没有备份 |
| 3 | P1 | 招中标导出（每次最多 10 万行）和所有查询都不写操作日志，是平台唯一不留审计的数据出口 |
| 4 | P1 | 各服务连接池加起来上限约 180 条，Postgres 默认只允许 100 条；而且没有语句超时 |
| 5 | P1 | 招中标源库的只读只靠应用层的字符串前缀检查，真正的保障取决于数据库账号权限，仓库里查不到 |

---

## 二、分级问题清单

字段说明：**类别**／**位置**／**问题与影响**／**建议**／**工作量与风险**（工作量：S ≤ 半天，M 1–3 天，L ≥ 1 周）。

### P0 · 严重

#### P0-1 PostgreSQL 超级用户经公网 5433 可达

- **类别**：安全 / 部署
- **位置**
  - `deploy/compose/docker-compose.yml:59-65`：postgres 同时接入 `gateway` 网络，端口按 `${POSTGRES_BIND_ADDR}` 映射
  - `.env.example:15-18`：注释写着「Navicat 从公网连接时设为 0.0.0.0」
  - `docs/guides/部署与维护.md:17`、`:288`：确认云安全组已放行 5433，「公网 `36.134.128.137:5433`，供 Navicat 连接」
  - `Makefile` 的 `migrate_audit` 宏注释：「5433 对公网开放；它能进全部五个库」
  - `docs/guides/系统全面审查与整改报告.md:73`：上一轮审查把这一项定为「低危 / 部署建议」，至今没有关闭
- **问题与影响**：数据库只靠口令防护，暴露在公网，长期面对口令爆破和 PostgreSQL 漏洞利用。超级用户一旦失守，审计库「只增不改」的设计也随之失效（超级用户可以删表），全部业务数据都可能泄露或被篡改。这是全仓影响面最大的一项。
- **建议**
  1. 把 `.env` 里的 `POSTGRES_BIND_ADDR` 改回 `127.0.0.1`，Navicat 改走 SSH 隧道（Navicat 自带 SSH 通道）。
  2. 如果确实需要直连，至少把安全组 5433 收窄到办公网出口 IP，并在 `pg_hba.conf` 里限制超级用户只能从本机或容器网段登录：
     ```conf
     # 超级用户只允许本机 / Docker 网段
     host all postgres 127.0.0.1/32   scram-sha-256
     host all postgres 172.16.0.0/12  scram-sha-256
     host all postgres 0.0.0.0/0      reject
     ```
  3. 给 Navicat 单独建一个只读账号（`GRANT SELECT`），不要用应用账号或超级用户。
  4. 把上一轮报告的 SEC-05 改为高危并跟踪到关闭。
- **工作量与风险**：S。改绑定地址会让现在用 Navicat 直连的人连不上，需要提前通知并发 SSH 隧道配置说明。

#### P0-2 备份与恢复漏掉智库服务的库和文件卷

- **类别**：运维 / 数据安全
- **位置**
  - `scripts/backup_business.sh:32`：只循环 `iam / audit / policy / codebook / ai` 五个库；第 44 行只打包了 `ai-data` 卷
  - `scripts/backup.sh:20`、`scripts/restore.sh:24`：`SERVICES="iam audit policy codebook ai"`
  - `deploy/compose/docker-compose.yml:23`、`:468`：智库有独立的 `thinktank-data` 卷，没配 MinIO 时知识文件就落在这里（`services/thinktank-service/app/core/storage.py:186-248`）
- **问题与影响**：智库知识库的元数据、收藏、操作日志（`thinktank_db`），以及本地存储模式下的原始文件，都**完全不在备份里**。磁盘故障或误删卷时无法恢复。P6 的恢复演练也覆盖不到它，所以这个缺口不会被发现。
- **建议**
  ```bash
  # backup_business.sh
  for pair in ... "ai:$AI_DB_NAME" "thinktank:$THINKTANK_DB_NAME"; do
  ...
  $BACKUP_COMPOSE exec -T thinktank-service tar -C /data/thinktank -czf - . > "$TMP/thinktank-files.tar.gz"
  ```
  同步修改 `backup.sh`、`restore.sh` 的 `SERVICES`、`SHA256SUMS` 的文件清单、`scripts/verify_restore_p6.py`，把备份格式版本升到 `v3`。如果生产环境用的是 MinIO，要写明 MinIO 桶由谁备份。
- **工作量与风险**：S。风险很低，只增加备份内容。

### P1 · 高

#### P1-1 招中标导出与查询没有任何审计

- **类别**：安全合规 / 审计缺口
- **位置**
  - `services/tender-service/app/api/routes.py:44-47`：导出路由只挂了权限依赖，没有取 `actor`
  - `services/tender-service/app/application/records.py:91-106`：`export_records` 不记录任何审计事件
  - 对照：政策、码表、AI 的导出都有审计，如 `services/policy-service/app/policy/application/interpretations.py:381`、`services/codebook-service/app/application/area_codes.py:277`、`services/ai-service/app/application/batch_runs.py:291`
- **问题与影响**：招中标是体量最大的外部数据源，单次最多能导出 10 万行，但「谁、什么时候、按什么条件导出了多少行」在操作日志里查不到。出现数据外泄时无从追溯，也和平台「业务写操作与数据导出必留痕」的口径不一致。
- **建议**：tender-service 没有自己的 Postgres，有两种做法。
  1. **推荐**：给 tender 建一个只放 `tender_outbox` 的小库，复用 `platform_common.audit_emit.AuditEmitter`，和其他服务完全一致。
  2. 过渡方案：导出时同步调用 audit-service 的内部 ingest 接口，失败就拒绝导出（不可用时返回 503，保证不漏记）。

  事件内容至少包括：`kind`、筛选条件摘要、导出行数、`actor`。正文查看（`/{record_id}/content`）建议也记。
- **工作量与风险**：M。需要新建库、迁移和部署变量，风险中等。

#### P1-2 数据库连接预算超出 Postgres 上限，且没有语句超时

- **类别**：后端性能 / 稳定性
- **位置**
  - `services/{iam,audit,codebook,policy,ai,thinktank}-service/app/core/database.py:12-14`：`create_async_engine(..., pool_pre_ping=True)` 都用 SQLAlchemy 默认的 `pool_size=5, max_overflow=10`
  - `services/iam-service/app/core/database.py:21-22`：另有 `side_engine`（2+3）
  - `deploy/compose/docker-compose.yml:28-71`：postgres 没有设置 `max_connections`（默认 100）
  - 全仓没有 `statement_timeout`、`idle_in_transaction_session_timeout`、`pool_recycle`
- **问题与影响**：iam、iam-worker、audit、audit-worker、codebook、policy、policy-worker、ai、ai-worker、thinktank 一共 10 个进程，每个最多 15 条连接，再加 IAM 的旁路池，**理论上限约 180 条，超过 Postgres 默认的 100**。高峰期（例如批量导入和打标同时跑）会出现 `too many connections`，又因为每次鉴权都要连 IAM，结果可能是全平台 503。另外，一条失控的慢查询或忘了提交的事务会一直占着连接和锁，没有任何兜底。
- **建议**：在 platform-common 加一个统一的引擎工厂，所有服务共用：
  ```python
  def build_engine(url: str, *, pool_size: int, max_overflow: int, statement_timeout_ms: int = 60_000):
      return create_async_engine(
          url, pool_pre_ping=True, pool_size=pool_size, max_overflow=max_overflow,
          pool_recycle=1800, pool_timeout=10,
          connect_args={"server_settings": {
              "statement_timeout": str(statement_timeout_ms),
              "idle_in_transaction_session_timeout": "60000",
              "application_name": settings.service_name,
          }},
      )
  ```
  连接数做成环境变量（如 `IAM_DB_POOL_SIZE`），在 `docs/design/实现决策.md` 记一张连接预算表，postgres 加 `command: ["postgres", "-c", "max_connections=200"]`。爬虫回填、AI 打标这类长任务按会话单独放宽 `statement_timeout`。
- **工作量与风险**：M。超时值设得太紧会误杀合法的长查询，需要先在 P6 上压测再上线。

#### P1-3 智库 PDF 在线预览可能被 CSP 拦截（待浏览器验证）

- **类别**：前端 / 功能缺陷
- **位置**
  - `frontend/src/modules/thinktank/knowledge/KnowledgePreview.vue:76`：用 `URL.createObjectURL(resp.data)` 生成 `blob:` 地址
  - `frontend/src/modules/thinktank/knowledge/KnowledgeDocViewer.vue:49-54`：`<iframe :src="pdfUrl">`
  - `frontend/deploy/nginx.conf:19`、`:26` 和 `deploy/gateway/dynamic.https.yml:108`：CSP 里只有 `default-src 'self'`，没有 `frame-src`
- **问题与影响**：CSP 没写 `frame-src` 时，浏览器会退回用 `default-src 'self'` 判断，而 `blob:` 不在 `'self'` 范围内。也就是说，PDF iframe 在 Chrome / Edge 里很可能是空白，控制台报 `Refused to frame 'blob:...'`。`frontend/e2e/thinktank.spec.ts` 没有断言 PDF 能否渲染，测试发现不了。
- **建议**：先在 8443 环境打开一个 PDF 资料确认；确认后在两处 CSP 里都加上
  ```
  frame-src 'self' blob:; object-src 'none'
  ```
  并在 e2e 里断言 iframe 内容加载成功（或者监听 `securitypolicyviolation` 事件，出现就算失败）。
- **工作量与风险**：S。改的是全站 CSP，需要回归招中标正文（它用 `srcdoc` 沙箱 iframe，不受 `blob:` 影响）。

#### P1-4 招中标源库的「严格只读」只靠应用层前缀检查

- **类别**：安全 / 数据边界（用户的硬性要求）
- **位置**
  - `services/tender-service/app/core/source.py:24-25`：只检查 SQL 是不是以 `SELECT ` 开头、有没有 `;`
  - `services/tender-service/app/core/source.py:37-49`：`autocommit=True`，没有把会话设成只读
  - 政策服务的源库连接 `services/policy-service/app/common/mysql_source.py:49-62` 情况相同
- **问题与影响**：`SELECT ... FOR UPDATE`（会给源表加锁）、`SELECT ... INTO OUTFILE`（会在 DB 服务器上写文件）都能通过这个检查。现在的代码里没有这类语句，所以不是可被利用的漏洞，但「严格只读」这个用户明确提的约束，最终取决于 MySQL 账号的权限，而仓库和文档里都没有记录、也没有校验这一点。
- **建议**
  1. 确认 `TENDER_MYSQL_USER`、政策源库账号在 MySQL 上只有 `SELECT` 权限，并写进 `docs/guides/招中标模块.md`。
  2. 连接建好后执行 `SET SESSION TRANSACTION READ ONLY`（ShardingSphere 是否支持需要先验证）。
  3. 在 `Reader.select` 里再拒绝 `FOR UPDATE`、`INTO OUTFILE`、`INTO DUMPFILE`、`LOCK IN SHARE MODE`，并补对应单测。
- **工作量与风险**：S。风险很低。

### P2 · 中

#### P2-1 智库：对象存储读失败时返回假摘要，掩盖故障

- **位置**：`services/thinktank-service/app/knowledge/application/knowledge.py:262-275`、`:241`；`services/thinktank-service/app/core/storage.py:266-275`
- **问题**：预览时（`for_download=False`）如果 MinIO 读失败，会先退回读本地文件；本地也没有，就把 `_fallback_summary_bytes`（内容可能是「（示例知识资料摘要）」）当作文件内容，以 200 返回。用户看到的是占位文字，运维看到的只是一条 warning 日志。
- **建议**：只在 seed 示例数据（`storage_path` 为空）时用占位摘要；真实文件读不到时，预览也返回 503 或 404，前端显示「文件暂不可用」。
- **工作量与风险**：S，低。

#### P2-2 智库：上传在提交失败时、删除在存储失败时都会留下孤儿对象

- **位置**：`services/thinktank-service/app/knowledge/application/knowledge_write.py:243-271`（补偿只包住 `flush`）；`app/core/database.py:22-24`（提交在依赖退出时才发生）；`knowledge_write.py:295-300`（删除时存储失败只记日志）
- **问题**：对象先写进存储，事务在路由返回之后才提交。提交阶段失败（比如连接断开、序列化冲突）时，补偿逻辑已经不在作用域内，对象永远留在存储里。删除时如果存储暂时不可用，也会留下孤儿。时间一长，存储容量和数据库记录会对不上。
- **建议**：在 upload 里显式 `await session.commit()`，并把它放进补偿的 `try`；另外加一个定期对账任务（登记到 `platform_common.scheduler`），清理数据库里没有记录、且超过 24 小时的 `knowledgeBase/*` 对象。
- **工作量与风险**：M，低。

#### P2-3 智库：数据范围封顶在缺少模块档位时不会收紧

- **位置**：`services/thinktank-service/app/knowledge/domain/scopes.py:115-118`；`app/knowledge/api/routes.py:39-47`；`packages/platform-common/platform_common/service_authz.py:109-110`
- **问题**：`_cap_level` 在 `cap` 为空时原样返回范围档位，而 `request.state.authz_level` 只在权限依赖先执行、而且 `result.level` 有值时才会写入。现在每个路由都把 `actor` 参数写在 `access` 前面，所以能正常工作，但这依赖 FastAPI 按参数顺序解析依赖。以后有人调整参数顺序或复用 `get_knowledge_access`，封顶会悄悄失效，用户拿到的就是未封顶的范围权限。
- **建议**：`get_knowledge_access` 里显式依赖权限依赖的结果；读不到模块档位时，按最低档 `READ` 封顶或直接拒绝。再加一条测试：故意不设置 `authz_level`，断言结果被收紧。
- **工作量与风险**：S，低。

#### P2-4 智库：没配 MinIO 时，生产环境的密钥检查与「回退本地」的设计冲突（待验证）

- **位置**：`services/thinktank-service/app/core/config.py:39-44`；`packages/platform-common/platform_common/config.py:43-56`；`deploy/compose/docker-compose.yml:458-461`
- **问题**：基础校验要求生产环境里名字带 `secret` 的字段不能为空，而 `minio_secret_key` 默认是空串，compose 的默认值也是空。所以只要没配 MinIO，`ENVIRONMENT=production` 下服务会拒绝启动，和注释说的「未配置则回退本地 storage_dir」矛盾。服务器上如果已经配了 MinIO 就不会触发，但本地存储模式在生产环境实际用不了。
- **建议**：把字段改名为 `minio_secret`，并在 `_secret_values` 里规定「只有 endpoint 非空时才要求非空」；或者在 thinktank 的 Settings 里覆盖这条规则。另外补一条单测：生产环境、MinIO 为空时服务能启动。
- **工作量与风险**：S，低。

#### P2-5 文件下载整份读进内存

- **位置**：`services/thinktank-service/app/knowledge/api/routes.py:259-286`；单个文件上限 50MB（`config.py`），容器内存上限 1G（`docker-compose.yml:446`）
- **问题**：`Response(content=raw)` 会把整个文件读进内存。十几个人同时下载大文件就可能触发 OOM。AI 服务已经有现成的 `path_response` 做流式输出（`services/ai-service/app/api/schemas.py:109-135`）。
- **建议**：存储层提供一个 `iter_object` 异步迭代器（MinIO 用 `client.stream`，本地文件分块读），路由改用 `StreamingResponse`。
- **工作量与风险**：M，低。

#### P2-6 招中标每个请求都新建一条 MySQL 连接

- **位置**：`services/tender-service/app/core/source.py:31-55`
- **问题**：列表、详情、正文、计数每次都要经过 ShardingSphere 重新握手、认证。页面一次并发加载几个请求时，延迟会叠加；源库那边的连接数也会随着页面访问上下波动。
- **建议**：在线程池里用一个小连接池（例如用 `queue.Queue` 包一层，或者 `DBUtils.PooledDB`，最多 4 条），取出连接时先 `ping(reconnect=True)`。计数线程池继续用单独的连接。
- **工作量与风险**：S–M，低。

#### P2-7 质量门没覆盖 thinktank，文档也没跟上

- **位置**
  - `.githooks/pre-commit:9`：包列表里没有 `services/thinktank-service`（`Makefile:20` 的 `PY_PACKAGES` 里有）
  - `CLAUDE.md` 的「服务边界」「每个服务一套独立数据库」没写 thinktank / `thinktank_db`；`README.md` 的目录树也没有
  - `deploy/compose/docker-compose.yml:2-3` 文件头的「运行单元」没有列 thinktank-service
  - `docs/guides/部署与维护.md:17` 的库名列表、`:265` 的 `*_ENVIRONMENT` 列表都没有 thinktank
- **问题**：thinktank 的 Python 改动在提交时不跑 ruff，要到推送时才发现。文档是 AI 助手和新成员的主要入口，缺了这一块会让人照旧规则改出问题（比如这次备份就漏了它）。
- **建议**：钩子的包列表改成从 `Makefile` 的 `PY_PACKAGES` 读取（`make -s print-py-packages`），只维护一份；同步补齐上面几处文档。
- **工作量与风险**：S，无风险。

#### P2-8 可观测性：没有统一的指标

- **位置**：只有 IAM 有 `GET /internal/v1/outbox/metrics`（`services/iam-service/app/api/internal.py:55-63`）；全仓搜不到 `prometheus` / `opentelemetry`；`docs/guides/部署与维护.md:255-263` 的告警只停留在「建议」
- **问题**：policy、codebook、ai、thinktank 的 Outbox 积压、调度任务失败、AI 费用异常、源库超时等情况，只能靠翻日志发现。没有一处能告诉运维「今天哪里出了问题」。
- **建议**：先低成本做起来：在 platform-common 提供 `/internal/v1/metrics`（Prometheus 文本格式，指标包括 Outbox 积压与死信数、调度最近一次结果、HTTP 5xx 计数），Traefik 打开 `metrics.prometheus`，部署一台 Prometheus 和 Alertmanager，按文档里已有的阈值配置告警。
- **工作量与风险**：L，低。

#### P2-9 容器没有做最小权限加固

- **位置**：`deploy/compose/docker-compose.yml` 全文都没有 `read_only`、`cap_drop`、`security_opt: no-new-privileges`；前端和 api-fallback 的 nginx 以 root 运行（`frontend/Dockerfile` 的 runtime 阶段）
- **问题**：一旦有某个容器被突破，攻击者拿到的权限比实际需要的多。postgres 同时接在非 internal 的 `gateway` 网络上（`docker-compose.yml:59-61`），网关、前端容器都能直接连到数据库端口。
- **建议**：所有应用服务加上
  ```yaml
  security_opt: ["no-new-privileges:true"]
  cap_drop: ["ALL"]
  read_only: true            # 配 tmpfs: [/tmp]
  ```
  前端改用 `nginxinc/nginx-unprivileged`。postgres 的端口映射处理完 P0-1 后，可以考虑把 postgres 从 `gateway` 网络撤下（不再需要对外映射端口）。
- **工作量与风险**：M。`read_only` 需要逐个服务确认写入路径，风险中等。

#### P2-10 没有 CI，推送前的钩子依赖本机环境

- **位置**：`.githooks/pre-push`（`make check`、`make test-unit`、`make audit-deps`）；`CLAUDE.md`「没有 CI，git 钩子是唯一的自动关卡」
- **问题**：钩子可以用 `--no-verify` 跳过；`audit-deps` 需要外网；Windows 等非 Mac 环境缺少 `python3` 或 `make` 时钩子会直接失败，开发者会倾向于跳过。主分支的质量最终取决于每个人的自觉。
- **建议**：在 GitLab 上加一个最小的 CI（一个 shell runner 跑 `make check && make test-unit`），把主分支设为受保护分支、只允许经 MR 合并；钩子仍然保留，作为本地的快速反馈。
- **工作量与风险**：M，低。

### P3 · 可选改进

| 编号 | 类别 | 位置 | 问题 | 建议 | 工作量 |
| --- | --- | --- | --- | --- | --- |
| P3-1 | 可维护性 | `scripts/check_code_rules.py:16`（`MAX_LINES = 400`） | 有 18 个源文件在 380–400 行之间，如 `frontend/src/views/ProfileView.vue`（398 行）、`services/ai-service/app/application/batch_execute.py`（389 行）。上限正在被「压线」，后续一改就要临时拆分 | 对这些文件按职责主动拆分，不要等到超线才拆 | M |
| P3-2 | 安全 | `services/iam-service/app/api/security.py:73` | CSRF 双提交比较用的是 `!=`，不是常量时间比较 | 改成 `hmac.compare_digest`（实际被利用的可能性极低） | S |
| P3-3 | 安全 | `services/iam-service/app/core/config.py:36` | Access Token 有效期 8 小时。每次请求都会查会话表，所以吊销能立即生效，但令牌泄露后的可用窗口偏长 | 缩短到 30–60 分钟，靠刷新令牌续期 | S |
| P3-4 | 架构一致性 | `services/thinktank-service/app/main.py:33` | Outbox 投递在 API 进程的 lifespan 里跑，其他服务都放在单独的 worker；`config.py:29-30` 的 `worker_*` 配置也没有用到 | 拆出 `thinktank-worker`（同一个镜像），或在文档里说明这样做的理由 | S |
| P3-5 | 测试 | `services/tender-service/tests/`（只有 `test_readonly.py`） | 覆盖率下限是 95%，但计数缓存、统计的双重检查锁、导出上限这些并发和边界场景没有专门的测试 | 补 `counts.poll` 的并发和失败短缓存测试、导出超限 422 的测试 | S |
| P3-6 | 测试 | `services/thinktank-service/tests/`（5 个文件） | 存储故障（MinIO 超时）、孤儿补偿、预览退回占位摘要的路径没有测试 | 用 `httpx.MockTransport` 模拟存储故障 | S |
| P3-7 | 文档 | `docs/guides/系统全面审查与整改报告.md:73` | SEC-05 的定级和现状不符（见 P0-1） | 合并进本报告后删除旧条目，或改为指向本报告 | S |

---

## 三、分阶段优化路线图

### 阶段 0 · 立即处理（本周内，约 1–2 人日）

1. **P0-1**：5433 改回只绑本机，Navicat 改走 SSH 隧道，新建只读账号，收紧 `pg_hba`。
2. **P0-2**：备份和恢复脚本加上 `thinktank_db` 与 `thinktank-data`，在 P6 上做一次恢复演练。
3. **P1-3**：浏览器确认 PDF 预览后，给 CSP 加 `frame-src 'self' blob:; object-src 'none'`。
4. **P1-4**：确认两个源库账号只有 SELECT 权限并写进文档；`Reader.select` 补拒绝列表。
5. **P2-7**：pre-commit 包列表改成和 Makefile 共用一份，补齐 thinktank 相关文档。

### 阶段 1 · 短期（2–4 周）

1. **P1-1**：给招中标接上审计 Outbox，导出和正文查看都要留痕。
2. **P1-2**：统一引擎工厂，加连接预算、`statement_timeout`、`max_connections`，先在 P6 上压测。
3. **P2-1 / P2-2 / P2-3 / P2-4**：智库存储一致性四件套，包括显式提交加补偿、对账任务、预览失败如实报错、范围封顶收紧、MinIO 配置校验修正。
4. **P2-5 / P2-6**：智库下载改流式，招中标源库加连接复用。
5. **P3-2 / P3-3 / P3-5 / P3-6**：顺手完成的安全细节和测试补强。

### 阶段 2 · 中期（1–2 个月）

1. **P2-8**：指标端点、Prometheus 加 Alertmanager、Traefik 指标，按已有阈值配置告警。
2. **P2-9**：容器最小权限加固，postgres 从 `gateway` 网络撤下。
3. **P2-10**：GitLab 最小 CI 加受保护分支。
4. **P3-1 / P3-4**：拆分压线文件，拆出 thinktank-worker。

### 跟踪建议

- 每一项落地时，提交信息里引用本报告的编号（如 `fix(deploy): 收紧 5433 公网暴露（审计 P0-1）`），方便回查。
- 每完成一个阶段，在本报告里更新状态。全部关闭后按 `docs/README.md` 的放置规则，把结论并入现行文档，删除本报告。
