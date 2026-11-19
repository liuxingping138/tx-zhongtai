# tx-zhongtai 全仓审查与优化建议报告

- 审查日期：2026-11-18
- 审查基线：`main` @ `2f828d2`
- 范围：`packages/platform-common`、`services/*`（iam / audit / codebook / policy / ai / tender / thinktank）、`frontend/`、`deploy/`、`scripts/`、`.githooks/`、`tests/`、`docs/`
- 方法：
  - 先由主审做一轮全仓通读，再分四个方向**并行独立深审**：① 后端与 platform-common（架构、数据库、异步、性能）；② 前端（Vue / TS 架构、状态、体验、性能）；③ 安全（认证、RBAC、审计、密钥）；④ 测试、钩子与 Docker / 部署配置。
  - 汇总时去重、合并同源问题、重新定级。关键结论都由主审回到代码复核过（见附录 A）。
  - 全程只读，没有改动任何代码，也没有在服务器上运行。
- 置信度：**已确认**是指读代码确认了问题路径；**待验证**是指代码路径成立，但实际影响取决于运行环境或服务器配置，需要实测。

---

## 一、执行摘要

### 1.1 总体健康度

整体工程成熟度**较高**。这个仓库没有 CI，但用 git 钩子、`make check`、路由安全分级体检、筛选条件一致性测试和迁移漂移检查，把大部分约定固化成了自动检查。认证与会话做得扎实：

- JWT 固定 RS256 并校验 kid / iss / aud；
- 刷新令牌轮换时按令牌族吊销；
- 密码用 argon2，对不存在的用户也走等时路径；
- 内部调用用常量时间比较凭据；
- 鉴权依赖不可用时一律返回 503。

分层干净，四个审查方向都没有发现下层反向 import 的情况。

风险集中在下面四类：

1. **部署暴露面与密钥兜底**：Postgres 超级用户经公网 5433 可达；四个服务的子类校验器**覆盖掉了**平台公共的「生产拒绝示例口令」检查。
2. **新加的智库服务（thinktank-service）没跟上周边配套**：备份、依赖扫描、钩子、运行手册、CSP、前端请求时序都没覆盖到它。
3. **跨服务可靠性与 AI 费用控制**：建 AI 任务的调用不幂等，超时后会产生「孤儿任务」继续花钱；场景比对一次送超过 500 条会被码表拒收，让积压永久卡住；停用调度任务后，正在跑的批次失败了仍会重试。
4. **静默失败**：政策导出在源库报错时给出正文为空的「成功」文件；重新打标的「立即启动」调用的路径根本不存在，失败被吞掉，页面却显示正在重打。

| 维度 | 评价 | 说明 |
| --- | --- | --- |
| 架构与边界 | 良 | 公共能力下沉、import-linter 强制分层；跨服务调用缺幂等键，调度器对心跳和锁的处理还不够健壮 |
| 后端质量与性能 | 中上 | 部分索引、`literal_execute`、按天聚合等细节到位；有事件循环上的 CPU 计算、缺排序索引、批量逐行查询、连接预算超限 |
| 前端 | 良 | `strict` + `noUncheckedIndexedAccess`、列表请求时序、导出约定都守住了；重新打标流程和智库预览页的时序有真实缺陷 |
| 安全与合规 | 中 | 认证会话扎实；暴露面、校验器被覆盖、用户管理员可横向接管账号、招中标导出与用户导出无审计 |
| 测试与质量门 | 中上 | 覆盖率只升不降、契约测试；有测试永远跳过、集成测试全跳过也算通过、冒烟不判断结果、没有单测超时 |
| 运维与可维护性 | 中 | 镜像锁版本、依赖校验哈希、设了内存上限；备份漏掉智库、迁移没有锁超时、证书续期失败不告警、没有指标 |

### 1.2 主要优点（四个方向都确认过）

- **认证与会话**：`services/iam-service/app/core/jwt_tokens.py` 固定算法和 kid 白名单。刷新令牌按族吊销，在返回 401 之前先落库；改密、重置、停用、删除时都吊销会话。登录限流是原子操作，Redis 不可用时返回 503，不会放行。
- **鉴权不会放行**：`platform_common/authz.py:85-102`，加上 `route_audit` 体检强制每条路由声明分级。对象级检查（AI 模板类型、智库逐条范围）都在。
- **注入面**：SQL 全部参数化，表名列名来自白名单；CSV / Excel 导出转义公式，有 xlsx 解压炸弹防护；存储路径只用十六进制 ID 或经过安全解析；`Content-Disposition` 做了清洗；招中标正文放在 `sandbox=""` 的 iframe 里显示；没有发现 SSRF。
- **前端**：`useListLoader` / `useListQuery` 用请求序号丢弃过期响应；11 个导出页都传 `applied`；除了有说明的 `eventStream` 之外没有裸 `fetch`；没有 `v-html`；echarts 实例和 SSE 在卸载时都会释放。
- **并发与锁**：IAM 改人时按固定顺序加锁；码表场景编号分配用 `pg_advisory_xact_lock`；Outbox 回写受租约保护；审计入库去重；爬虫同步用 advisory lock，取消时会释放。
- **供应链**：镜像版本全部锁定；`uv export --frozen` 加 `--require-hashes`；以非 root 用户运行；Traefik 锁版本，注释写明了不能回退的 CVE。

### 1.3 主要风险（Top 10）

| # | 级别 | 风险 | 编号 |
| --- | --- | --- | --- |
| 1 | P0 | Postgres 超级用户经公网 5433 可达，能进全部业务库 | P0-1 |
| 2 | P0 | 备份与恢复漏掉 `thinktank_db` 和 `thinktank-data` 卷 | P0-2 |
| 3 | P1 | 四个服务的子类校验器同名覆盖了公共的生产密钥检查；智库数据库口令默认值写在仓库里 | P1-1 |
| 4 | P1 | 用户管理员能重置任何非超管账号的密码，并直接拿到临时密码 | P1-2 |
| 5 | P1 | 建 AI 流水线任务不幂等，30 秒超时后产生孤儿任务，费用可以超出每日上限 | P1-3 |
| 6 | P1 | 场景比对超过 500 条时被码表拒收，解读导入整体失败，归集积压永久卡住 | P1-4 |
| 7 | P1 | 政策导出在 API 事件循环上清洗最多 10 万页 HTML，源库报错时返回正文为空的「成功」文件 | P1-5 |
| 8 | P1 | 重新打标的「立即启动」请求路径写错，固定返回 404 且被吞掉，页面空转 90 秒 | P1-6 |
| 9 | P1 | 招中标导出不留审计 | P1-7 |
| 10 | P1 | 连接池上限合计约 180 条，超过 Postgres 默认的 100 条；没有语句超时和锁超时 | P1-8 |

---

## 二、分级问题清单

每条包括：类别／位置（文件:行）／问题与影响／建议／工作量（S ≤ 半天，M 1–3 天，L ≥ 1 周）与风险／置信度。来源方向用 [后端]、[前端]、[安全]、[测试部署] 标注，多个方向都报告了的合并成一条。

### P0 · 严重

#### P0-1 Postgres 超级用户经公网 5433 可达 [安全][测试部署]

- **位置**
  - `deploy/compose/docker-compose.yml:59-65`：postgres 接入非 internal 的 `gateway` 网络，端口按 `POSTGRES_BIND_ADDR` 映射
  - `.env.example:15-18`
  - `docs/guides/部署与维护.md:17`、`:288`：安全组已经放行 5433，供 Navicat 直连
  - `docs/guides/系统全面审查与整改报告.md:73`：上一轮把这一项定为「低危」，至今没有关闭
- **问题与影响**：数据库只靠口令防护，暴露在公网，长期面对口令爆破和数据库漏洞利用。超级用户一旦失守，审计库「只增不改」的设计也随之失效，全部业务数据都可能泄露或被篡改。和 P1-1 叠加时更危险：如果某个服务的数据库口令其实还是仓库里的示例值，攻击者可以直接用它登录。
- **建议**
  1. `POSTGRES_BIND_ADDR=127.0.0.1`，Navicat 改走 SSH 隧道。
  2. 确实需要直连时，安全组只放行办公网出口 IP，并在 `pg_hba.conf` 里拒绝超级用户从外网登录：
     ```conf
     host all postgres 0.0.0.0/0 reject
     ```
  3. 单独建一个只读账号给 Navicat 用。
- **工作量与风险**：S。需要提前通知 Navicat 使用者。**置信度**：已确认。

#### P0-2 备份与恢复漏掉智库的库和文件卷 [主审][测试部署]

- **位置**
  - `scripts/backup_business.sh:32`、`:44`：只覆盖五个库和 `ai-data` 卷
  - `scripts/backup.sh:20`、`scripts/restore.sh:24`、`scripts/verify_restore_p6.py:10,14`：都没有 thinktank
  - `deploy/compose/docker-compose.yml:23`、`:468`：`thinktank-data` 卷
- **问题与影响**：智库知识库的元数据、收藏、操作日志，以及本地存储模式下的原始文件，都不在备份里，出事后无法恢复。恢复演练也覆盖不到，这个缺口不会被发现。
- **建议**：在循环里加上 `"thinktank:$THINKTANK_DB_NAME"`，再打包 `/data/thinktank`；同步修改恢复脚本、校验脚本和备份格式版本。如果生产用的是 MinIO，写明桶由谁备份。
- **工作量与风险**：S，低。**置信度**：已确认。

### P1 · 高

#### P1-1 子类校验器同名覆盖了公共的生产密钥检查；智库数据库口令有示例默认值 [安全][主审复核]

- **位置**
  - `packages/platform-common/platform_common/config.py:43-56`：`BaseServiceSettings._reject_demo_secrets_in_production` 会检查连接串里的口令，并要求带 secret 的字段不能为空
  - `services/ai-service/app/core/config.py:56`、`services/codebook-service/app/core/config.py:36`、`services/policy-service/app/core/config.py:75`、`services/thinktank-service/app/core/config.py:48`：这四个子类定义了**同名**的 `@model_validator` 方法，自己只查少数几个 token
  - `deploy/compose/docker-compose.yml:55`、`:451`：`${THINKTANK_DB_PASSWORD:-dev-only-change-me-thinktank}`。其他库的口令都用 `:?`（未设置就报错）
  - `deploy/compose/postgres-init/01-init-databases.sh:47-48`：按这个默认值建库账号
- **问题与影响**：在 pydantic v2 里，子类定义同名的校验方法会**替换**父类的校验器，而不是两个都执行。所以 ai / codebook / policy / thinktank 在生产环境下**不再检查数据库口令是不是示例值**，也不再拒绝空的内部密钥。只要服务器 `.env` 漏了 `THINKTANK_DB_PASSWORD`，`thinktank_app` 的口令就是仓库里公开的值，服务照样以 production 启动；再叠加 P0-1，等于从公网可以读写智库库。

  这一点也修正了上一版报告的 P2-4：上一版说「没配 MinIO 时生产环境启动会被拒绝」，前提是父类校验会执行，实际上它被覆盖了，并不执行。
- **建议**
  1. 子类方法改名（如 `_reject_service_demo_secrets`），或者在方法里先调用父类的检查，让两层校验都执行。
  2. compose 里的智库口令改为 `:?` 必填。
  3. 在 platform-common 加一条单测，保证所有服务的 Settings 在 production 下都会拒绝示例数据库口令。
  4. 立即核对服务器 `.env`。
- **工作量与风险**：S。需要先确认服务器上已经配了真实值，否则改完后服务会拒绝启动。**置信度**：已确认代码路径（基于 pydantic v2 的覆盖语义；本机没有 Python 环境，没有实际运行，建议补单测确认）。

#### P1-2 用户管理员能接管任何非超管账号 [安全]

- **位置**
  - `services/iam-service/app/application/user_admin.py:37-50`：`assert_can_manage_target` 只保护内置超管
  - `user_admin.py:226-241`：`reset_password` 把临时密码返回给操作人
  - `services/iam-service/app/api/users.py:204-212`：只要求 `system.users:reset_password`
- **问题与影响**：拥有用户管理权限、但不是超管的人，可以重置任何其他账号的密码并拿到临时密码，然后用对方身份登录。对方可能持有 `ai.releases`、会花钱的 `policy.ai_tagging`、`ai.billing`、智库范围等权限，甚至是另一个用户管理员。这绕开了「分配角色只限超管」的关键约束（CLAUDE.md「系统管理」一节）。
- **建议**：只有当目标账号的实际权限（`list_effective_levels`）是操作人权限的子集时，才允许重置、停用、下线，否则要求 `system.permissions:grant`。`manageable_ids` 用同一规则，前端据此隐藏按钮。
- **工作量与风险**：M。会改变现有管理员的操作范围，需要和业务方确认。**置信度**：已确认。

#### P1-3 建 AI 流水线任务不幂等，超时后产生孤儿任务、费用超出上限 [后端]

- **位置**
  - `services/policy-service/app/aitag/application/pipeline.py:167-178`：POST 在调用 `stop_quietly` 的 try 之外；`:185` 取结果的调用同样在外面
  - `services/policy-service/app/common/internal_clients.py:32-35`、`core/config.py:72`：内部调用超时 30 秒
  - `services/ai-service/app/application/pipeline_runs.py:135-188`：`create` 要解析最多 56MB 的行数据、写快照、复用旧答案（读两遍原始 CSV）、取系统码表，全程持有模板行的 `FOR UPDATE` 锁
- **问题与影响**：`create` 超过 30 秒时，政策服务按「依赖不可用」处理并把本批记为失败。但 ai-service 那边的处理不会因为客户端断开而取消，任务照样提交、被 ai-worker 领走执行。政策服务没记下这个 run id，所以：
  - 停不掉它；
  - 它花的钱不进 `spent_since`；
  - 复用逻辑也找不到它。

  调度器 60 秒后重试，又按剩余额度新建一个任务，同一批行被问两遍，每次重试都可能让当天费用超出上限一倍。取结果的调用也可能因为超时反复失败。
- **建议**
  1. 政策服务先生成幂等键（客户端 run id），在 POST 之前写进 `PolicyAiRun`；ai-service 的 `create` 按这个键做 upsert。失败时按键调用 `stop` 并记账。
  2. 建任务和取结果这两个调用单独设较长的超时。
  3. 文件 I/O 之前先释放模板行锁。
- **工作量与风险**：M，中。**置信度**：代码路径已确认，实际耗时待验证。

#### P1-4 场景比对超过 500 条时被拒收，导入失败、积压卡死 [后端]

- **位置**
  - `services/policy-service/app/policy/application/scenario_engine.py:279-305`：一次请求送出全部条目，只捕获 `DependencyUnavailableError`
  - `services/codebook-service/app/api/internal.py:83`：`Field(max_length=500)`
  - `services/policy-service/app/common/internal_clients.py:39-40`：422 被转成 `ApiError`
- **问题与影响**：
  - **解读 Excel 导入**（`interpretations.py:330` → `classify_quietly`，`scenario_engine.py:328-339`）：新候选超过 500 个时整次导入失败，提示「参数校验失败」。
  - **归集积压**（`classify_backlog`，`:342-358`，每批 1000 条）：没有捕获 `ApiError`，事务回滚后，每批 AI 跑完都重试同样的前 1000 行，积压**永久卡住**。`interpreting._classify_new_rows:168-171` 只记日志。
  - **`classify_scenarios --resimilar`**：待审候选超过 500 个时必然失败。
- **建议**：按 500 条分片发送（参考 `scenario_rows.lookup` 里已有的 `LOOKUP_CHUNK`）；相似度计算失败时也捕获 `ApiError`，当作非致命错误处理。
- **工作量与风险**：S，低。**置信度**：已确认（主审复核了 500 条上限和异常处理）。

#### P1-5 政策导出在事件循环上清洗 HTML，源库报错时静默返回空正文 [后端]

- **位置**
  - `services/policy-service/app/policy/application/policy_content.py:63-84`：`:76` 读取放进了线程，但 `:82` 的 `rules.clean_content` 在协程里同步执行；`:78-79` 失败时直接返回已经读到的那部分
  - 调用方：`policy/application/base_tags.py:283`、`interpretations.py:368`
  - `common/mysql_source.py:44-66`：使用 worker 的默认参数（读超时 1200 秒，带 `time.sleep` 重试 3 次）
- **问题与影响**：
  - 导出最多 10 万行，每页正文都要过两遍 `html.parser`，全部跑在单个 uvicorn worker 的事件循环上，政策服务的所有请求会卡住几分钟。
  - 源库中途报错时，文件仍然「成功」下载，但报错之后的所有行政策正文都是空的，用户不会收到任何提示。
  - 这也违反了 CLAUDE.md 里「HTTP 进程读源库用短超时、不重试」的约定。
- **建议**：清洗也放进线程（`to_thread.run_sync(lambda: {k: clean_content(v, 0) for k, v in source.read_contents(batch).items()})`）；改用页面读取用的短超时连接；失败时抛 503，不返回部分数据；带正文的导出另设较低的行数上限（5–10k），或者把正文改成可选列。
- **工作量与风险**：S–M，低。**置信度**：已确认。

#### P1-6 重新打标流程：「立即启动」路径写错，轮询误报完成 [前端]

- **位置**
  - `frontend/src/modules/policy/base-tags/retag.ts:15`：`triggerJob(\`policy_ai_${step}\`, { base: '/policy' })` 实际请求的是 `POST /api/v1/policy/policy_ai_type/runs`，而正确的前缀是 `/policy/scheduled-jobs`（`frontend/src/api/scheduler.ts:59,66,79`、`services/policy-service/app/scheduler/api/jobs.py:11`）
  - `retag.ts:43-56`、`:69-76`：轮询方式
  - `BaseTagList.vue:61-63`、`InterpretationList.vue:63-65`：刷新时连带重载 `filters.load()`
- **问题与影响**
  - 请求固定返回 404，`.then(()=>true, ()=>false)` 把错误吞掉。用户在三个入口点「重新打标」后，按钮显示「正在重新打标…」空转 90 秒，后台其实什么都没执行。单测 mock 掉了 `triggerJob`，契约测试只覆盖默认前缀，所以都没发现。
  - 轮询拿整页数据做基线快照：翻页、别人改了行、定时批次写入都会被误判成「重新打标已完成」；行的状态变成失败也会报完成。90 秒后无声放弃，而 AI 批次通常要好几分钟。每 3 秒还要重算一次几百万行表的筛选项。
- **建议**：去掉 `base` 参数（默认值就是政策调度前缀）并补一条断言路径的测试；轮询改成只按这次重打的 id 查询，固定当前页，失败如实报告，时间窗口改成退避，轮询期间不重载筛选项。
- **工作量与风险**：S（路径）加 M（轮询），低。**置信度**：已确认（主审复核了路径）。

#### P1-7 招中标导出与正文查看都不留审计 [主审]

- **位置**：`services/tender-service/app/api/routes.py:44-47`；`app/application/records.py:91-106`。对照：其他模块的导出都会写 `*.exported` 事件（如 `policy/.../interpretations.py:381`）。
- **问题与影响**：单次最多导出 10 万行的招中标数据，但没有任何操作日志，出现外泄时无法追溯。
- **建议**：给 tender 建一个只放 `tender_outbox` 的小库，复用 `AuditEmitter`；过渡方案是导出时同步调用审计入库接口，失败就返回 503。
- **工作量与风险**：M，中。**置信度**：已确认。

#### P1-8 连接预算超出上限；没有语句超时、迁移没有锁超时 [主审][测试部署]

- **位置**
  - 各服务的 `app/core/database.py:12-14` 都用 SQLAlchemy 默认的 5+10 连接池；`iam-service/app/core/database.py:21-22` 另有旁路池
  - postgres 没有设置 `max_connections`（`docker-compose.yml:28-71`）
  - 全仓没有 `statement_timeout`、`idle_in_transaction_session_timeout`
  - `services/*/migrations/env.py:44-46`：迁移不设 `lock_timeout`
- **问题与影响**：10 个进程，每个最多 15 条连接，合计约 180 条，超过默认上限 100 条。高峰期会出现 `too many connections`，加上每次鉴权都要连 IAM，结果可能是全平台 503。慢查询和忘了提交的事务也没有兜底。

  迁移在执行 `ALTER TABLE` 时要拿排他锁。如果表上正好有长事务（AI 打标、爬虫同步、导出），迁移会一直等，而后面所有访问这张表的查询都排在它后面，部署期间整个平台卡住。`scheduler/store.py` 的列表接口还有逐任务查询（每 5 秒约 30 次查询，见 P3-13），进一步加重连接压力。
- **建议**：在 platform-common 提供统一的引擎工厂，连接池大小做成环境变量，并在 `connect_args.server_settings` 里设置 `statement_timeout`、`idle_in_transaction_session_timeout`、`application_name`。postgres 设 `max_connections=200`，并在 `docs/design/实现决策.md` 记一张连接预算表。迁移的 `do_run_migrations` 先执行 `SET lock_timeout='5s'`，超时就重跑。
- **工作量与风险**：M。超时设得太紧会误杀合法的长查询，需要先在 P6 上压测。**置信度**：已确认。

#### P1-9 政策基础标签列表的默认排序没有索引，每页都整表计数 [后端]

- **位置**：`services/policy-service/app/policy/repositories/base_tags.py:16`（`_ORDER = province_code, policy_name, id`）、`:114-126`；索引定义在 `policy/domain/models.py:86-125`。
- **问题与影响**：表上没有以 `province_code` 开头的 B 树索引。几百万行时，不带筛选的默认首页就要全表扫描加排序，再做一次全表 `count(*)`；深分页用 OFFSET 更慢，详情页的上一条 / 下一条也会受影响。
- **建议**：用 `CREATE INDEX CONCURRENTLY` 建 `(province_code, policy_name, id)` 索引；计数参照审计服务的做法，只在当前页取满时才 count。解读列表（`interpretations.py:15`）也按同样方式检查执行计划。
- **工作量与风险**：S，低。**置信度**：缺索引已确认，实际耗时待验证。

#### P1-10 智库预览页没有请求时序保护，快速切换后操作可能落到上一个文件 [前端]

- **位置**：`frontend/src/modules/thinktank/knowledge/KnowledgePreview.vue:125-148`（`loadPage`）、`:83-98`、`:100-113`、`:189-191`；`:155-187`（收藏、下载、删除）；`KnowledgeMetaCard.vue:139`；`:76` 覆盖 `pdfUrl` 前没有释放旧的地址。
- **问题与影响**：快速点「上一个 / 下一个」时，A 文件的响应可能晚于 B 文件到达，于是 B 的地址下显示的是 A 的元数据或 PDF。这时点**删除**、收藏、下载或保存元数据，操作对象都是 A。每次加载都创建新的 blob URL 而不释放，也会造成内存泄漏。
- **建议**：照 `useReviewRecord` 的做法给每次加载编序号，丢弃过期结果；赋值前先 revoke 旧地址；只有 `item.id === 路由 id` 时才允许操作。
- **工作量与风险**：M，低。**置信度**：已确认。

#### P1-11 智库 PDF 预览可能被 CSP 拦截 [主审]

- **位置**：`KnowledgePreview.vue:76`（blob URL）、`KnowledgeDocViewer.vue:49-54`（iframe）；`frontend/deploy/nginx.conf:19,26` 和 `deploy/gateway/dynamic.https.yml:108` 的 CSP 只有 `default-src 'self'`，没有 `frame-src`。
- **问题与影响**：没写 `frame-src` 时浏览器按 `default-src 'self'` 判断，`blob:` 不算 `'self'`，PDF 区域会是空白。e2e 没有断言 PDF 能否渲染。
- **建议**：两处 CSP 都加 `frame-src 'self' blob:; object-src 'none'`，并在 e2e 里断言没有触发 `securitypolicyviolation`。
- **工作量与风险**：S，低。**置信度**：待验证（需要在浏览器里实测）。

#### P1-12 招中标和政策源库的「只读」只靠应用层前缀检查 [主审]

- **位置**：`services/tender-service/app/core/source.py:24-25`、`:37-49`；`services/policy-service/app/common/mysql_source.py:49-62`。
- **问题与影响**：`SELECT ... FOR UPDATE`、`SELECT ... INTO OUTFILE` 都能通过前缀检查。用户明确要求的「严格只读」最终取决于 MySQL 账号权限，而仓库里没有任何记录或校验。
- **建议**：核实两个源库账号只有 SELECT 权限并写进文档；连接后执行 `SET SESSION TRANSACTION READ ONLY`（先确认 ShardingSphere 是否支持）；`Reader.select` 再拒绝 `FOR UPDATE` 和 `INTO OUTFILE` / `INTO DUMPFILE`。
- **工作量与风险**：S，低。**置信度**：已确认（实际风险取决于账号权限）。

### P2 · 中

| 编号 | 类别 / 来源 | 位置 | 问题与影响 | 建议 | 工作量 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- |
| P2-1 | 调度 / 费用 [后端] | `platform_common/scheduler/store.py` 的 `update_job`（约 389-403 行）、`claim_next_run`（约 457-479 行）；`scheduler/jobs.py` 的 `fail_run`（约 63-72 行） | 停用任务只取消排队中的执行，正在跑的批次失败后照样进入重试，最多 3 次，每次都可能花满当天额度、跑 6 小时。停用 AI 打标并不能止损 | `fail_run` 和 `execute_claim` 先重新读取任务；已停用的计划执行直接记为取消；花钱的任务增加「停止正在运行」操作 | S | 已确认 |
| P2-2 | 调度健壮性 [后端] | `platform_common/scheduler/runner.py:127-134`、`:169-193` | 心跳写入只要报一次错（锁等待、语句被取消），整个 leader 就退出，并取消所有通道，包括跑了几个小时的 AI 批次 | 心跳失败先重试，只有确认连接已断开时才退出；可以再查 `pg_locks` 确认锁仍在自己手里 | S | 已确认 |
| P2-3 | 选主 [后端] | `services/ai-service/app/worker/runner.py:76-92`，心跳在 `:64-72` 走另一条连接 | 拿锁的连接断开后锁就自动释放了，但进程不会察觉，继续领任务执行；第二个 worker 上来后会把前一个进程正在跑的任务标成中断，导致重复执行、重复计费 | 心跳循环里同时检查拿锁的那条连接 | S | 待验证（当前只跑一个副本） |
| P2-4 | 事件循环阻塞 [后端] | `services/ai-service/app/api/internal.py:52-62`、`application/pipeline_runs.py:49-62` | 最多 56MB 的 JSON 请求体在事件循环上解析和校验，同一事件循环上的 SSE 试发会卡几秒，也加剧了 P1-3 的超时 | 读取原始请求体，放进线程里解析 | S–M | 待验证 |
| P2-5 | 智库存储 [主审] | `thinktank-service/.../knowledge.py:262-275`、`:241`；`core/storage.py:266-275` | 对象存储读失败时，预览返回 200 和占位摘要（「示例知识资料摘要」），故障被掩盖 | 只有 seed 示例数据才用占位摘要；真实文件读不到时返回 503 或 404 | S | 已确认 |
| P2-6 | 智库存储 [主审] | `knowledge_write.py:243-271`（补偿只包住 flush）；`core/database.py:22-24`；`knowledge_write.py:295-300` | 提交阶段失败或删除时存储不可用，都会留下孤儿对象，存储和数据库逐渐对不上 | 显式提交并放进补偿范围；加一个定期对账任务 | M | 已确认 |
| P2-7 | 智库权限 [主审] | `domain/scopes.py:115-118`；`api/routes.py:39-47`；`platform_common/service_authz.py:109-110` | 读不到模块档位时，范围档位不会被封顶，而能否读到依赖 FastAPI 按参数顺序执行依赖 | 显式依赖权限结果；读不到时按最低档处理，并补测试 | S | 已确认 |
| P2-8 | 大文件 [主审][前端] | 后端 `thinktank-service/.../routes.py:259-286` 整个文件读进内存（上限 50MB，容器 1G）；前端 `frontend/src/api/thinktank.ts:114-120` 沿用默认 30 秒超时（`http.ts:21`），预览失败被吞掉（`KnowledgePreview.vue:93-94`） | 并发下载可能触发 OOM；大文件在一般网速下超时，预览无提示地退回摘要模式 | 后端改流式响应；前端传 `timeout: 600_000`，预览失败显示错误 | M | 已确认 |
| P2-9 | 网关 [测试部署] | `deploy/gateway/dynamic.yml:88-96` 的 `buffering` 中间件挂在 `ai-stream` 之外的所有路由上 | Traefik 的 buffering 同时缓冲响应：几百 MB 的结果下载要等全部生成并缓冲完才开始发送，占用网关内存和磁盘，也可能超过 600 秒写超时 | 下载路由不挂 buffering，或者显式设置响应体上限，并在 P6 上用 200MB 文件实测 | M | 待验证 |
| P2-10 | 运行时 [测试部署] | 各服务 Dockerfile 的 `CMD`（如 `policy-service/Dockerfile:48`），uvicorn 默认 keep-alive 5 秒；网关没有配置 `serversTransport` | Traefik 默认会复用空闲 90 秒内的后端连接，而后端 5 秒就关掉了，这是偶发 502 / EOF 的经典原因 | uvicorn 加 `--timeout-keep-alive 75`，或者 Traefik 设 `idleConnTimeout: 4s` | S | 待验证 |
| P2-11 | 非 HTTPS 配置的安全基线 [安全] | `deploy/gateway/dynamic.yml:14-74` 没有 `secure-headers`；`docker-compose.yml:506` 默认绑 `0.0.0.0`；`iam-service/app/core/config.py:44,77-87` 的 `cookie_secure` 默认是 false 且生产环境不强制；`api/auth.py:68-108` 的 `/login` 不检查 Origin | 一旦漏叠 HTTPS 覆盖文件，就既没有 CSP 也没有防 iframe 嵌入，刷新 Cookie 走明文；登录接口存在 CSRF（受害者会被登录进攻击者的账号） | `dynamic.yml` 也挂 secure-headers（不含 HSTS）；生产环境拒绝 `cookie_secure=False`；`/login` 加 `check_origin` | S | 已确认 |
| P2-12 | 网络分段 [主审][安全] | `docker-compose.yml`：postgres、各服务、网关、前端、api-fallback 都接在 `gateway` 网络上；redis（`:72-79`）没有密码；全文没有 `read_only` / `cap_drop` / `no-new-privileges`；前端 nginx 以 root 运行 | 任何一个边缘容器被攻破，都能绕过网关直连数据库和各服务的 `/internal/*` 接口 | 单独建一个边缘网络，只接需要路由的服务；postgres 撤出 `gateway`；redis 设 `requirepass`；容器做最小权限加固；前端换 `nginx-unprivileged` | M | 已确认 |
| P2-13 | 质量门覆盖 [主审][测试部署] | `.githooks/pre-commit:9` 和 `scripts/audit_deps.sh:7` 的包列表都没有 thinktank；`docs/guides/部署与维护.md:67`（重建全部服务的命令漏了 tender 和 thinktank）、`:94-98`（迁移步骤漏了智库的建库和迁移）、`:17`、`:265`；CLAUDE.md、README、compose 文件头都没提 thinktank | 智库的改动提交时不跑 ruff，依赖漏洞不扫描；照着运行手册部署会出现「新代码跑在旧表结构上」 | 包列表统一从 `Makefile` 的 `PY_PACKAGES` 读取；补齐文档；手册里的迁移步骤直接改成 `make SERVER=1 migrate` | S | 已确认 |
| P2-14 | P6 验收盲区 [测试部署] | `deploy/compose/docker-compose.p6.yml:30,37`（IAM 的内部调用密钥里没有 tender-service）；`docker-compose.yml:287`；`tests/p6/accept.py:426-436` 只断言匿名 401 | P6 里 tender 的所有登录态请求都会 503，但测试一直是绿的；IAM 到 tender 这条最容易配错的链路从来没被验证过 | 补上密钥和 tender 的 override，A17 断言管理员请求不会因为「鉴权不可用」返回 503 | S | 已确认（主审复核） |
| P2-15 | 证书 [测试部署] | `deploy/systemd/tx-zhongtai-cert-renew.service` 没有 `OnFailure=`；`scripts/renew_ip_cert.sh:16` 依赖 80 端口空闲 | 证书有效期约 6 天，续期静默失败几天后 8443 就会断 | 加 `OnFailure=` 告警，每天用 `openssl x509 -checkend 172800` 检查一次 | S | 已确认 |
| P2-16 | 密钥扫描 [测试部署] | `scripts/scan_scope.py:18-22` 只匹配带引号的 `password=`，以及 PEM 头 | 漏掉 `.env` 风格的 `*_SECRET=` / `*_API_KEY=`，以及连接串里的口令；真的方舟或千帆密钥提交进来也扫不出 | 扩展匹配规则，加入 `://user:pass@` 检测，并补测试用例 | S | 已确认 |
| P2-17 | 前端权限 [前端] | `InterpretationList.vue:146`（按 `canFull('policy.interpretations')` 显示按钮）对比后端 `aitag/api/ai_tagging.py:83-88`（要求 `policy.base_tags:update`） | 只有解读权限的用户能看到「重新打标」，填完弹窗才收到 403 | 显示条件改成 `canFull('policy.base_tags')` | S | 已确认 |
| P2-18 | 前端时序 [前端] | `KnowledgeLogsDrawer.vue:23-45`、`:57-63` | 没有请求序号，会串到别的文件的日志；重新打开不清空；请求失败时显示「暂无操作日志」 | 加请求序号，打开时清空，增加错误分支 | S | 已确认 |
| P2-19 | 渲染性能 [前端] | `components/ScrollPort.vue:79-83`、`:36-49`（每个列表页都经 `ListPage.vue:103` 用到它） | `MutationObserver` 监听整张表的 subtree 和 attributes，鼠标划过每一行都会强制重排；捕获阶段的 wheel 处理器会抢走内层滚动 | 改用 ResizeObserver，用 rAF 合并测量；内层可滚动时不拦截 wheel | M | 待验证 |
| P2-20 | 可观测性 [主审] | 只有 IAM 有 `/internal/v1/outbox/metrics`（`iam-service/app/api/internal.py:55-63`）；全仓没有 Prometheus | Outbox 积压、调度失败、费用异常只能靠翻日志发现 | platform-common 提供统一的指标端点，配上 Traefik 指标、Prometheus 和 Alertmanager | L | 已确认 |
| P2-21 | CI [主审] | `.githooks/pre-push`；本机（Windows）没有 `python3`、`uv`，钩子也没启用（`core.hooksPath` 为空） | 质量门可以用 `--no-verify` 跳过，在非 Mac 环境上实际不会运行，主分支质量全靠自觉 | GitLab 加最小 CI（`make check && make test-unit`）并开启受保护分支 | M | 已确认 |
| P2-22 | 招中标连接 [主审] | `tender-service/app/core/source.py:31-55` | 每个请求都经 ShardingSphere 重新建连 | 用一个小连接池，取出时先 ping | S–M | 已确认 |

### P3 · 可选改进

| 编号 | 类别 / 来源 | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| P3-1 | 审计 [安全] | `iam-service/app/api/users.py:71-84`、`application/user_excel.py:44-70` | 导出用户（含手机号和邮箱）不留审计 | 记 `iam.user.exported` 事件，带筛选条件和行数 |
| P3-2 | 审计 [安全] | `iam-service/app/application/user_admin.py:205-221` | `iam.user.updated` 只记了状态，联系方式改了什么查不到 | 记录改动前后的字段差异 |
| P3-3 | 审计敏感数据 [安全] | `iam-service/app/application/auth_service.py:160-175` | 对不上账号的登录失败会原样记下用户名输入框的内容，用户常把密码误输进用户名框，明文密码会进只增不改的审计库保留 180 天 | 对不上账号时只记脱敏值或 HMAC |
| P3-4 | XSS [安全] | `frontend/src/modules/policy/crawler-config/ConfigNewSites.vue:77-81`；`policy-service/.../sources.py` | 链接直接绑定 `row.url`，没有校验协议，`javascript:` 链接可以通过信源导入写进来 | 改用 `fieldLink`；后端校验只允许 http(s) |
| P3-5 | 内部鉴权 [安全] | `.env.example:51,59,72-77`；`codebook-service/app/core/config.py:35-42`；`codebook-service/app/api/internal.py:150-195`；`audit-service/app/api/internal.py:26` | 不强制各调用方的密钥互不相同；运维如果复制同一个值，任何服务都能冒充 policy 写码表，或冒充别的服务写审计 | 生产环境拒绝重复的密钥值；`.env.example` 给每个调用方不同的占位值 |
| P3-6 | 内部鉴权 [安全] | `iam-service/app/api/internal.py:33-52`、`api/schemas.py:111-115` | 任何内部调用方都能查询任意资源和范围前缀 | 按调用方配置可查询的资源命名空间白名单 |
| P3-7 | 会话 [安全][主审] | `auth_service.py:187-198`（重用宽限 30 秒）；`iam-service/app/core/config.py:36`（Access Token 8 小时）；`api/security.py:73`（CSRF 用 `!=` 比较） | 宽限期内重放刷新令牌不会被发现；令牌可用窗口偏长；CSRF 比较不是常量时间 | 宽限期缩到约 5 秒，要求 IP 和 UA 一致，并记审计；Access Token 改为 30–60 分钟；改用 `hmac.compare_digest` |
| P3-8 | 打标性能 [后端] | `policy-service/app/aitag/application/tagging.py:94-143`（`:113` 逐行查询）；`aitag/repositories/tagging.py:77-81`、`:129-133`；`aitag/application/settings.py:22`（每批上限 2 万） | 2 万行逐行查哈希，同时持有全部行锁；两处加锁顺序不同，可能死锁，回滚已经付过钱的保存 | 一次查出所有哈希；按 id 固定顺序加锁；每批上限降到 2–5k |
| P3-9 | 费用口径 [后端] | `aitag/repositories/tagging.py:37-43`；`aitag/application/pipeline.py:130-142` | 每日额度按批次开始时间归属，跨午夜的批次和事后的费用修正都算到旧的日期，实际花费可能接近上限的 2 倍 | 改用 ai-service 已有的按天账本 |
| P3-10 | Outbox 吞吐 [后端] | `platform_common/audit_emit.py:395-407`、`:473-486` | 每 2 秒最多投递 20 条，批次满了也照样等待；积压后要好几个小时才能排空（IAM 没有这个问题，见 `iam-service/app/worker/__main__.py:80-81`） | 批次满了就不等待，并考虑有界并发投递 |
| P3-11 | 调度 N+1 [后端] | `platform_common/scheduler/store.py` 的 `list_jobs`（约 344-380 行）、`history`（约 442 行）；`policy-service/app/scheduler/application/jobs.py:79-80` | 页面每 5 秒轮询一次，每次约 30 条查询，外加约 10 次额外的连接借出 | 用 `DISTINCT ON (job_code)` 一次查出 |
| P3-12 | 智库架构 [主审] | `thinktank-service/app/main.py:33`；`core/config.py:29-30`（`worker_*` 配置没有用到） | Outbox 投递在 API 进程里跑，和其他服务不一致 | 拆出 `thinktank-worker` |
| P3-13 | 无效测试 [测试部署] | `codebook-service/tests/test_fields_and_excel.py:55-61` | 文件路径写错，测试永远跳过；即使找到文件也没有断言 | 修正路径并改成 assert，或者删除 |
| P3-14 | 测试通过不代表测过 [测试部署] | `policy-service/tests/test_scheduler_integration.py:30`、`test_aitag_integration.py:23`、`test_crawlconfig_integration.py:24`，ai `test_integration.py:36`；`scripts/scheduler-integration.sh:42`；`scripts/test_restore_owner.sh`、`verify_restore_p6.py` 没有任何地方调用 | 全部跳过时 pytest 照样返回 0；恢复校验脚本等于死代码 | 设置了集成标志却有跳过时判为失败；把校验脚本接进 `p6-restore` |
| P3-15 | 冒烟与等待 [测试部署] | `Makefile:339-353`、`:255-258` | `smoke` 只打印状态码，永远返回 0；`p6-up` 等满 120 秒后无声继续 | 比较状态码，失败就退出 |
| P3-16 | 单测超时 [测试部署] | 各 `pyproject.toml` 没有 pytest-timeout；`platform-common/tests/test_scheduler_api.py:167`、`test_scheduler_runner.py:324` 用了 `sleep(60)` | 取消逻辑一旦回归，pre-push 会一直卡住 | 加 `pytest-timeout`，`timeout = 120` |
| P3-17 | 迁移规则 [测试部署] | `scripts/check_code_rules.py:47-50`、`:98-112` | 大表规则只拦建索引，不拦唯一约束、改列类型、`SET NOT NULL`；`BIG_TABLES` 写死了 4 张表 | 扩大规则覆盖范围 |
| P3-18 | 契约测试 [测试部署] | `frontend/src/api/contract.test.ts:52-69`；`eventStream.ts:47`；`e2e/filter-options.spec.ts:150` | 导出路径和流式接口路径不在契约测试里；有一条 `toBeTruthy()` 断言不可能失败 | 把导出路径收进常量模块，纳入契约测试 |
| P3-19 | Compose / 镜像 [测试部署] | `docker-compose.yml:387-440`（iam-worker、audit-worker 没有健康检查，也没设 `init`）、`:509-517`（网关的 depends_on 漏了 tender）；各 Dockerfile 生成了没人用的 `/opt/requirements.frozen.txt`；`.dockerignore` 只排除根目录的 `.env.*` | 运维盲区、镜像偏大，`frontend/.env.local` 可能被带进构建 | 补齐上述配置；改用多阶段构建；排除规则改成 `**/.env.*` |
| P3-20 | 前端提示 [前端] | `http.ts:57-62`；`useCandidateExtras.ts:26-30` | 码表不可用时同时弹出全局提示和行内提示 | 每个调用单独标记错误已提示 |
| P3-21 | 前端 403 [前端] | `main.ts:48-52`；`http.ts:98-100` | N 个并发 403 会重载 N 次个人资料，权限撤销后当前页面不会跳走 | 同一时间只保留一个加载 Promise，加载后重新检查路由权限 |
| P3-22 | 未保存数据 [前端] | `KnowledgeMetaCard.vue:176-186`；`KnowledgePreview.vue:150-153` | 用浏览器前进 / 后退在预览页之间切换时，正在编辑的元数据会无提示丢失 | 加 `onBeforeRouteUpdate` |
| P3-23 | 前端健壮性 [前端] | `KnowledgePreview.vue:49,70` | `localStorage` 没有 try/catch，浏览器禁用存储时整个预览页无法挂载 | 包一层 try/catch |
| P3-24 | 重复实现 [前端] | `system/audit/AuditList.vue:57-78`、`system/sessions/LoginLogList.vue:47+`；共 29 个文件各自写请求序号 | 智库页面缺少时序保护就是这么来的 | 统一用 `useListLoader`，另提供 `useLatest()` |
| P3-25 | 无障碍 [前端] | `ai/prompts/SamplePreviewTable.vue:51-56` | 选择样本行只能用鼠标 | 参照 `SampleResultsDrawer.vue:243-249` 用按钮 |
| P3-26 | 测试厚度 [主审] | `tender-service/tests/`（只有 1 个文件）；`thinktank-service/tests/`（没有存储故障的测试） | 计数缓存的并发、导出超限、存储故障路径都没有测试 | 用 `httpx.MockTransport` 等补测试 |
| P3-27 | 可维护性 [主审] | `scripts/check_code_rules.py:16`；有 18 个文件在 380–400 行之间 | 行数上限正在被「压线」 | 按职责主动拆分 |
| P3-28 | 文档 [主审] | `docs/guides/系统全面审查与整改报告.md:73` | SEC-05 的定级和现状不符 | 改为指向本报告的 P0-1 |

---

## 三、分阶段优化路线图

### 阶段 0 · 立即处理（本周，约 2–3 人日）

先止损：暴露面、数据安全、会花钱的问题和明显的功能缺陷。

1. **P0-1**：5433 改回只绑本机，Navicat 走 SSH 隧道，新建只读账号。
2. **P1-1**：先核对服务器 `.env`，再修校验器同名覆盖，智库口令改为必填。（和 P0-1 一起做，两者叠加时风险最大。）
3. **P0-2**：备份和恢复脚本加上智库，在 P6 上做一次恢复演练。
4. **P1-6（路径部分）**：去掉 `base: '/policy'`，一行改动，加一条测试。
5. **P1-4**：场景比对按 500 条分片，并捕获 `ApiError`，解开卡住的积压。
6. **P2-1**：停用任务后，不再重试正在跑的批次（AI 费用止损）。
7. **P1-11 / P2-13 / P2-14 / P2-15**：CSP 的 `frame-src`、质量门和手册补上 thinktank、P6 的 tender 密钥、证书续期失败告警。

### 阶段 1 · 短期（2–4 周）

1. **费用与可靠性**：P1-3（流水线幂等键和超时）、P1-5（导出清洗移进线程、失败返回 503）、P2-2 / P2-3（调度器心跳与锁检查）、P2-4。
2. **安全**：P1-2（重置密码的权限按子集判断）、P1-7（招中标审计 Outbox）、P1-12（源库只读）、P2-11（非 HTTPS 配置的安全基线、登录 Origin 检查）。
3. **性能与稳定性**：P1-8（统一引擎工厂、连接预算、语句超时和锁超时）、P1-9（基础标签排序索引，用 `CONCURRENTLY` 建）、P2-9 / P2-10（网关 buffering 和 keep-alive，在 P6 上实测）。
4. **前端**：P1-6（轮询部分）、P1-10、P2-8、P2-17、P2-18。
5. **智库存储**：P2-5、P2-6、P2-7。

### 阶段 2 · 中期（1–2 个月）

1. **工程体系**：P2-21（GitLab CI 和受保护分支）、P2-16（密钥扫描）、P3-13 至 P3-18（让测试和冒烟真的能失败）。
2. **运维**：P2-20（指标与告警）、P2-12（网络分段和容器加固）、P2-22、P3-19。
3. **性能与架构**：P3-8 至 P3-12、P2-19、P3-24、P3-27。
4. **审计与会话细节**：P3-1 至 P3-7。

### 跟踪建议

- 提交信息里引用编号，如 `fix(iam): 重置密码改为按权限子集判断（审计 P1-2）`。
- 每完成一个阶段，在本报告里更新状态。全部关闭后，把结论并入现行文档，删除本报告（遵循 `docs/README.md` 的放置规则）。

---

## 附录 A · 汇总与复核说明

- **四个方向的原始发现**：后端 12 条、前端 13 条、安全 12 条、测试部署 15 组，加上主审第一轮的 20 余条。合并重复项后剩约 60 条，按「可被利用性 × 影响面 × 是否静默」重新定级。
- **合并的条目**：
  - 连接池（主审）和迁移锁超时（测试部署）合成 P1-8。
  - 智库下载内存（主审）和前端 30 秒超时（前端）合成 P2-8。
  - 网络分段（安全）和容器加固（主审）合成 P2-12。
  - 质量门（主审）、依赖扫描（测试部署）和运行手册（测试部署）合成 P2-13。
  - 会话细节三项合成 P3-7。
- **上调的条目**：安全方向把「用户管理员接管账号」定为 P2，本报告上调为 P1，因为它绕过了「分配角色只限超管」这一明确的设计约束。
- **主审回到代码复核过的结论**：
  - P1-1：四个子类的同名校验器，以及 compose 里的 `:-` 默认值；
  - P1-2：`assert_can_manage_target` 只判断超管；
  - P1-4：码表的 `max_length=500`，以及只捕获 `DependencyUnavailableError`；
  - P1-5：清洗在协程里执行，失败时返回部分结果；
  - P1-6：`triggerJob` 的路径拼接和正确前缀；
  - P2-13：`audit_deps.sh:7` 的包列表；
  - P2-14：P6 覆盖文件里缺 tender-service 的密钥。
- **修正**：上一版报告的 P2-4（「没配 MinIO 时生产环境启动会被拒绝」）不成立，原因见 P1-1，已删除。
- **复查后没有问题的方向**（避免重复排查）：
  - 后端：IAM 改人时的加锁顺序；授权目录的重读节流；Outbox 的租约回写；审计去重；爬虫同步的 advisory lock；分层没有反向 import。
  - 前端：导出都用 `applied`、没有裸 fetch、筛选都是多选；登录跳转防开放重定向；各类轮询在卸载时都会清理；echarts 和 SSE 都会释放。
  - 部署：`sync-to-server.sh --delete` 的排除清单完整；迁移没有 import 运行时 model；不可逆的 downgrade 都写明了理由；Docker 日志轮转由宿主机 `daemon.json` 配置。

---

## 四、整改执行记录（2026-11-19）

### 已完成并验证通过（全仓 `make check && make test-unit` 绿灯）

| 批次 | 提交 | 覆盖编号 | 摘要 |
| --- | --- | --- | --- |
| 阶段 0 止损 | `eafb716` | P0-2, P1-1, P1-4, P1-6(路径), P1-11, P2-1, P2-13, P2-14 | 修复四服务同名密钥校验覆盖与 compose 必填口令、备份恢复补齐智库、重打标路径修复、场景比对 500 分片与 ApiError 容错、停用任务不重试、CSP 放行 blob iframe、pre-commit/audit_deps/P6 补齐 thinktank 与 tender |
| 前端高优修复 | `a316ea0` | P1-10, P2-8(前端), P2-17, P2-18, P3-4, P3-21, P3-22, P3-23 | 智库预览请求时序保护+revokeObjectURL+路由切页保护+localStorage 容错+600s 超时+预览报错提示、解读重打标权限改为 `policy.base_tags`、日志抽屉时序/清空/错误态、信源链接协议校验防 XSS、403 个人资料重载去重与无权跳回首页 |
| 政策/招中标/智库 | `3178100` | P1-5, P1-12, P2-5, P2-7 | 政策导出正文改为工作线程短超时拉取清洗且故障抛 503、招中标源库拦截 `FOR UPDATE`/`INTO OUTFILE` 并设会话只读、智库预览存储故障不再回退占位摘要、智库模块档位缺失时 fail-closed |
| IAM 与网关安全 | `4c3443b` | P2-11, P3-1, P3-3, P3-7(CSRF) | 生产强制 `IAM_COOKIE_SECURE=true`、`/login` 增加 Origin 检查、非 HTTPS 网关补齐安全头、CSRF 改为 `hmac.compare_digest`、用户导出写入 `iam.user.exported` 审计、未知账号登录失败脱敏入库 |
| 平台与基础设施 | `e03b66c` | P1-8(连接/锁超时), P2-2, P2-10, P3-10, P3-15, P3-19 | 调度器心跳瞬时错误重试、Outbox 满批无等待排空、Postgres `max_connections=200`、全服务 Alembic 迁移 `SET lock_timeout='5s'`、全服务 uvicorn `--timeout-keep-alive 75`、`.dockerignore` 递归排除 `**/.env.*`、`make smoke` 严格校验状态码 |
| 批次 1：IAM 越权与审计 diff | `3b3fbf7` | P1-2, P3-2 | `user_guard.py` 限制非超管/无全局授权管理者仅可操作权限子集；`iam.user.updated` 审计记录前后字段 `changes` diff |
| 批次 2：AI 流水线幂等与并发 | `241394f` | P1-3, P2-3, P2-4 | 跨服务 AI 流水线新增 `client_run_id` 幂等键并预置快照、异步释放锁不再阻塞事件循环、AI worker 心跳绑定锁连接防事件循环阻塞、policy-service `stop_quietly` 兜底止损 |
| 批次 3：政策大表并发索引与防死锁 | `246ee13` | P1-9, P3-8 | `BaseTag` 并发创建默认排序联合索引（`postgresql_concurrently=True`）、末页/不足页跳过 `COUNT(*)`、`for_update` 固定按 `id` 排序 + 批量哈希查表 |
| 批次 4：招中标审计/连接池与智库流式 | `49e4f3f` | P1-7, P2-6, P2-8(后端), P2-22 | 招中标导出接入统一审计上报与线程安全 `LifoQueue` MySQL 连接池；智库上传孤儿清理补 `commit`；智库 `/content` 与 `/download` 改为分块 `StreamingResponse` |
| 批次 5：连接池治理/大下载分流与规则基线 | `8bbd666` | P1-8(全库引擎), P2-9, P2-15, P2-16, P3-11, P3-13, P3-14, P3-15, P3-17, P3-19 | 抽出 `create_service_engine` 统一全库 `statement_timeout`/`pool` 配额；调度器窗口函数消除 `2N` 查询；网关增加不缓冲大文件下载路由；worker 补 `init: true` 与 gateway 依赖顺序；证书续期失败 systemd 告警脚本；`scan_scope.py` 与 `check_code_rules.py` 规则收严 |
| 批次 6：前端体验、去重、无障碍与契约 | `4970389` | P1-6(轮询/过滤), P2-19, P3-18, P3-20, P3-25 | 重打标按 `targetIds` 精确跟踪+退避轮询+仅调 `load` 不重载筛选项+部分失败/超时分级提示；`ScrollPort` 改 rAF 合帧与内层可滚放行；`useCandidateExtras` 失败即刻 `markShown` 去重；AI 预览行键盘 Enter/Space 无障碍；OpenAPI 导出接口契约全覆盖 |
| 批次 7：文档与手册补齐 | 本次提交 | P2-13, P3-28 | 更新 `部署与维护.md`（补 `audit-worker`/`tender-service`/`thinktank-service`、`thinktank_db` 与 SSH 隧道说明、统一 `make SERVER=1 migrate`）、闭环 `系统全面审查与整改报告.md` `SEC-05` 引用并同步本报告执行台账 |

### 待外部环境/专项立项处理的剩余项
- **部署上线时随 `.env` 一并落地**：`P0-1`（服务端 `.env` 设 `POSTGRES_BIND_ADDR=127.0.0.1`，Navicat 改用 SSH 隧道）、注入 `TENDER_AUDIT_INGEST_SECRET` 与 `AUDIT_INTERNAL_CALLER_SECRETS`、全量重建容器与执行 `make SERVER=1 migrate`。
- **需云厂商控制台手工操作**：在云服务器安全组中移除 `5433` 端口公网入站放行规则（与服务端 `127.0.0.1` 绑定形成双保险）。
- **明确延后至独立专项基建的条目**：`P2-12`（Docker 内部网络彻底隔离与非 root 容器用户改造）、`P2-20`（Prometheus/Alertmanager 监控告警栈）、`P2-21`（独立 CI 流水线建设）。
