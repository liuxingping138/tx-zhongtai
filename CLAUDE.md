# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

一体化业务数据平台，最终包含：客户、招投标、政策、场景、爬虫监测、码表管理、系统管理。
主要业务数据围绕「客群」串联；爬虫监测是独立模块，与客群无直接关联。

当前进度：公共框架已到 P6（账号/会话/RBAC、Outbox、审计、隔离验收、备份恢复、OpenAPI），
政策三张表（信源、基础标签、解读）与码表三张表（政策类型、行业场景、省市区编码）已接入，
爬虫监测已接入（只读统计页，数据来自外部爬虫库采集总表的按天聚合，按网站统计）。
**客户、招投标仅有占位目录**，未开发——不要为它们提前暴露无功能入口或做过度抽象。
其余文档按 设计决策 / 操作手册 分类，索引见 `docs/README.md`。文档只写与现有代码一致的现状，过时内容直接删除，历史留在 git 里。

## 常用命令

当前运行环境是 `https://1.119.196.77`（8091 HTTP 自动跳转）。在 Mac 上改代码并推送到 GitLab，再用 `scripts/sync-to-server.sh` 同步到服务器构建。不要在服务器 `git pull`，不要在本机 `make dev-up`。步骤见 `docs/guides/部署与维护.md`。

```bash
make check            # 质量门：Python ruff+mypy，前端 type-check+build+lint，范围与密钥扫描，文件行数与忽略注释原因
make test-unit        # 后端 pytest + 前端 vitest（不需要本机 Docker）
make export-openapi   # 从本地 FastAPI 应用导出 OpenAPI；前端 src/api/contract.test.ts 拿它核对每个接口封装的方法和路径
make hooks            # 启用 .githooks：提交前代码规则 + ruff、提交信息格式、推送前跑 check + test-unit + audit-deps
make audit-deps       # 依赖漏洞扫描（pip-audit + pnpm audit，需要外网）
```

没有 CI，git 钩子是唯一的自动关卡。新克隆的仓库先 `make hooks`（`make bootstrap` 已包含）。

服务器上的迁移、种子、爬虫同步和冒烟用该文档里的 `docker-compose` 命令，不用下面这些依赖本机 Compose 的 Make 目标。

运维类：`make iam-session-cleanup`（清理失效会话/令牌）、`make audit-cleanup`（清理到期审计）、
`make outbox-replay`（重放 dead/failed 事件）、`make admin-create`、`make seed-area-codes`。

### 跑单个测试

```bash
# 后端：在对应服务目录下
cd services/policy-service && uv run pytest tests/test_export_limit.py -q
cd services/policy-service && uv run pytest -q -k "export_rejects"

# 前端单测
cd frontend && pnpm vitest run src/composables/useFilterOptions.test.ts

# e2e（Playwright）默认指向 P6 的 8090。不要改指到 8091 的业务库。
cd frontend && pnpm exec playwright test filter-options
cd frontend && pnpm exec playwright test --grep "date range"
```

### 前端改动必须在服务器上重建

入口是 `https://1.119.196.77`，页面来自服务器上的 frontend 镜像，不是热更新。改了前端源码后按 `docs/guides/部署与维护.md` 同步并重建 `frontend`，只刷新浏览器不会生效。

### 开发部署机 vs 本机 / P6

日常只使用 `1.119.196.77`。本机 Docker 栈已停止。分工：`make check` / `make test-unit` 在 Mac 上跑（不要 Docker）；
集成和 e2e 在服务器上跑 P6：`bash scripts/p6-on-server.sh`（同步 → 集成 + e2e → 一定 `p6-down`），
Mac 不用开 Docker。P6 与业务栈同机但隔离（项目名 `tx-zhongtai-p6`、独立卷与库，网关只绑 `127.0.0.1:8090`），
不要把 Playwright 打到 8091 的业务库。同步一律用 `scripts/sync-to-server.sh`，排除列表只维护那一份。脚本带 `--delete`，
服务器上独有的文件（`.env`、密钥、P6 运行时文件等）全靠排除列表保护，新增服务器独有文件前先加进去。
Navicat 连 `1.119.196.77:5433`。

## 架构

### 服务边界

```
frontend/              Vue 管理端（pnpm）
services/
  iam-service/         账号、会话、RBAC、菜单；Compose 里 iam-worker 共用此镜像
  audit-service/       审计写入、查询、到期清理
  policy-service/      政策：信源、基础标签、解读、爬虫监测
  codebook-service/    码表：政策类型、行业场景、省市区编码
  customer-service/    占位，仅 .gitkeep
  tender-service/      占位，仅 .gitkeep
packages/platform-common/   跨服务公共包（见下）
deploy/gateway/        Traefik 静态+动态配置
deploy/compose/        docker-compose.yml、Postgres 初始化脚本
```

每个服务一套独立数据库（`iam_db` / `audit_db` / `policy_db` / `codebook_db`），
服务间不直连对方的库。

### 关键：公共能力一律放 platform-common

policy 和 codebook 的基础设施代码高度重复，已统一下沉。**新增业务服务时不要复制这些文件**：

| 能力 | 公共模块 | 服务内保留 |
| --- | --- | --- |
| 时钟、北京时间格式化 | `clock.py` | 无 |
| ORM Base | `orm_base.py` | 无 |
| 安全分级、Outbox 状态枚举 | `enums.py` | 无 |
| 操作者身份 | `actors.py` | 无 |
| 列表/导出筛选类型 | `filters.py` | 无 |
| 上传限流、统一响应 | `http_utils.py` | 无 |
| Excel 解析与生成 | `excel.py` | 各表列清单 `domain/fields.py` |
| 表头匹配、ColumnSpec | `columns.py` | 同上 |
| Outbox 仓储 | `outbox.py` 的 `OutboxRepository` | 绑定本服务 ORM model |
| 鉴权依赖 | `service_authz.py` | 绑定服务名与 Settings |
| 审计入队与投递 | `audit_emit.py` 的 `AuditEmitter` | 本服务的 `_EVENT_META` |
| 筛选项预览与搜索 | `options.py` | 字段映射表 |

### 分层

`api/`（路由、Query 参数、权限依赖）→ `application/`（业务编排、审计入队）→
`repositories/`（SQLAlchemy 查询）→ `domain/`（models、fields 列清单）。
`core/` 放配置、数据库等。依赖方向由各服务的 import-linter 契约强制（`make check` 跑 `lint-imports`）。
policy-service 内部再按领域分成 `policy/`、`crawler/`、`scheduler/` 三个子包，每个子包内部仍是这四层，
跨领域共用的审计入队、鉴权依赖、Outbox 表放 `app/common/`。

### 鉴权链路

业务服务不自己校验 JWT。每个受保护路由挂 `Depends(require_*_permission(RESOURCE, action))`，
它经 `platform_common.authz.AuthzClient` 调 iam-service 的 `/internal/v1/authorize`。
**依赖失败一律返回 503，绝不当作放行**。网关不启用 ForwardAuth，授权全在服务内执行。

路由必须带 `@classified(SecurityClass.*)`，`tests/test_route_security_class.py` 经
`platform_common.route_audit.audit_routes` 强制检查：声明为 `resource_authorized` 的路由必须真的挂了
权限依赖，挂了依赖的也不能错标成别的分级。新写的 `require_*_permission` 工厂要调 `mark_permission_dependency`，
否则体检认不出来。测试里要遍历路由用 `route_audit.iter_api_routes(app)`：`app.routes` 里是未展开的
`include_router` 对象，直接遍历什么都找不到，检查会空跑通过。

### 爬虫监测是只读统计，数据靠同步进来

数据源是外部爬虫库（MySQL `crawler2021`，前面挂 ShardingSphere 代理），**页面永远不查它**。
`app/crawler/application/crawler_sync_v2.py`（入口 `python -m app.cli.sync_crawler_v2`，`make crawler-sync`）
只读采集总表 `csys_policy_info_source_all`，按天聚合后写本服务的三张表：
`policy_crawler_site_daily`（网站×采集日，按天整体替换）、`policy_crawler_sites`（页面唯一读取的快照）、
`policy_crawler_v2_sync_runs`（水位与状态）。资源编码、路由、表名里保留 `v2` 字样是历史原因，页面和菜单叫「爬虫监测」。

- 监测单位是「网站名称 + 省份 + 地市」的**原始值**（用户确认不做别名归一），停更天数按最新入库日期算
- 核心指标是「停更天数」不是「今天有没有出数」：政策网站本来就不是天天更新
- 首次必须回填到爬虫库最早的采集日期；没有成功回填过时日常同步直接报错，不用短窗口算出偏小的总量
- 聚合按 `collect_date`（采集日）分桶，日常按入库时间水位找到受影响日期，再加当天重算，不固定每天全量。
  `--days` / `--since` 是人工指定范围，适用于初始化、口径升级或数据修复
- 同步持有 advisory lock（键见 `app/crawler/repositories/crawler_v2.py`），概览据 `pg_locks` 把停在 running 的批次识别为中断
- ShardingSphere 不支持 `REGEXP` 和多列 `COUNT(DISTINCT)`，写源库 SQL 时用 `LIKE`、单列聚合
- 页面图表只读本地表：采集趋势按日期范围读 `policy_crawler_site_daily`（主键以采集日开头，一年约 26ms），健康结构和省份分布读快照。
 省份图按「省份」字段的分类排，单独占一整行、左右两列：32 个省级行政区以及香港、澳门、全国、国央企都在列（`province_categories`），没有数据的补 0。
 同一分类的不同写法只在图表里合并（`app/crawler/domain/provinces.py`），网站身份、表格和筛选仍用原始值
- 卡片「较上周」读 `policy_crawler_status_daily`（每日状态分布）。同步重建快照后按快照写当天一行；最近 90 天缺的日期
 由同步用按天统计推算补齐（口径同快照：每个网站最后入库日期），推算一次约 10 秒，所以只在缺数时跑、页面不能现算
- 整表 `GROUP BY` 在代理后跑十分钟都出不来，带 `collect_date` 的单天聚合只要 1.4 秒：全量统计按天循环，别写一条大 SQL

### 系统管理：给人分配角色即授权

菜单四项：用户管理、角色与权限（角色和权限分配在同一页）、操作日志、任务调度。给人分配角色的所有入口
（建人带角色、用户详情调角色、角色侧增删成员、复制角色）都要求 `system.permissions:grant`，
而该资源只能授予超级管理员角色——这是防止「用户管理员给自己加超级管理员」的关键约束，改入口时不要放宽。
权限页的模块分组、可选档位和中文说明都由 `frontend/src/permissions/catalog.ts` 从资源树推导。

删除用户是逻辑删除：`status` 置 `UserStatus.DELETED`，同时吊销会话、清空角色，行保留以便操作日志对得上人。
新写的用户查询（登录、列表、按名查找、改人前的存在性检查）都要排除 `DELETED`，
否则已删账号会重新出现或能登录。

没有授权记录时是 `NONE`，不表示另一档权限。已授权的三档逐档包含：`READ`（查看）< `EXPORT`（查看+导出）< `FULL`（含新增、编辑、导入）。新增模块时导出动作
必须标 `GrantLevel.EXPORT`，`test_every_export_action_requires_export_tier` 会拦；前端导出按钮用 `auth.canExport`。
越权探针 `tests/authz_probe.py` 会自建 `越权探测-*` 角色与 `probe.*` 账号，在开发栈跑完记得清掉。

### 审计走 Outbox

业务写操作调 `enqueue_event(...)` 写本服务的 `*_outbox` 表（与业务同事务），
再由 worker 投递到 audit-service。失败按指数退避重试，超上限置 dead，可用 `make outbox-replay` 重放
（覆盖 iam/policy/codebook，`OUTBOX_SERVICES=policy-service` 只跑一个）。

认领时置 delivering 并写 `lease_until`，回写只在租约没被别人重新认领时生效。进程在投递途中重启，
租约到期后会被重新认领，不会永远卡在 delivering。IAM 默认租约 30 秒（`IAM_WORKER_LEASE_SECONDS`）；
policy / codebook 走公共 Outbox，默认 5 分钟。审计服务按 `event_id` 去重，重投不重复入库。

`audit_events` 对审计服务的应用账号只有 SELECT/INSERT，删改权被收回；到期清理用独立的清理账号
（`make migrate` 里 `provision-audit-cleanup` + `app.cli.grant_cleanup` 负责授权）。
新的审计写入逻辑不能依赖 UPDATE/DELETE，换库或重建后要重新跑这两步。

### 任务调度

系统管理的任务调度页面 `/system/scheduler` 使用政策服务接口 `/api/v1/policy/scheduled-jobs`，
资源 `system.scheduler` 归属 `policy-service`；READ 可查看，FULL 可设置计划和手动执行。
`policy-worker` 独立容器持 PostgreSQL 全局会话锁，按北京时间每日调度任务。目前只有一项：爬虫监测增量同步
（任务编码 `crawler-v2`，默认 10:10，时刻可在页面改）。
配置、执行队列、重试状态持久化在政策库；重启错过多天只合并一次增量。
初始化无成功水位时拒绝自动同步，需要先完成历史回填，不能自动退回短窗口。
worker 必须连接可出站的 gateway 网络以访问外部 MySQL，只有 internal data 网络会无法连接源库。
详细规则和验收见 `docs/guides/任务调度.md`。

### 网关

Traefik 文件 Provider（非 Docker Provider）。路由优先级：
具体业务前缀（100）> 未接入业务的 `/api/v1` 兜底 404（50）> 前端 SPA 兜底（1）。
`/health/*`、`/internal/*` 未声明路由，不对外暴露。全部路由挂了 `compress` 中间件，
xlsx/zip/图片在 `excludedContentTypes` 里排除。

## 硬性开发约定

### ORM 中文 comment（Cursor 规则，强制）

新建或修改表/列**必须**写中文 `comment`，PostgreSQL 会落到 `COMMENT ON`，Navicat 直接可见。

- 表：`__table_args__` 带 `comment="中文表名"`；有约束时把该字典放 tuple 最后一项
- 列：每个 `mapped_column(...)` 带 `comment="中文列名"`，与页面/Excel 表头对齐
- Alembic `create_table` / `add_column` 同步带 comment；`COMMENT ON ... IS` 用 SQL 字面量，不能绑参数
- 历史迁移不能 import 运行时的 model 模块（如 `app.domain.models`、政策服务的 `app.models`）/ `Base.metadata`：模型以后新增的列在那一步还不存在，
  空库从头迁移会报 column does not exist。需要表结构时像 `*_chinese_comments` 那样冻结成字典
- `alembic_version` 不用注释

```python
class Source(Base):
    __tablename__ = "policy_sources"
    __table_args__ = (
        UniqueConstraint("site_code", name="uq_policy_sources_site_code"),
        {"comment": "信源管理"},
    )

    site_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="网站名称")
    site_code: Mapped[str] = mapped_column(String(16), nullable=False, comment="网站编码")
```

### 数据库会话依赖必须是 function 作用域

路由里一律写 `Depends(get_db_session, scope="function")`。`get_db_session` 在 yield 之后提交事务，
FastAPI 默认的 request 作用域要等响应发出后才执行这一步，提交失败（如并发撞唯一约束）时客户端已经拿到成功响应、
数据却没落库。`scripts/check_code_rules.py` 会拦住不带 scope 的写法。

### Excel 必须放线程池，上传必须边读边限流

openpyxl 是纯 CPU 同步库，每个服务只有一个 uvicorn worker，直接在协程里调用会占住整个事件循环
（实测 5 万行导出阻塞 4.2s，期间该服务所有请求挂起）。

- 业务层一律用 `parse_sheet_async` / `build_workbook_async` / `encode_skipped_file_async`，
  同步版本只留给单测
- 上传用 `read_upload_within_limit(file, settings.import_max_bytes)`。
  先 `await file.read()` 再判断长度，体积上限形同虚设
- 导出前用 `count_filtered` 校验 `export_max_rows`（默认 10 万），超限不执行查询
- 自己拼 Excel 时逐行用 `platform_common.excel.append_text_row`，别直接 `sheet.append`：openpyxl 会把 `=` 开头的
  字符串存成公式，导出的网站名、导入内容里带 `=HYPERLINK(...)` 就成了打开即执行的活公式

### 列表与导出共用一份筛选定义

仓储里的 `FILTER_COLUMNS` + `_conditions` 同时供 `list_items` / `count_filtered` / `list_filtered` 使用，
从结构上杜绝列表和导出条件走偏。未知字段直接 `KeyError`（API 层转 422），
不允许静默忽略——否则导出会悄悄变成导全表。
`tests/test_export_filter_parity.py` 会强制三者一致。

### 前端复用规范

改页面前读 `DESIGN.md`、`UX-CONTRACT.md`、`docs/guides/UI开发规范.md`。优先复用：

`ListPage` / `FilterBar` / `FilterSelect` / `ScrollPort` / `BusinessTable` / `ColumnPicker` /
`GroupedFields` / `UserAccountMenu`，图表用 `BaseChart`（ECharts 按需注册在 `components/charts/echarts.ts`），基础视觉用 `theme.css`。

新增业务列表页 = 一份 `fields.ts`（`TABLE_COLUMNS` / `SUMMARY_KEYS` / `EDITOR_GROUPS`）+ 页面，照 `modules/policy/base-tags/BaseTagList.vue` 组装：

- 查询与加载：`useListQuery`（FilterBar 直接接 `listQuery.search` / `listQuery.resetFilters`）+ `useListLoader`（只采用最后一次请求的结果）
- 列：`useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)` 给出 ColumnPicker 和 BusinessTable 共用的完整列
- 新增编辑：`useRecordEditor` + `RecordEditorDrawer`（分组表单、跨字段校验、409 冲突保留草稿、未保存保护都在里面），不要在页面里自己拼抽屉
- 工具栏：`ImportButton`、`ExportButton` + `useExcelExport`、`AuditLogButton`
- 权限矩阵的勾选联动、整组勾选、锁定和搜索是 `permissions/matrix.ts` 里的纯函数，改交互先改它和单测

- 筛选项：`v-bind="filters.bind('字段')"`（`useFilterOptions`），不要自己再维护一份 options
- 筛选一律多选：前端 query 字段默认 `[]`，`http` 按重复参数（`a=1&a=2`）提交；后端参数写
  `list[str] | None = Query(default=None)`，仓储用 `platform_common.filters` 的 `ilike_any`（模糊，同字段「或」）
  或 `in_any`（枚举精确）。只写 `str | None` 会让多选只剩最后一个值生效
- Excel 下载：经 `useExcelExport({ path, filename, filters: () => filtersForExport(listQuery.applied) })`，
  底层是 `downloadFile`。**不要用裸 fetch**——会绕开 401 自动续期和统一中文错误提示
- 导出传 `applied` 而非 `query`：`query` 是用户还没点查询的输入
- 重新部署后，开着的旧页面切路由会因旧分包文件不存在而失败；`router/chunkReload.ts` 在 `router.onError` 里整页刷新到目标地址一次（会话存储防循环），不要删
- 修改共享组件或约定，同步更新 DESIGN.md / UX-CONTRACT.md / UI开发规范.md

### 已确认的产品规则（不要自行推翻）

- 列表默认展示全部字段，列设置支持逐列勾选/显示全部/恢复默认，浏览器记忆选择
- 一列只展示对应字段，不在列里拼接部门、编码等辅助信息
- 上传和下载入口都必须保留在列表工具栏
- 列宽按字段内容制定，不给首列统一大宽度
- 桌面筛选一次展开全部条件，点查询才生效
- 账号入口在侧栏底部（显示名 + 角色），不做右上角芯片，不改登录页

### Git 提交信息

格式固定为 `type(scope): 中文描述`（英文前缀 + 冒号 + 空格 + 中文正文），前缀不能省。
早期仓库有一批纯英文句子式提交（如 `Add policy sources...`），那是更早的写法，不要模仿。

- `type` 用 `feat` / `fix` / `perf` / `refactor` / `style` / `test` / `docs` / `chore`；
  `scope` 是服务名或关注点（`iam`、`export`、`migrations`、`concurrency`、`authz`、`a11y`、`e2e`、`excel`、`gateway`…），
  涉及两三个模块时用逗号分隔（`refactor(iam,audit): …`），没有明确归属时省略 `(scope)`，直接 `type: 中文描述`。
  格式由 `.githooks/commit-msg` 检查
- 中文正文聚焦改动会导致的问题/价值，不要写成文件改动清单，也不要写"更新 xx”“修改 xx”这类空洞描述
- 正文（标题下空一行的部分）可省；要写就先说原来哪里有问题，再说改完好在哪，一两句为宜。
  不要用分号串起一排「做了 A；做了 B；做了 C」的功能罗列——那仍是改动清单，只是换成了功能名
  - 不合格：`权限矩阵勾高档自动带上低档、整组可按列开通；用户查看和编辑合成一个抽屉；状态改成行内开关`
  - 合格：`原来授权要在四档里单选、改人的角色要先点「调整角色」再保存，管理员常找不到入口。改成常见后台的三列勾选和一个抽屉编辑，一次改完。`
  - `fix(migrations): 清掉 model 与数据库的三处漂移，补 make migrate-check`
  - `fix(concurrency): 更新路径补行锁，修掉并发编辑静默丢失；p6-up 补 --build`
  - `feat(export): 单次导出加 10 万行上限，超限明确退回`
  - `refactor: 把 policy/codebook 的重复基础设施下沉到 platform-common`
- 只在用户明确要求时才创建提交；默认新建提交，不 `--amend` 已推送的历史

## 排查提示

- `pg_stat_user_tables.n_live_tup` 是过期统计会显示 0 行，判断数据量用 `count(*)`
- mypy 有缓存假报错，改完文件结构先 `rm -rf .mypy_cache`
- 登录失败按账号 5 次、IP 20 次 / 300 秒限流，账号键是小写后的用户名。探测后清理：
  `docker exec tx-zhongtai-redis-1 redis-cli del 'iam:login:user:<账号>' 'iam:login:ip:<IP>'`
- Element Plus 的原生 checkbox 是 `opacity:0; 0x0` 隐藏元素，e2e 里 `check()` 会一直等可见，
  改点可见标签；hover 才出现的清除图标用 `dispatchEvent('click')`，
  `click({force:true})` 会静默失效（测试变绿但实际没点到）
- e2e 里 `getByLabel('字段名')` 会同时命中列设置弹层的同名复选框，需限定 `.el-drawer` 作用域
- Excel 表头匹配一律走 `header_to_field`：它按**最长前缀**匹配，按列顺序取第一个会把「省份编码」错配成「省份」

## 已知限制

- 本期不执行生产部署；`deploy/gateway/traefik.prod.yml.example` 只是 HTTPS 模板
- `client_ip` 无条件信任 `X-Forwarded-For` 首段，成立前提是服务只能经网关访问
  （Traefik 会清洗客户端自带的该头）。服务端口 8001–8004 不得直接对外暴露，
  也不要在 Traefik 前再加一层不做同样清洗的代理
- 导出不分页，整个结果集读进内存再生成 Excel，靠 `export_max_rows` 兜底
- 筛选项服务端搜索最坏情况线性扫索引（20002 行约 5ms），到 20 万行量级再考虑 pg_trgm
