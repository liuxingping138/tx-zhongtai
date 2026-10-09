# 仓库、文档与服务器一致性审查（2026-10-08）

审查基线：`75342c0cb1b21850012c9ddd837c6384055efd01`，北京时间 2026-10-08 17:18–17:30 左右。审查开始时工作区干净。本次只新增审查报告及证据，未修复业务代码、提交 Git、部署、重启容器或写入服务器业务数据。

结论：项目已经部署且当前服务正常，但文档不能整体视为现行说明，质量检查通过也不足以证明关键安全与数据更新行为正确。确认 10 项代码/部署问题，其中 4 项 P1、6 项 P2；另列文档漂移和运维缺口。优先修复刷新重放事务、上传入口限制、PATCH 数据清空以及公网 HTTP 认证。

## 1. 覆盖范围与验证边界

- 清点全仓 659 个受 Git 管理文件：267 个 Python、61 个 TypeScript、43 个 Vue、31 个 Markdown；含公共包、四个服务、前端、迁移、脚本、Docker/网关和测试。详细范围见 [scope.json](scope.json)，逐份文档结论见 [documents.md](documents.md)。
- 全仓静态检查与现有单元测试；人工重点审查会话/RBAC、事务与并发、导入导出、爬虫同步/调度、Outbox/审计、部署备份和前端请求/状态管理。没有把清点或静态扫描等同于每行代码已被形式化验证。
- 31 份 Markdown 按现行规范、操作说明、设计决策、历史证据分类核对；4 份 OpenAPI 与当前应用对象结构化比较。历史截图、原始 Excel/SQL 作为资料清点，本次未重新进行视觉验收或逐单元格业务数据核验。
- SSH 只读检查服务器 `1.119.196.77`：容器状态、源码哈希、镜像内 Python 源码哈希、非敏感运行配置、Alembic current/check、首页 HTTP 状态。
- 不在业务库运行会写入的 P6、E2E、越权探针、导入、重放攻击或恢复演练。本地针对性复现使用模拟仓储/会话或 TestClient；证据级别在各项标明。
- 没有执行在线 CVE/依赖漏洞数据库扫描、外部端口扫描、压力测试和数据库恢复演练；不声称不存在其他问题。

## 2. 线上现状

| 检查 | 结果 |
| --- | --- |
| 容器 | 11 个 running；配置健康检查的 7 个均 healthy；其他 4 个没有健康检查状态 |
| 网关首页 | 服务器本机访问 `http://127.0.0.1:8091/` 返回 200 |
| 服务器工作目录 | 对比 493 个受版本管理的非图片/表格/SQL/锁文件，哈希全部与本地一致；不包含服务器多余未跟踪文件检查 |
| policy-service / policy-worker | 各核对 83 个 Python 文件，与本地一致 |
| codebook-service | 核对 58 个 Python 文件，与本地一致 |
| iam-service / iam-worker | 各核对 81 个 Python 文件，仅公共包 `platform_common/excel.py` 与本地不同 |
| audit-service | 核对 52 个 Python 文件，仅公共包 `platform_common/excel.py` 与本地不同 |
| 四库迁移 | IAM `a8c4d2e3f702`、审计 `d3c9e8f1b302`、码表 `f6a4c5d6e803`、政策 `e6f7a8b9c614`，均为各自 head |
| 模型漂移 | 直接执行四个容器内 `alembic check`，均为 `No new upgrade operations detected.` |
| 运行环境 | 四个 API 服务均为 development；IAM `cookie_secure=false`，Access Token 28800 秒 |
| 端口 | 网关绑定 8091；PostgreSQL 绑定 `0.0.0.0:5433`；四个 API 没有宿主机映射；Redis 当前运行容器没有宿主机映射 |

镜像中的公共 Excel 差异说明“工作目录已同步”不等于“所有镜像已更新”。本次未发现 IAM/审计正常业务路径使用该 Excel 模块，故不单列为线上功能故障。前端容器在运行，但未做构建产物与本地源码的可重复构建证明。

Redis 与部署文档的“绑定 127.0.0.1:6380”不一致；当前没有端口映射反而缩小了暴露面，不应为了符合旧文档而直接开放端口。PostgreSQL 的公网地址绑定已确认，但未验证外部防火墙允许范围或 TLS，不能据此声称任意公网来源均可连接。

原始只读结果见 [server-readonly.txt](server-readonly.txt)。

## 3. 需要修复的问题

### F01 · P1 · 刷新凭据重放导致的会话撤销被回滚

位置：`services/iam-service/app/application/auth_service.py:147–158`，`services/iam-service/app/core/database.py:18–25`。

超过 30 秒宽限期的旧刷新令牌再次使用时，`refresh()` 先撤销整个 family 并入队 `auth.refresh.replayed`，随后抛出 `UnauthenticatedError`。请求数据库依赖对所有 Exception 执行 rollback，撤销与审计一起消失。该请求会返回 401，但新刷新凭据及该会话的访问凭据不会因此被撤销，违背重放保护目的。

本地通过真实 `AuthService.refresh` 和真实 `get_db_session` 控制流、模拟数据库确认：`revoke_called=1, audit_enqueued=1, commits=0, rollbacks=1`。未向线上发送重放请求。

建议：在返回拒绝前，以明确的事务边界提交撤销和安全审计；不能全局把所有业务异常改成提交。补数据库集成测试，确认拒绝响应后另一个事务看到 `revoked_at` 和审计事件，且新令牌也不能继续使用。

### F02 · P1 · 上传大小限制在框架接收完整文件之后才执行

位置：`services/policy-service/app/api/interpretations.py:122–130`；同类 policy/codebook 上传接口；`packages/platform-common/platform_common/http_utils.py:46–62`；`deploy/gateway/dynamic.yml`。

`UploadFile = File(...)` 使 FastAPI 先执行 multipart 解析，再求解权限依赖，最后才进入路由中的 `read_upload_within_limit`。当前网关只有压缩中间件，没有请求体总大小限制。现有校验限制的是从临时文件读入业务内存的大小，不能限制接收阶段的网络/临时磁盘占用；未认证客户端也能先上传超限文件。

本地在实际政策应用中把鉴权依赖替换为固定 401，统计 `UploadFile.write`：21 MiB（22,020,096 字节）全部在鉴权拒绝前写入，最后才返回 401。没有在服务器执行大文件测试。

建议：在网关或 ASGI 接收层实施总字节计数/上限，并覆盖无 Content-Length 的流式请求；尽可能在解析文件前验证身份。保留业务层现有校验。另给 Excel 解压后大小、行列数和并发解析设界限，20MB 压缩文件本身不能限制解析后的资源占用。

### F03 · P1 · PATCH 会把未提交字段清空

位置：`services/codebook-service/app/api/scenarios.py:137–145`、`app/api/schemas.py:15`、`app/application/scenarios.py:129`；六张业务表的 PATCH 均使用类似 `body.model_dump()`。

创建与修改共用带大量空字符串默认值的模型。对行业场景发送 `{ "version": 1, "scenario_tag": "changed" }` 后，`model_dump()` 把其他字段补为空，业务层因此认为这些字段被显式清空。虽然业务层用 `data.get(field, old)` 保留缺省字段，但默认值已由 API 层填入，这个保护不会触发。

本地用真实 Pydantic 模型和更新函数、模拟仓储复现：仅提交 2 个键，30 个未提交业务字段被清空。当前前端主要提交整份表单，通常遮住了此问题；部分字段调用、旧客户端或未来批量编辑会触发。其他表还可能因遗漏必填字段返回 422，不能宣称六表每种部分更新都表现相同。

建议：区分 Create/Patch 模型，Patch 仅传 `model_dump(exclude_unset=True)`，明确空字符串与未提供的差别，保留必要字段校验和版本号。补 HTTP 层回归，不能只测直接调用业务函数。

### F04 · P1 · 服务器仍用公网 HTTP 承载认证

位置：`deploy/compose/docker-compose.yml:87`、网关 8091 映射；`docs/guides/部署与维护.md:5–11`。

已确认当前入口为 HTTP，IAM 为 development 且 Refresh Cookie `Secure=false`。按该公开入口登录时，密码、Bearer Token 和 Cookie 缺少 TLS 传输保护。这是当前部署配置事实；没有证据表明已发生窃取，也没有将该环境擅自认定为正式生产。

建议：为实际访问入口配置 HTTPS、重定向 HTTP，切换安全 Cookie，并验证反向代理/Origin 配置。现有生产模板不能直接替换使用（见 D06）。PostgreSQL `0.0.0.0:5433` 另应核对访问白名单、TLS或隧道，不直接改动以免中断现有连接。

### F05 · P2 · Python 镜像构建没有使用服务锁文件

位置：四个服务 Dockerfile，例如 `services/policy-service/Dockerfile:17–26`。

Dockerfile 只 COPY `pyproject.toml` 和 `.python-version`，没有 COPY 本服务 `uv.lock`，随后执行未冻结的 `uv sync`。四个服务的镜像会在构建时按版本范围重新解析依赖，本地测试使用的锁文件不能保证与下次发布一致。

抽查当前线上/本地 fastapi、starlette、pydantic、sqlalchemy、httpx 五个包版本一致；本问题是构建不可重复，并非声称此次已出现依赖版本故障。

建议：把服务锁文件纳入构建，使用 frozen/locked 安装并验证构建用 uv 与锁格式兼容，生成发布依赖清单。

### F06 · P2 · 文档宣称可调的配置没有传入 Compose 容器

位置：`deploy/compose/docker-compose.yml` 各服务 environment；`docs/guides/配置说明.md`。

Compose 使用 `.env` 做变量插值，但没有服务级 `env_file`，也没有挂载根 `.env`。因此只在服务器 `.env` 添加下列变量不会进入容器：

- `IAM_LOGIN_MAX_FAILURES`、`IAM_LOGIN_MAX_FAILURES_PER_IP`、`IAM_SESSION_RETENTION_DAYS`。
- `POLICY_IMPORT_MAX_BYTES` / `POLICY_EXPORT_MAX_ROWS`、码表对应项。
- `POLICY_CRAWLER_HEALTH_NORMAL_DAYS` / `POLICY_CRAWLER_HEALTH_WATCH_DAYS` 等同步设置。

此外 `IAM_COOKIE_SECURE` 和 Access Token TTL 在 YAML 中硬编码；部署手册写的 `IAM_ENVIRONMENT=production` / `AUDIT_ENVIRONMENT=production` 不控制当前 Compose，实际插值变量是全局 `ENVIRONMENT`。

建议：逐项显式透传并写清配置作用位置，政策 API 与 worker 保持相同阈值；只输出白名单非敏感参数检查生效，不打印完整配置/环境。

### F07 · P2 · migrate-check 会把失败报告为成功

位置：`Makefile:97–103`。

命令使用 `set -e`，但把 `alembic check` 管道到 `tail -1` 且没有 `pipefail`。迁移检查退出非零时，shell 看到的仍是 tail 的成功，make 返回 0，可令发布门禁误放行。

本地将 COMPOSE 替换为输出错误并退出 42 的无副作用脚本：四次都输出 ERROR，`make migrate-check` 最终仍为 0。线上四库本次是直接执行检查，均通过，未依赖这个错误门禁。

建议：启用 `set -euo pipefail` 或显式保存/传递检查退出码；保留完整诊断。

### F08 · P2 · 密钥扫描漏掉中文文件名

位置：`scripts/scan_scope.py:43–51`。

`git ls-files` 默认对非 ASCII 路径进行引用/转义，代码把带双引号和转义的输出直接交给 Path，`is_file()` 为 false 后静默跳过。在当前仓库实测有 22 个此类路径，包括中文文档。因此 `secrets_scan_clean` 不能证明这些文件被扫描。没有发现或披露实际泄漏的凭据。

建议：使用 `git ls-files -z` 按 NUL 分割，加入中文文件名回归；重新执行扫描。当前正则也仅覆盖少数形式，不应将其当作完整的凭据审计。

### F09 · P2 · P6 刷新重放验收与现行宽限语义冲突

位置：`tests/p6/accept.py:243–254`；`services/iam-service/app/core/config.py:38`；`deploy/compose/docker-compose.p6.yml`。

测试在旋转后立即重放旧令牌并断言 401，但现行默认 30 秒宽限期内明确返回 200；P6 配置未覆盖宽限期。常规执行速度下这一断言会失败，且只断言响应码，没有检查撤销是否持久化，无法覆盖 F01。

本次没有运行整个 P6 栈；结论来自测试序列、默认配置和业务分支的直接核对。

建议：分别覆盖宽限期内并发重复成功、宽限期外重放拒绝，以及 family 撤销与审计落库；用受控时钟或专用测试配置避免等待和时间抖动。

### F10 · P2 · 恢复脚本没有恢复对象所有权

位置：`scripts/restore.sh:60–65`。

以 PostgreSQL 超级用户执行 `pg_restore --no-owner` 后，脚本只给应用账号 `GRANT ALL PRIVILEGES`，却输出“属主权限已还给”。表/序列的 owner 并没有恢复为应用账号；表的普通权限不包含 owner 才能执行的 ALTER/DROP。恢复后 CRUD 可能正常，但后续由应用账号运行 Alembic 表结构迁移会失败。

本项为脚本与权限语义审查，未在业务库执行恢复。脚本限于隔离库的保护应保留。

建议：恢复时使用正确目标 role 或显式恢复受控对象的 owner，避免对共享实例全局 REASSIGN；验收需包括“恢复后应用账号执行下一次迁移”，不只检查数据数量/登录。末尾 `uv run` 也应与现行运维规范统一为已安装的 `.venv/bin/python`。

## 4. 文档一致性

### D01 · README 与当前部署、开发范围直接矛盾

`README.md:65,116` 仍要求日常本机 `make dev-up`，与 `.cursor/rules/dev-vs-p6.mdc`、CLAUDE 和服务器部署手册相反；`:124` 写“业务表、业务 API、业务页面仍未开发”，与六张业务表、两个爬虫页面、任务调度的实现相反。快速开始还缺首次非 P6 环境所需的 seed/admin-create。

建议以部署手册为日常入口，本机 Compose 明确标成可选隔离环境；删除“业务未开发”的现状结论，补上调度、码表地区与实际初始化步骤。

### D02 · 三份 OpenAPI 已过期

| 文档 | 文档路径数 | 当前路径数 | 缺少路径数 | 其他差异 |
| --- | ---: | ---: | ---: | --- |
| iam.json | 22 | 26 | 4 | 用户/角色列表参数、请求 schema 有变化 |
| audit.json | 5 | 7 | 2 | 列表多选参数有变化 |
| codebook.json | 10 | 21 | 11 | 缺地区码表及筛选选项端点，schema/参数有变化 |
| policy.json | 35 | 35 | 0 | 完整结构一致 |

缺失的 17 个是路径数，不等于 HTTP 操作数。完整差异见 [openapi-diff.json](openapi-diff.json)。IAM 缺角色复制/成员/用户实际权限；审计缺 options/search；码表缺地区接口及多个 options/search。

`docs/README.md:34` 又错误描述为“从运行中服务导出”，实际 `scripts/export_openapi.py` 本地导入应用，不连接运行服务；`scan_scope.py` 也没有做 OpenAPI 与实际路由一致性检查。

建议重新生成全部四份，并增加生成结果无 diff 检查。本次为了保留过期证据，没有覆盖现有 OpenAPI 文件。

### D03 · 主键/导入导出分析的“现状”已部分过期

`docs/design/业务表主键与导入导出分析.md:77` 写“六张表下载……不传页面筛选……全表数据”，而现行前端使用 `filtersForExport(listQuery.applied)`，后端 count/list/export 共用筛选并限制 10 万行。该句会误导用户把筛选导出当全量导出。

六表导入去重/新增/更新差异大体仍符合代码；候选主键调整明确标记“未经确认”，应保留待决策状态，不把建议误改成既定实现。

### D04 · UI 文档列清单与本地入口过期

`docs/guides/UI开发规范.md:60–67` 中信源标为 16 列、解读标为 27 列，当前 `SourceList.vue` 为 13 列、`InterpretationList.vue` 为 26 列。其他表含动态映射，不能只按 `prop` 文本次数统计。现行 UI 规范“所有字段在列设置/详情可访问”也应结合已隐藏的标识/地区编码重新确认。

同文件第 5 节仍要求本机重建 8080；`docs/guides/任务调度.md:38–46` 使用 `docker compose` 和 8080，而目标服务器实际使用 `docker-compose`、8091。两者应引用统一服务器发布章节，避免维护三套命令。

DESIGN.md / UX-CONTRACT.md 的桌面范围、双层导航、权限、筛选和调度规则整体能在代码找到对应实现；仍有“爬虫等未完成模块”旧措辞。此结论是源码一致性，不是本次视觉或无障碍验收。

### D05 · CLAUDE、公共包与历史决策有旧描述

- `packages/platform-common/README.md:13` 指向不存在的 `platform_common.auth_client`，实际是 `authz.py` / `service_authz.py`，JWT 校验在 IAM；公共 Excel、filters、options 等能力也未列全。
- CLAUDE 的服务器入口/主要服务边界基本正确；“授权四档逐档包含”实际只列 READ/EXPORT/FULL，NONE 表示无记录，应澄清；统一写“租约 5 分钟”不适用于 IAM 默认 30 秒租约。
- `docs/design/实现决策.md` 保留历史 900 秒 access TTL、READ/FULL 两档、早期仅两库等记录，后续未完整追加取代说明；当前是 8 小时、三种已授权等级、四库。不能抹去历史，应追加“现行覆盖”索引。
- `docs/design/业务数据运营平台公共基础框架设计.md` 是设计基线，不是逐项实现保证；应显式指向现行参数/权限升级决定。
- `docs/开发进度.md` 是按日期保存的历史记录，最后记录到 9 月；服务器迁移和 10 月发布现状没有完整同步。旧测试通过记录只能代表当时版本。

### D06 · HTTPS 模板与当前路由方式不兼容

`deploy/gateway/traefik.prod.yml.example` 使用 Docker Provider，当前 Compose 没有路由 labels，也没有挂载 Docker socket；当前 dynamic.yml 路由只挂 web，而模板会把 web 重定向到 websecure。仅复制模板并更换域名/证书，无法得到现有业务路由的可用 HTTPS 部署。

这份文件已标为模板，不当作当前线上缺失路由故障；但应补全匹配文件 Provider 的 TLS 路由、证书和 Compose overlay，使其真正可操作。

### D07 · 业务服务器备份操作缺口

部署手册坦诚说明备份/恢复脚本只允许隔离库，代码也确实拒绝 `iam_db/audit_db/policy_db/codebook_db`。因此“已交付备份恢复”只代表隔离验收能力，不能作为当前业务库已有日常备份保障的依据。

仓库缺当前服务器业务四库的可执行备份/保留/异机存储/恢复演练流程。未核对服务器外部备份平台和管理员私有任务，不能断言服务器从未备份。建议补只读业务备份入口和有保护的恢复手册，并记录恢复点/恢复时间目标与演练结果；不要直接移除现有恢复白名单。

### D08 · 历史证据不应按现行手册修改

`docs/archive/` 的 9 份 Markdown 及 `docs/reviews/` 原有 7 份 Markdown 是带日期的历史计划、截图说明、验收或设计探索。里面的 localhost:8080、旧测试数量和当时 UI 可以保留；应经索引明确“只供追溯”。例如 9 月 23 日记录“运维调用同步”不代表 9 月 29 日后仍未接入 policy-worker。不要批量把这些历史记录改成“服务器现已验证”。

## 5. 检查结果及测试盲区

| 检查 | 结果 |
| --- | --- |
| make check | 通过：五个 Python 包 ruff/mypy、前端类型/构建/lint、现有范围与密钥扫描 |
| 后端 pytest | 288 passed，11 skipped（公共包51、IAM53、审计18、码表46、政策120） |
| 前端 Vitest | 12 文件、68 passed |
| 合计 | 356 passed，11 skipped |
| 服务器 Alembic check | 四库直接检查均通过 |
| OpenAPI 对比 | policy 一致；其余三份不一致 |
| 定向复现 | F01、F02、F03、F07 均确认，见本地脚本和说明 |
| P6/E2E | 本次未运行；不能把历史“P6完整验收”视为当前全量回归已通过 |

证据：[静态检查输出](check-output.txt)、[单测输出](unit-output.txt)。构建有 Element Plus chunk 约 998KB（gzip 约321KB）的告警；这是性能改进项，未当作构建失败。现有依赖有 Starlette/AnyIO 弃用警告。

现有测试的价值是覆盖了路由安全分级、导出筛选一致、Excel 公式转文本、版本冲突部分路径和调度领域规则。但事务持久化、HTTP PATCH 默认值、上传解析顺序、部署门禁退出码没有被当前单测有效覆盖。11 项跳过也不能算通过。仓库未发现已提交的 GitHub Actions/GitLab CI 配置，质量门目前依赖手动执行。

复现命令在仓库根目录执行（均不需要服务器或真实数据库）：

```sh
services/iam-service/.venv/bin/python docs/reviews/repository-audit-2026-10-08/repro-refresh.py
services/codebook-service/.venv/bin/python docs/reviews/repository-audit-2026-10-08/repro-patch.py
services/policy-service/.venv/bin/python docs/reviews/repository-audit-2026-10-08/repro-upload.py
```

`repro-upload.py` 仅本地 TestClient 构造 21MiB 文件，鉴权固定拒绝，不连接源库或业务库。F07 的复现方法为将 COMPOSE 覆盖成输出错误并退出 42 的临时脚本，观察 make 最终退出码 0。

## 6. 建议处理顺序

1. 先修 F01/F02/F03，并补事务与真实 HTTP 层回归；随后安排 HTTPS 与数据库访问边界核对。
2. 修复迁移/扫描门禁、P6 过期断言，锁定镜像依赖、透传配置并验证恢复后的迁移能力。
3. 更新 README、现行操作手册、公共包说明和三份 OpenAPI，保留历史证据原貌；文档生成/一致性检查纳入质量门。
4. 为服务器建立业务备份与恢复演练记录、发布版本/镜像摘要清单和运行配置漂移检查，再进行隔离全量集成/E2E 验收。

本次是审查交付，所有上述修复仍待实施。
