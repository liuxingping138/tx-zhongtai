# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

一体化业务数据平台，最终包含：客户、招投标、政策、场景、爬虫监测、码表管理、AI提问、智库、系统管理。
主要业务数据围绕「客群」串联；爬虫监测、AI提问、智库是独立模块，与客群无直接关联。

当前进度：公共框架已到 P6（账号/会话/RBAC、Outbox、审计、隔离验收、备份恢复、OpenAPI），
政策三张表（信源、基础标签、解读）与码表三张表（政策类型、行业场景、省市区编码）已接入，
爬虫监测已接入（只读统计页，数据来自外部爬虫库采集总表的按天聚合，按网站统计），
爬虫配置统计已接入（按规则表把信源标成已爬，按周按省统计上线栏目数），
AI提问已接入（独立的 ai-service：提示词模板、样本试跑与上线、按 Excel 逐行跑的批量任务，从旧 Django 项目 difyapi/chat_web 迁来），
智库已接入（独立的 thinktank-service：知识库，按文件类型 × 行业类型授权，文件存 MinIO）。
**客户仅有占位目录**，未开发——不要提前暴露无功能入口。招中标已实现独立只读 tender-service（接口、页面、菜单与部署配置），部署说明见 docs/guides/招中标模块.md。
其余文档按 设计决策 / 操作手册 分类，索引见 `docs/README.md`。文档只写与现有代码一致的现状，过时内容直接删除，历史留在 git 里。

## 常用命令

当前运行环境是 `https://36.134.128.137:8443`（8091 HTTP 自动跳转；443 被同机其他站点占用）。在 Mac 上改代码并推送到 GitHub，再用 `scripts/sync-to-server.sh` 同步到服务器构建。不要在服务器 `git pull`，不要在本机 `make dev-up`。步骤见 `docs/guides/部署与维护.md`。
服务器 `.env` 是 `ENVIRONMENT=production`：新增内部密钥类变量（compose 里默认 `dev-only-…`）必须先写进服务器 `.env`，否则服务拒绝启动。

```bash
make check            # 质量门：Python ruff+mypy，前端 type-check+build+lint，范围与密钥扫描，文件行数与忽略注释原因，前端页面不写色值
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

入口是 `https://36.134.128.137:8443`，页面来自服务器上的 frontend 镜像，不是热更新。改了前端源码后按 `docs/guides/部署与维护.md` 同步并重建 `frontend`，只刷新浏览器不会生效。

### 开发部署机 vs 本机 / P6

日常只使用 `36.134.128.137`。本机 Docker 栈已停止。分工：`make check` / `make test-unit` 在 Mac 上跑（不要 Docker）；
集成和 e2e 在服务器上跑 P6：`bash scripts/p6-on-server.sh`（同步到单独的 `/data/tx-zhongtai-p6` → 集成 + e2e → 一定 `p6-down`；`sync-to-server.sh` 同步生产目录时要求工作区已提交）。P6 的模型调用经 `AI_LLM_BASE_URL` 全部发到模拟模型服务 `llm-mock`（`deploy/compose/p6/llm_mock.py`，生产环境配了这个变量会拒绝启动），e2e 能不花钱跑通试发、样本试跑、上线和批量任务，
Mac 不用开 Docker。P6 与业务栈同机但隔离（项目名 `tx-zhongtai-p6`、独立卷与库，网关只绑 `127.0.0.1:8090`），
不要把 Playwright 打到 8091 的业务库。同步一律用 `scripts/sync-to-server.sh`，排除列表只维护那一份。脚本带 `--delete`，
服务器上独有的文件（`.env`、密钥、P6 运行时文件等）全靠排除列表保护，新增服务器独有文件前先加进去。
Navicat 连 `36.134.128.137:5433`。

## 架构

### 服务边界

```
frontend/              Vue 管理端（pnpm）
services/
  iam-service/         账号、会话、RBAC、菜单；Compose 里 iam-worker 共用此镜像
  audit-service/       审计写入、查询、到期清理；Compose 里 audit-worker 共用此镜像跑到期清理
  policy-service/      政策：信源、基础标签、解读、爬虫监测
  codebook-service/    码表：政策类型、行业场景、省市区编码
  ai-service/          AI提问：提示词模板、批量任务；Compose 里 ai-worker 共用此镜像执行批量任务
  customer-service/    占位，仅 .gitkeep
  tender-service/      招中标只读查询、按采集日统计、按需正文（没有本地库）
  thinktank-service/   智库：知识库（预留报告库、方案库）
packages/platform-common/   跨服务公共包（见下）
deploy/gateway/        Traefik 静态+动态配置
deploy/compose/        docker-compose.yml（及 https / p6 叠加文件）、Postgres 初始化与 provision-* 补建脚本
deploy/systemd/       IP 证书续期、到期检查的 systemd 单元
```

每个服务一套独立数据库（`iam_db` / `audit_db` / `policy_db` / `codebook_db` / `ai_db` / `thinktank_db`），
服务间不直连对方的库。tender-service 没有本地库，只读外部 MySQL。服务端口 iam 8001、audit 8002、codebook 8003、
policy 8004、ai 8005、tender 8006、thinktank 8007，都只在容器网络内。

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
| 每日定时任务（队列、leader、重试、页面接口） | `scheduler/` | 三张表的 model、登记的 `Job` |

### 分层

`api/`（路由、Query 参数、权限依赖）→ `application/`（业务编排、审计入队）→
`repositories/`（SQLAlchemy 查询）→ `domain/`（models、fields 列清单）。
`core/` 放配置、数据库等。依赖方向由各服务的 import-linter 契约强制（`make check` 跑 `lint-imports`）。
policy-service 内部再按领域分成 `policy/`、`crawler/`、`scheduler/`、`aitag/`、`crawlconfig/` 几个子包，每个子包内部仍是这四层（`scheduler/` 的查询在公共引擎里，没有 repositories），
跨领域共用的审计入队、鉴权依赖、Outbox 表放 `app/common/`。

### 鉴权链路

业务服务不自己校验 JWT。每个受保护路由挂 `Depends(require_*_permission(RESOURCE, action))`，
它经 `platform_common.authz.AuthzClient` 调 iam-service 的 `/internal/v1/authorize`。
**依赖失败一律返回 503，绝不当作放行**。IAM 判定时资源和动作目录缓存在进程里（`app/application/authz_catalog.py`，60 秒到期重读，
资源或动作编码查不到时立即重读一次；seed 在另一个进程跑，下线、取消发布最多一分钟后生效，要立即生效就重启 iam-service），
用户的角色和单独授权不缓存、每次现查，撤销下一次请求就生效：一次 authorize 两条查询（会话连账号、这个模块的档位）。网关不启用 ForwardAuth，授权全在服务内执行。

路由必须带 `@classified(SecurityClass.*)`，`tests/test_route_security_class.py` 经
`platform_common.route_audit.audit_routes` 强制检查：声明为 `resource_authorized` 的路由必须真的挂了
权限依赖，挂了依赖的也不能错标成别的分级。新写的 `require_*_permission` 工厂要调 `mark_permission_dependency`，
否则体检认不出来。测试里要遍历路由用 `route_audit.iter_api_routes(app)`：`app.routes` 里是未展开的
`include_router` 对象，直接遍历什么都找不到，检查会空跑通过。

### 招中标源表严格只读（用户明确要求）

- `tender-service` 的源表只能 SELECT，禁止对 `bid_analyse` 的四张招中标表以及正文表执行 INSERT / UPDATE / DELETE / DDL，也不建索引、不回传状态。
- `project_status=0` 列表读 `bid_purchaser_info_dis_pro` / `bid_winbid_info_dis_pro`；`1` 列表读对应 `_dis_approval_pro` 交付表。不能用原始表冒充交付表的优化字段。
- 统计只读原始表，按 `collect_date` 分日；状态 1 同时计入信息化标签、基础字段补充，场景工作量暂为 0。两项工序不能相加当作处理数据量。
- 正文按需：项目 ID 长度 <=13 时读 `bid_analyse.qlm_saas_content.infoid` 对应的 `infocontent`；其他读 `crawler2021.zhaobiao2021_prod.uid` 对应 `content`，必须同时限制 `create_time = 原始表.collect_date`（用户已确认 uid）。
- 源库雪花 ID 序列化成字符串。全表精确计数在有界后台线程中执行，前端轮询；列表 LIMIT 多取一条判断下一页，不等待 COUNT。统计缓存只在服务内存，不建源表和平台业务表。

### 智库：独立知识库，文件在对象存储

- `thinktank-service`（库 `thinktank_db`）目前只有知识库（`app/knowledge/`，预留报告库、方案库）。菜单「智库 → 知识库」`/thinktank/knowledge`，
  单个文件的预览工作台 `/thinktank/knowledge/:id`。码表管理下的「智库码表」目录（`menu.codebook.thinktank`）目前没有子菜单
- 两层授权：模块资源 `thinktank.knowledge` 决定能做什么（查看档：列表、详情、预览、收藏；导出档：导出、导出未定义、下载源文件；
  完整档：上传、编辑、导入标签表、删除）；数据范围资源 `thinktank.file_type.*`、`thinktank.industry_type.*` 决定能碰哪些文件
  （IAM `app/domain/thinktank_catalog.py` 和服务 `app/knowledge/domain/scopes.py` 的编码一一对应，改一边要改另一边）。
  范围档位按模块档位封顶（`KnowledgeAccess.from_levels`）；看和下载要文件类型命中、行业任一命中，编辑要文件的全部行业都有完整档。
  越权访问单条记录也记审计
- 文件存储 `app/core/storage.py`：配了 `THINKTANK_MINIO_ENDPOINT` 读写 MinIO（S3v4 签名，沿用原服务器的对象键），没配落本地卷 `thinktank-data`（`/data/thinktank`）；
  存储连不上回 503。上传只收 PDF / Word / Excel / PPT / TXT / CSV / MD，单个上限 `THINKTANK_UPLOAD_MAX_BYTES`（50MB），网关这个前缀另用 `thinktank-limit`
- 预览：PDF 在页面里内嵌显示，TXT / MD / CSV 显示文本；Word / Excel / PPT 由镜像里的 LibreOffice 转成 PDF 内嵌显示（`app/core/office_preview.py`），
  转好的缓存在 `/data/thinktank/preview_cache/`（`app/core/preview_cache.py`；按文件 ID + 对象键 + 大小命名，原子写入）：命中刷新修改时间，总量超过
  `THINKTANK_PREVIEW_CACHE_MAX_BYTES`（2GB）从最久没用的删起，删知识文件时连缓存一起删，业务备份不打包它。同时最多转 2 个，单个 60 秒超时，同一个文件同时只转一次；
  转失败记 `{key}.fail`，10 分钟内再打开直接回摘要、不再占名额重转。拿到名额后才把源文件按块写进临时文件，
  转码前先提交事务交还数据库连接（转码可能排队一分钟，占着连接会拖垮连接池），缓存 PDF 在下发前就打开、按块读出（之后被淘汰也能读完）。
  soffice 单开进程组、只带最少的环境变量（不把数据库口令、存储密钥交给处理上传文档的进程），每次用独立配置关掉宏和外部链接更新，
  超时、请求取消都整组杀掉，compose 里 `init: true` 回收孤儿进程。转换进程仍在服务的网络里，要隔离网络得拆成单独的转换容器。
  没装 LibreOffice 时 Office 仍只显示资料摘要；转换失败、源文件不存在时 `/content` 回摘要 txt，存储连不上回 503。没有源文件的记录下载得到摘要 txt。
  源文件经 `/{id}/content`、`/{id}/download` 流式返回（网关 110 路由，不压缩不缓冲），客户端提前断开也关掉对象存储的流和缓存文件句柄；
  `/content` 带 `Cache-Control: private, no-store`，撤权、删文件后浏览器不留旧内容。前端下载开始、失败用消息提示。
  LibreOffice 让镜像变大，转码时占内存，默认 `THINKTANK_MEM_LIMIT` 是 1536m
- 预览、下载、编辑等写知识库自己的操作记录（`/{id}/logs`），同时经 Outbox 上报审计（投递循环在服务 lifespan 里，没有单独 worker）。
  省份候选值经 codebook `/internal/v1/provinces` 取，取不到用内置列表（密钥 `CODEBOOK_THINKTANK_CALLER_SECRET`，compose 传给两边）
- 历史资料、操作记录和收藏用 `python -m app.cli.seed_knowledge`（`make seed-knowledge`）从 `services/thinktank-service/data` 导入

### 爬虫监测是只读统计，数据靠同步进来

数据源是外部爬虫库（MySQL `crawler2021`，前面挂 ShardingSphere 代理），**页面永远不查它**。
`app/crawler/application/crawler_sync.py`（入口 `python -m app.cli.sync_crawler`，`make crawler-sync`）
只读采集总表 `csys_policy_info_source_all`，按天聚合后写本服务的三张表：
`policy_crawler_site_daily`（网站×采集日，按天整体替换）、`policy_crawler_sites`（页面唯一读取的快照）、
`policy_crawler_sync_runs`（水位与状态）。

- 监测单位是「网站名称 + 省份 + 地市」的**原始值**（用户确认不做别名归一），例外：省份为空的同步时写成「国央企」、「国家」写成「全国」（`stored_province`），
  表格、筛选、图表一致。停更天数按最新入库日期算
- 核心指标是「停更天数」不是「今天有没有出数」：政策网站本来就不是天天更新
- 首次必须回填到爬虫库最早的采集日期；没有成功回填过时日常同步直接报错，不用短窗口算出偏小的总量
- 聚合按 `collect_date`（采集日）分桶，日常按入库时间水位找到受影响日期，再加当天重算，不固定每天全量。
  `--days` / `--since` 是人工指定范围，适用于初始化、口径升级或数据修复
- 同步持有 advisory lock（键见 `app/crawler/repositories/crawler_sites.py`），概览据 `pg_locks` 把停在 running 的批次识别为中断
- ShardingSphere 不支持 `REGEXP` 和多列 `COUNT(DISTINCT)`，写源库 SQL 时用 `LIKE`、单列聚合
- 页面图表只读本地表：采集趋势按日期范围读 `policy_crawler_site_daily`（主键以采集日开头，一年约 26ms），健康结构和省份分布读快照。
 省份分布按「省份」字段的分类画成整行竖柱图，可切换成卡片网格：31 个省级行政区以及全国、国央企都在列（`province_categories`，不含港澳台），没有数据的补 0。
 同一分类的不同写法只在图表里合并（`app/crawler/domain/provinces.py`），网站身份、表格和筛选仍用原始值
- 卡片「较上周」读 `policy_crawler_status_daily`（每日状态分布）。同步重建快照后按快照写当天一行；最近 90 天缺的日期
 由同步用按天统计推算补齐（口径同快照：每个网站最后入库日期），推算一次约 10 秒，所以只在缺数时跑、页面不能现算
- 整表 `GROUP BY` 在代理后跑十分钟都出不来，带 `collect_date` 的单天聚合只要 1.4 秒：全量统计按天循环，别写一条大 SQL

### 爬虫配置统计：规则表 → 信源已爬 → 按周按省统计

- `app/crawlconfig/`（与 policy、crawler 平级）。爬虫同事维护的规则表 `crawler2021.policy_rules_alls` 一行一个栏目，
  `site_code` 对应信源的网站编码（老数据很多没填），同事每周五批量建规则。调度任务 `crawler_config` 每天 18:00 只读编码和创建时间：
  关联上的信源标成已爬，**上线时间 = 这个网站最早那条规则的创建日期**（同步第一次见到某个网站的规则时早晚都对齐，导入时随手填的日期、上线时统一补填的日期都会被纠正；见过之后只往前对齐、不往后挪：最早的规则被删后不能让网站从已汇报的那周消失。见过的最早规则日期记在信源的 `rule_date`，不进 Excel），异常（人工标）不动，从规则表消失也不改回。
  用户每周按信源表透视的就是规则当周新建的网站，按创建日期记才对得上；记同步当天会把信源表里一直没标的老配置算进本周。批次记在 `policy_crawler_config_syncs`
- **工作量按栏目算，信源表按栏目展开**（用户定的）：规则表一个网站常有好几行（一行一个栏目，网站编码相同），信源表原来一个网站一行、标签里列一串栏目。
  从 `POLICY_CRAWLER_CONFIG_EXPAND_FROM`（2026-10-26，用户定的从这周开始）那天起建的规则，同步时每条在信源表里展开成一行（`app/crawlconfig/domain/expand.py`）：标签换成栏目名、链接换成规则链接，
  其余字段照抄这个网站那一行，网站编码共用（所以网站编码不再唯一，`rule_id` 记对应的规则、部分唯一；信源导入允许同一网站（名称、省、市都一样）共用编码，不同网站撞编码才拒收）。这个网站之前没有规则的，原来那行改成第一个栏目；
  之前配过规则的，原来那行留着代表老栏目，新栏目另起一行；信源表已有同名栏目的行就记上规则 ID。之前的规则不展开（历史不好处理，用户定的先不管），没填编码的规则不管。
  展开的行按自己那条规则的创建日期算上线时间（同样只往前对齐、不往后挪），按网站一行的对齐（上一条）只管 `rule_id` 为空的行。
  展开后爬虫同事改了规则的网站编码：展开时按规则 ID 也取一遍已对上的行，那一行留在原编码下照常跟着规则走（用户定的），批次记 `moved` 让人核对；只按编码取会再展开一次、撞规则 ID 唯一索引，整次同步回滚、天天失败。
  要核对某天起的规则会怎样展开，用 `python -m app.cli.preview_source_expand --from <日期> --out <xlsx>`（policy-worker 里跑，只读），会标出同网站已有相同链接的信源
- 统计页「爬虫配置统计」`/policy/crawler-config`（资源 `policy.crawler_config`：查看 / 导出 / 完整档才能「立即同步」）直接对信源表分组统计，不建快照。
  用户每周给领导的是「省份 / 配置网站数量 / 总计」：信源表一行算一个（展开后一行一个栏目），按上线时间落在哪一期透视，省份随数据变化不写死。
  页面从上到下：一句话结论 + 五张卡 → 按周 / 月 / 季度 / 年的配置数量柱图（周是近 12 周、默认上周，因为同事周五建规则、周一汇报；
  月、季度只画今年的 12 个月、四个季度，默认当前这期，没到的期为 0；年从最早有数据的那年起）→ 信源表按省透视的已爬 / 未爬 / 异常（数字链到信源管理）。
  点柱子整页换到那期并弹出这期各省配置的排行（`ConfigProvinceDialog.vue`，可复制成汇报表，点省份开抽屉看网站）。
  `POLICY_CRAWLER_CONFIG_BACKFILL_DATE`（2026-10-22，上线时给历史已爬统一补填的日期）上线、又没有规则印证（`rule_date` 不是这天）的，和已爬没填日期的算期初，不进任何一期；规则正好在这天建的照常算进那一期。
  报告 Excel 第一张就是那张表
- 「立即同步」的接口在 `app/scheduler/api/config_sync.py`：只往调度队列放一次，执行仍在 policy-worker，HTTP 进程不连爬虫库

### AI提问：模型调用走统一客户端，批量在 worker 里跑

- 字节方舟、百度千帆都用 Responses 流式接口，`app/core/llm.py` 一个 httpx 异步客户端归一事件（文本、思考、联网进度、
  用量、错误、response_id）。可选模型、接入点、请求参数和单价存在 `ai_models` 表，在「模型配置」页（`ai.models`）维护，
  保存即生效；请求体和计价规则在 `app/domain/llm_models.py`。模型只停用不删除：模板和历史任务按模型 ID 引用。密钥 `AI_ARK_API_KEY` /
  `AI_BAIDU_API_KEY` 仍在环境变量里，没配的那家在页面上显示为不可用，不会换别家顶替
- 计价按调用时刻：低优档用低优价，配了高峰价的在北京时间工作日高峰时段用高峰价（不认节假日），其余用常规价。
  批量任务每行完成时按当时单价累加费用，不在结束时按总 token 一次算
- 模板里 `@【列名】` 引用 Excel 当前行，`@【上传码表】` 引用码表全文；返回的 `[{字段: 值}]` 按「新增输出字段」解析，
  一个提问解析出多条就展开成多行。规则在 `app/domain/templating.py`，与旧系统一致，改了会影响已有模板的结果
- 模板分政策、客户、招投标三类（`app/domain/categories.py`），类型也是授权单位：IAM 资源 `ai.category.*` 查看档能看这类模板和批量历史，
  完整档才能新建、修改、试发、运行、停止、删除。这一层叠在 `ai.prompts` / `ai.batch_runs` 之上，服务层逐个检查，没授任何类型时列表为空。
  任务发起时把类型快照进 `prompt_category`，模板改类型不影响历史归属
- 模板的码表可选上传文件或系统码表（`app/domain/code_tables.py`：政策类型、行业场景六级、一级行业 + 一级场景）。系统码表每次经
  codebook-service 的 `/internal/v1/code-tables/{name}` 实时取，取不到就报 503，绝不拿空码表去问；密钥 `CODEBOOK_AI_CALLER_SECRET` 两边共用。
  只取名称列、去重（原表按客群重复，8370 行只有 3348 条路径）；六级码表按三级行业分组输出（「一级行业 > 二级行业 > 三级行业：场景；场景」，保留上级场景），约 3.8 万字，原样六列要 10.6 万字
- 模板「上线」由 `ai.releases`（只给管理员，只有管理档：看上线记录跟着模板的查看权限）把提示词、输出字段、模型、码表冻结成 `ai_template_releases` 一版，模板 `release_id` 指向生效版本。
  上线后再改模板只改草稿，页面列出与上线版本不同的项；已上线的模板要先下线才能删，删模板连它的样本试跑记录和产物一起删，试跑没结束的先拦下。定时任务只用上线版本。
  上线请求带管理员核对时看到的草稿 `version`：核对期间草稿又被保存、换了文件就 409，免得上线一份没人核对过的内容
- 主线是业务人员写模板、样本试跑 → 管理员上线 → 定时任务只跑上线版本（`releases.current`）。页面发起的批量任务（`app/application/batch_start.py`）用 `version` 选跑上线版本还是已保存的草稿：人自己传 Excel、当场看结果，不用等上线。只跑了前几行的任务可以「用同一份数据跑全部」（`app/application/batch_run_all.py`，`/batch-runs/{id}/run-all`）：复制那次的数据快照、码表和冻结的提示词 / 输出字段 / 模型新建任务，前面答好的行沿用不重问。单独上传本次 Excel，按要跑那一版引用的列检查（`input-preview` 预检不调模型；`input-template` 按同一份列给出只有表头的数据模板下载），把输入文件、那一版的提示词 / 输出字段 / 模型 / 码表冻结进任务目录和任务行（跑上线版本记 `release_no`，跑草稿记 `draft_saved_at`，以及 `input_name`）：之后改模板、重新上线、删模板都不影响排队中、运行中和已完成的任务
- 样本试跑（`app/application/sample_runs.py`，`/api/v1/ai/prompts/{id}/sample-run`，权限同试发 `ai.prompts:ask`）：草稿 × 模板测试样本前 N 条（最多 50），也是一条 `ai_batch_runs`，`source=sample`，不进批量任务列表（`repositories/batch_runs.TASK_SOURCES`），和正式任务互不阻挡；按先后叫「第 N 次」，`view` 默认看最近一次、和前一次逐行对比（`run_compare`：按发起时复制进任务目录的样本内容判断是不是同一份，同一份才按行号对上，标 fixed / broke / changed；changed 只比标签类短值，超过 `PROSE_CHARS` 字的说明文字措辞变了不算，前端 `sampleView.isProse` 同一规则），`run_id` / `compare_id` 能换着看最近 20 次；`/sample-run/{run_id}/retry` 只重问失败的行，用的是那次冻结的提示词；模板列表带最近一次试跑（`sample`，`current` 表示跑的就是现在的草稿）。逐行结果预览 `run_rows.preview` 样本试跑和批量详情共用，任务可能几十万行，只读要列的那几行：输入读逐行副本 `input.jsonl`（第一次打开时由快照生成，快照大小或修改时间变了就重建），原始返回不留提问原文；每写一行原始返回同步追加一条结果记录 `temp.outcomes.jsonl`（`batch_output.append_raw`，不带提问，几十万行也只有几 MB，记着这一行在原始返回里的字节位置 `at`，同一任务的几路并发写原始返回用 `Job.write_lock` 排队，位置才准）：前 N 行按记录定下最终结果、成功行按位置直接取，「只看失败」也读它。记录（或位置）功能上线前开始的任务没有它，才顺序读原始返回。跑完的结果 Excel 在模板页下载（`/sample-run/{run_id}/files/{kind}`），挂模板的导出档 `ai.prompts:export` 而不是批量任务的，只给这个模板自己 `source=sample` 的任务
- `ai-worker` 持 Postgres 全局锁，用 `SKIP LOCKED` 认领排队任务，最多同时跑 `AI_BATCH_MAX_RUNNING` 个，其中留一个给样本试跑和定时打标（页面发起的批量任务最多占其余几个，`batch_queue.bulk_limit`），每个任务
  `AI_BATCH_CONCURRENCY` 路并发。leader 每 10 秒写 `ai_worker_heartbeat`，一分钟没写就算不在线：批量任务列表和样本试跑接口带 `worker_online`，页面据此提示排队的任务不会开始。提示词轮到哪行才拼哪行、成功行写完 CSV 就不再留提问原文、结果 Excel 用 `xlsx_writer` 流式写：10 万行乘上码表全文一次拼好要几个 G，worker 会被 OOM 杀掉。每行完成立即追加 `temp.csv`；进程被停时把已跑部分收尾成「中断」并生成结果。
  运行中超过 `AI_BATCH_STALE_SECONDS` 没心跳的任务，列表和进度接口会把它纠正为「中断」
- 自动补救（`app/application/batch_execute.py`）分两层。当场（`ask_row`）：限流、5xx、超时、断连、空返回按 `RETRY_DELAYS` 退避重发，
 400、密钥错误、写到上限被截停不重发。按轮：批量任务和定时任务一次执行最多三轮（`ROUNDS`），一轮跑完隔 `ROUND_WAITS`（1 分钟、5 分钟）
 只重问网络失败和格式不对（解析不出输出字段，error 列以 `返回格式不对` 开头，原始返回 CSV 不加列）的行，哪轮全成功就提前结束，三轮后仍失败的留着失败原因；
 格式不对不当场再问（每问一次都带码表全文、按全价收钱），交给下一轮。样本试跑不分轮，格式不对当场再问一次，结果原样给人看提示词哪里要改。
 任务上的 `retry_round` / `round_rows` / `round_starts_at` 给页面显示「第 2 轮：重问 N 条」；轮与轮之间心跳照写，否则会被纠正成「中断」。
 「重跑失败」把已结束的任务重新排队（轮次从 1 算起）：worker 读回原始返回，已成功的行沿用，只问失败和没跑到的行，token 和费用累加。要问几条用执行进程写进度时算好的 `open_count`（第 2 轮途中被杀时，按已处理、失败两个数推会把正在重问的行算两次）。
 旧系统迁来的任务没有 Excel 快照，不能重跑；定时任务的批次也不能重跑（政策服务已取走结果，重跑只会再花钱，要补的政策在基础标签里「重新打标」）。
 原始返回 CSV 的「提问」列是整段提示词，政策全文加码表能到十几万字，`batch_output` 放开了 csv 单格上限，别再按默认值读
- 试发（`/api/v1/ai/stream/ask`）带 `row` 选测试样本第几条（`app/application/test_rows.py`，`/prompts/{id}/test-rows` 给前 100 行每格开头 200 字供页面选行和预览），带 `output_fields` 时答完多推一块 `{"parsed": [...] | null}`，按和批量任务同一套 `parse_fields` 解析，页面据此说这一行能不能解析、和样本试跑比修好了没有
- 流式接口都在 `/api/v1/ai/stream/*`：网关对这个前缀不挂压缩和请求缓冲（buffering 会把整段回答攒满才下发），
  新加流式接口必须放在这个前缀下，`test_stream_routes_live_under_the_unbuffered_prefix` 会拦
- 模板附件和批量产物在 `ai-data` 卷（`/data/ai`），不在库里；业务备份脚本会一起打包
- 旧打表系统的模板和批量历史用 `python -m app.cli.import_legacy <导出目录> [--update] [--dry-run]` 导入，保留原 ID，可重复跑；
  `--update` 用旧库最新内容覆盖：模板只覆盖导入后没在新系统里保存过的，任务除排队中、运行中的都覆盖。导出目录结构见 `app/application/legacy_import.py`
- 试发的内容不进审计，只记谁对哪个模板、哪个任务做了什么。多轮对话已删（资源 `ai.chat` 在 `RETIRED_RESOURCE_CODES`）
- 费用账单（`ai.billing`，`/api/v1/ai/billing`）：批量任务、定时任务和样本试跑的费用在 `ai_batch_runs` 上（用途按 `source` 分成「批量任务」「样本试跑」，定时任务的用途是发起方名字，如「政策AI打标·类型判断」），
  试发答完时在 `ai_call_usages` 记一行（不记内容，`app/application/billing.py`；`kind = chat` 的是已删的多轮对话留下的，账单里照样算）。新增调模型的入口要么走批量任务，要么也记进 `ai_call_usages`，否则账单漏钱。
  删除批量任务、删模板连带的样本试跑只打 `deleted_at`（用户定的：删了的钱照样算）：除账单外的查询都要带 `repositories.batch_runs.LIVE`
  账单每行带三级归属供页面联动筛选：业务分类 `scene`（`source=pipeline` 是「日常调度」，其余都是「测试」）→ 一级业务板块 `category`（模板类型；试发记在 `ai_call_usages.prompt_category`，没保存的新模板取编辑页选的类型）→ 二级业务板块 `purpose`。
  AI 的审计事件经 `audit_emit.enqueue_event(category=…)` / `audit_template` 带模板类型，审计服务入库时据此算业务线；新加模板、任务相关的事件要带上

### 系统管理：给人分配角色即授权，个别人可再单独授权

菜单六项：用户管理、角色与权限（角色和权限分配在同一页）、在线用户、登录日志、操作日志、任务调度。在线用户（`/system/sessions`，读会话表，可按设备下线）的权限跟着 `system.users`，登录日志（操作日志里 `auth` 模块的登录 / 退出事件）跟着 `system.audit`，都不另设资源。
在线用户列出全部有效登录（没撤销、没过期），最近 `IAM_ONLINE_WINDOW_SECONDS`（30 分钟）内有操作的标「在线」。「最近活跃」由带令牌的请求（含业务服务的 authorize）经 `auth_service.note_activity` 更新：
每台设备至多 60 秒写一次，写在独立短事务里、行被锁就跳过（`FOR UPDATE SKIP LOCKED`），别改成在请求事务里改这一行，长事务会让同一个人的其他请求等锁。
这类「请求还占着一条连接时另开的短事务」（最近活跃、登录失败和越权被拒的留痕）一律用 `database.SideSessionLocal` 的小连接池（拿不到半秒就放弃）：和请求共用一个池的话，并发十几个就整池互等到超时，全平台鉴权 503。
自己正在用的那台标 `current`，接口拒绝下线（要退出用「退出登录」）。
登录失败能对上账号的（没删的用户名）也记 `actor_id` 和显示名，对不上的只记输入的用户名；锁定原因分 `locked_account` / `locked_ip`，IP 限制由超级管理员在登录日志页解除（`/system/login-limits/unlock-ip`）。
用户列表、用户详情、在线用户每行带 `can_manage`（`user_admin.manageable_ids`，规则同 `assert_can_manage_target`：不是超级管理员的管不了超级管理员），前端据此不给按钮，后端照旧拒绝。
角色之外可以单独给某个人授权（`iam_user_grants`，用户详情里「单独授权」，PUT `/users/{id}/grants` 挂 `system.permissions:grant`）：
实际权限 = 所有启用角色加单独授权，按模块取最高一档，口径在 `repositories/resources.py`：`list_effective_levels`（菜单、「我的权限」）和 `effective_level`（authorize 只查一个模块）是同一规则，改一处要改另一处；其他服务经 authorize 自动生效。「权限分配」永远不单独给人；删除用户时一起清掉。
用户列表的「最近登录」读 `iam_users.last_login_at` / `last_login_ip`（登录成功时写），不靠会话表倒推：会话过期会被清理。密码连续输错被锁的账号在列表里显示「已锁定」，管理员可直接解锁（删 Redis 里账号维度的计数，IP 维度不动）。给人分配角色的所有入口
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
再由 worker 投递到 audit-service。失败按指数退避重试（最长 15 分钟一次，默认 100 次，约一天），超上限置 dead；只有内容本身不合格（400/413/422）立即 dead，401/403（换密钥、容器重建有先后）照常重试。可用 `make outbox-replay` 重放（服务器上 `make SERVER=1 outbox-replay`）
（覆盖 iam/policy/codebook/ai/thinktank，`OUTBOX_SERVICES=policy-service` 只跑一个）。
tender-service 没有库也没有 Outbox：导出、查看正文同步上报审计，上报失败回 503（见 `docs/guides/招中标模块.md`）。

认领时置 delivering 并写 `lease_until`，回写只在租约没被别人重新认领时生效。进程在投递途中重启，
租约到期后会被重新认领，不会永远卡在 delivering。IAM 默认租约 30 秒（`IAM_WORKER_LEASE_SECONDS`）；
policy / codebook / ai / thinktank 走公共 Outbox（投递循环在各服务 lifespan 里），默认 5 分钟。审计服务按 `event_id` 去重，重投不重复入库。

审计库（库、public schema、全部表）归超级用户所有，`audit_events` 对应用账号只有 SELECT/INSERT：属主是应用账号时
「收回删改权」防不住被攻破的应用账号（属主能把权限授回给自己、直接删表删库）。所以审计迁移用超级用户跑（生产环境超级用户口令为空或还是示例值时 `migrate_audit` 拒绝执行），
跑完由 `deploy/compose/scripts/secure-audit-db.sh` 收紧权限，两步都在 `make migrate-audit`（服务器上 `make SERVER=1 migrate-audit`）里，
新表靠默认权限给应用账号增删改查。到期清理（`AUDIT_RETENTION_DAYS`，180 天）是审计服务自己的定时任务 `audit_cleanup`（每天 04:30），
在单独的 `audit-worker` 容器里用清理账号分批删：清理账号的连接串只给它，对外提供接口的 audit-service 拿不到。
新的审计写入逻辑不能依赖 UPDATE/DELETE。操作日志的「类型」存在 `audit_events.business_line`（policy / customer / tender），入库时由审计服务按模块编码和 `changes.category` 算好（`app/domain/business_lines.py`），列表可按它和「业务模块」（`module_root`，模块编码第一段）筛；2026-11-11 前的 AI 事件用一次性脚本 `deploy/compose/scripts/backfill-audit-business-line.sh`（超级用户）按目标ID 从 ai 库补过，只补分类标签、不动事件内容。已投递的出站记录各服务自己每小时清一次，保留 30 天（`audit_emit.OUTBOX_RETENTION`、IAM 的 `outbox_delivery.OUTBOX_RETENTION`）。

操作日志的筛选项（操作人、模块、动作）不整表 DISTINCT，而是用递归查询沿索引一个个跳到下一个不同的值
（`repositories/events.distinct_values_stmt`），步数只和不同值的个数有关；新加筛选项字段要给它建以它打头的索引，
否则每一步都是整表扫描（`test_option_columns_are_indexed` 会拦）。列表这一页没取满时总数直接算出来，取满了才 count。

### 任务调度

平台所有定时任务都在系统管理的任务调度页 `/system/scheduler`。引擎在 `platform_common.scheduler`：各服务在自己的库里存计划和执行记录，
登记自己的 `Job`，worker 持本服务的 PostgreSQL 全局会话锁执行，按 `Job.lane` 分通道：每条通道同时一条、通道之间并行，几个小时的 AI 打标走长通道，不堵爬虫同步；接口由 `build_scheduler_router` 生成，都校验资源 `system.scheduler`
（READ 查看，FULL 设置计划和手动执行）。前端 `src/api/scheduler.ts` 的 `SCHEDULER_SERVICES` 把各服务的任务汇总成一张表，
新服务接入照 `docs/guides/任务调度.md`「接入一个新服务的定时任务」，不要再自己写定时循环或宿主机 cron。

现有任务：iam-service 的清理失效会话（`iam_session_cleanup`，默认 03:30，在 iam-worker 里与 Outbox 投递同进程）；
audit-service 的清理到期操作日志（`audit_cleanup`，默认 04:30，在 audit-worker 里）；
policy-service 的三类（`policy-worker`，`app/scheduler/application/jobs.py` 登记）：爬虫监测增量同步
（任务编码 `crawler`，默认 10:10，时刻可在页面改）、爬虫配置同步（`crawler_config`，默认 18:00）和政策 AI 打标的五个任务（`policy_ai_type` / `policy_ai_interpret` / `policy_ai_opportunity` / `policy_ai_scenario` / `policy_ai_enrich`，
上线时默认停用、页面手动执行）。
执行、结果摘要、中断收尾、超时都写在各自的 `Job` 上，引擎不认识具体业务。重启错过多天只合并一次。
初始化无成功水位时拒绝自动同步，需要先完成历史回填，不能自动退回短窗口。
worker 必须连接可出站的 gateway 网络以访问外部 MySQL，只有 internal data 网络会无法连接源库。
详细规则和验收见 `docs/guides/任务调度.md`。

### 政策 AI 打标：读源库 → 用上线模板跑 → 写政策表

- `app/aitag/`（与 policy、crawler、scheduler 平级）。源数据是同一 MySQL 实例的 `bid_analyse.csys_policy_info` + `csys_policy_info_content`
  （正文，按 `content_id` 一对一），只读不回写。正文其实是整页网页源码，发给模型前由 `rules.page_text` 提取成看得见的文字（只剩约 6%），并去掉导航、页头页脚（语义标签，或 class / id 拆开后含 header、footer、nav、menu、crumb 等词的块，否定词开头的如 `no-breadNav-padd` 不算；去完把原文最长一段弄丢了、或导航块到结尾没闭合，就退回整页文字。400 页实测再少约四分之一、没丢正文句子），
  不提取既浪费十几倍的输入费用，又和业务人员用 Excel 测试时的输入口径不一致。按采集日逐天读、日内按 `content_id` 分页，只读到前天整天（源政策 ID 是哈希、不按入库先后排，读过一天之后再入库的会漏；源库每个采集日的数据第二天才入库完，实测最晚到第二天晚上），类型判断任务可设采集省份（`policy_ai_tasks.provinces`，按源库 `prov_name` 原样 `IN`，候选取省市区编码表的省份，空为不限；改省份不动读取进度），读到的政策已打过类型标的跳过（和已有基础标签内容相同、没写进去的记在 `policy_ai_skipped_sources`，也算打过）（读取进度往回调重扫补漏时不重复花钱）；批次进行中有人改了起始日期，收尾不把它改回去；每批开始前按模板现在的上线版本复核任务契约（`tagging.check_template_now`）；读取进度（采集日 + 正文ID）存在
  `policy_ai_tasks` 的类型判断那一行，一批写完才前移，费用到上限没跑到的行下批重读
- 类型判断、政策解读、市场机会、新增场景找相似、新增场景补描述是五个独立的调度任务（`app/aitag/domain/tasks.py`），各有模板、每批条数、正文长度和每日上限（`policy_ai_tasks` 一任务一行），
  一次执行只跑一个任务的一批。后两个按待办取数据，前一个没跑后一个就没有待办，彼此不串联
- 每批调 ai-service 的 `/internal/v1/pipeline-runs`：用模板**上线版本**、低优档、以这个任务当日剩余额度为费用上限跑，worker 到上限自停；
  一批最多发 `pipeline.PIPELINE_ROWS_BUDGET`（56MB，ai-service 这个前缀收 64MB），超出的行记成未执行、下一批接着做；内部调用的 JSON 按 UTF-8 发（转义的话一个汉字 6 字节）；
  政策服务轮询到结束再取解析结果（ai-service 那边已跑过三轮）。轮询偶尔问不到不放弃（连续 `POLL_MISSES` 次才算失败）；
  调度超时、进程中断、一直问不到都先停掉 ai-service 那边的任务（建任务的请求还在路上、任务还不存在时，ai-service 收到停止或查询会插一行已取消的占位，迟到的建任务撞主键按幂等返回它、不再执行；建任务读完上线版本就提交，不带着模板行锁和事务写快照），批次记失败时把已花的钱补进步骤费用列（`tagging._close`），重试时当日额度才算得到。
  下一批发起时带上复用期限内最近一次失败的 AI 任务（`pipeline._reusable` → `reuse_run_id`，不要求是最近一批）：同一上线版本、同一模型、同一码表、行数据一模一样且已答好的行，
  ai-service 直接抄进新任务（`pipeline_runs._reuse_answers`），不再花钱重问
- 类型判断结果用系统政策类型码表核对（缺「类」字的旧写法补上能对上就算），写进基础标签：按 `source_content_id` 更新，
  人工在打标后改过的行不覆盖；失败和没对上码表的写进备注。含「信息化建设类」的标「是否解读 = 是」
- 重新打标（`app/aitag/application/retag.py`，`POST /api/v1/policy/ai-tagging/retag`）：基础标签勾选后放回某个任务的待办，不当场调模型。
  重新判断类型记 `type_retag_at`（已在队里的不重记，入队时去掉上次的类型失败说明；排着队的不算「类型判断失败」），类型判断下一批先按源政策 ID 重打这些、强制覆盖（人填的穿透三列和人写的备注保留，只换 AI 写的几段；重打后内容和另一条基础标签相同的不写、出队并在备注注明（带本条源政策ID，几条副本彼此不撞哈希），否则撞内容哈希整批回滚）、不动读取进度；类型和「是否解读」都没变就不重做解读（用户定的），改成非信息化的删掉没人核对过的 AI 解读行；重新解读 / 补机会清掉完成时间。失败说明前缀在 `policy.domain.fields.AI_NOTE_*`，列表「打标状态」按它筛；表格里的「打标状态」列由 `policy.domain.fields.ai_status` 按同一套条件算，改筛选条件要一起改。源库标题是 `document.write(...)` 脚本残留的，`rules.policy_title` 取出其中文字写进基础标签和提示词，备注注明
- 模板和任务的约定在 `app/aitag/domain/contract.py`：每个任务给模板哪些列、要哪些输出字段，`check_template` 分必须改（errors）和提醒（warnings）。
  任务设置换模板时后端按它拦下；提示词模板编辑页按草稿实时提示（前端 `modules/ai/prompts/taskFit.ts` 同一套规则，两边改要一起改）
- 「从数据库取测试数据」（`app/aitag/application/samples.py`，`GET /api/v1/policy/ai-tagging/samples`，权限 `policy.base_tags:list`）：按任务生成和正式打标一样的行，
  前端再存成模板测试 Excel（ai-service `POST /api/v1/ai/prompts/{id}/test-data`）。接口只能挂本服务资源，所以不用 AI 模块的模板权限
- 打标会花钱，单独授权：改任务设置（模板、条数、每日费用上限）挂 `policy.ai_tagging:update`；打标调度任务的 `Job.cost_resource` 都是它，
  任务调度改计划、立即执行除了 `system.scheduler` 还要它的完整档（`build_scheduler_router` 的 `check_permission`）。新增花钱的调度任务照此设 `cost_resource`
- 政策正文不进平台库：基础标签、解读详情里的「政策正文」由 `policy/application/policy_content.py`（`GET /base-tags/{id}/content`、`/interpretations/{id}/content`，各挂自己的 `read`）按 `source_content_id` 现读源库，
  用 `rules.clean_content` 提取成和打标同一口径的文字；源库单条实测 0.2 秒。读源库用 `source.read_page`：一次连接、连接 5 秒读 20 秒超时、不重试，
  不沿用同步任务的 30 秒连接、20 分钟读取和重试（人在页面上等，卡住的请求还占着线程）。没有源政策 ID 的行回 404「没有正文」，源库连不上回 503
- 解读、市场机会按待办做：基础标签「是否解读 = 是」且 `interpreted_at` 为空的政策做解读，一条展开成多行写解读表（「政策概览」写进「政策要文」，
  非新增场景到码表查编码，名称对不上的写备注）；解读过、`opportunity_at` 为空的做市场机会，按一级行业 + 一级场景回填。
  费用到上限没轮到的不记时间，下批接着做；AI 行只要人工验证过或改过就不再覆盖（`app/aitag/application/interpreting.py`）。
  待办（以及还没和码表比对的解读行）都有部分索引，查询条件写在 `policy.domain.models` 的 `awaiting_interpretation` 等函数里、和索引条件一字不差，
  常量用 `literal_execute` 直接写进 SQL：写成绑定参数的话通用执行计划用不上部分索引，几百万行时又是整表扫描（`tests/test_backlog_indexes.py` 会拦）
- 新增场景不再逐行同步，按场景审核（菜单「新增场景审核」`/policy/scenario-candidates`，资源 `policy.scenario_candidates`：查看档看，完整档 `decide` 采纳 / 合并 / 驳回 / 改判，采纳、合并写码表还要 `codebook.scenarios:update`）。
  解读行和码表比对、归成候选、套用决定都在 `app/policy/application/scenario_engine.py`：AI 每批写完（`interpreting._classify_new_rows` 扫「待归集」部分索引）、手工编辑（名称或编码变了）、导入后都走它，
  码表服务连不上时行留着 `scenario_state = ''`，`python -m app.cli.classify_scenarios`（policy-worker 里跑）补。比对用 codebook `/internal/v1/scenarios/lookup` 返回的 `kind` / `new_level`（`scenario_codes.classify`）：
  码表已有的回填编码，AI 说新增的改成「否」并在备注注明；三级行业不在码表的标「行业不在码表」；新场景按「第一个新出现的那一级」的场景路径归成候选（不分行业，和各级场景号全局唯一一致），
  各级场景都有、只是没挂在这个行业下的是「新关联」候选（连行业一起算）。「是否新增场景」「新增场景级别」由比对结果覆盖 AI 的写法。
  候选表 `policy_scenario_candidates` 的 `key` 就是规则：决定过的候选，以后 AI 再写同样的说法直接按决定处理（合并的说法等于别名）。
  系统归集、套用决定只加版本号，不动 `updated_at` / 操作人：AI 按「更新时间 ≤ 打标时间」认没人改过的行，动了会让重新解读、补市场机会跳过它；只有来源政策里逐行「改场景」（`POST /interpretations/{id}/scenario`）算人工编辑。
  采纳、合并经 codebook `/internal/v1/scenarios/sync` 写码表（按编码规则 `app/domain/scenario_codes.py`：各级号全局最大 + 1，已有上级沿用，行业只查不建；合并到没挂在这个行业下的场景只新建关联行），合并前先确认目标码表里有；
  回填编码后关联主键换成编码形式，撞上同一政策同场景、同机会类型的另一行时这行标「重复」、留原主键，不删（用户定的）。码表里新建的行标「是否新增场景 = 是」、记「来源政策」（不进 Excel 导入列和内容哈希）。
  采纳进码表的新场景只有名称：码表行带「补充状态」`enrich_status`（新建为待补充，原有的为空，不进 Excel 导入和内容哈希）。打标任务「新增场景补描述」（`app/aitag/application/scenario_describing.py`，`policy_ai_enrich`，默认停用）经 codebook `/internal/v1/scenarios/enrich-backlog` 按场景路径取待补充的（带上级描述、同级范文），用上线模板写 90 字 / 130 字 / PEST / 本级描述，经 `/scenarios/enrich` 写回标待确认（没写出来的也标待确认、描述空着，免得天天重问）；业务人员在新增场景审核的「补充待确认」页签核对、改好后确认（codebook `POST /scenarios/enrich-confirm`，要码表管理档），各行业、各客群的行一起写。
  两个待审场景是同一个时并成一个（`scenario_merging.absorb`）：被并入的候选记 `merged_into`，行改成目标的说法搬过去，归集时顺着 `merged_into` 找到最后归到的场景（`scenario_rows.final_candidate`）。合并时可让原场景改用新说法：codebook `/internal/v1/scenarios/rename`（同一上级下已有同名就 409，`dry_run` 只数行数）改码表各行，再整批改解读行名称、挂在它下面的待审候选的路径和 key。
  审核在列表行上做（没有单个场景的页面），展开一行时「同一位置已有」「码表里像它的」现取 codebook `/internal/v1/scenarios/context`（字符二元组相似度，`app/domain/scenario_similarity.py`），名称相似只看字面，意思近、说法不同的找不出来，所以另有打标任务「新增场景找相似」（`app/aitag/application/scenario_similar.py`，`policy_ai_scenario`，默认停用）：待审、还没看过的场景一个只问一次，把码表里同一个一级行业下的全部场景（context 的 `with_paths`）交给上线模板，要它输出「判断」「最像的已有场景」「理由」，结论归成同一个场景 / 新场景 / 归到已有场景下，AI 说的场景码表里对得上才记 `ai_target`（点这一行的「合并」时预选成目标），系统建议先看 AI 的判断。别的一级行业下的已有场景字面再像也最多算「中」（不据此建议合并，「智慧机场工程建设管理」≠ 工会的「工程建设管理」）；新候选建好时缓存最像的一个给列表用，口径改了用 `classify_scenarios --resimilar` 重算待审的；选场景用 codebook `GET /scenarios/paths?q=`
- 费用：批次记 `task` 和各步费用列（`type_cost` 等），任务列表的「今日已花」按费用列（`tasks.TASK_COST`）算，拆分前三步合跑的旧批次也能各归各的任务；
  `/tasks` 的 `current` 给出每个任务正在跑的那批和 AI 已答条数。按天账单不在政策服务里做，统一看 AI提问 → 费用账单
- 内部调用密钥：`AI_POLICY_CALLER_SECRET`（政策→AI）、`CODEBOOK_POLICY_CALLER_SECRET`（政策→码表），compose 把同一个值传给两边

### 网关

Traefik 文件 Provider（非 Docker Provider）。路由优先级：
具体业务前缀（100）> 未接入业务的 `/api/v1` 兜底 404（50）> 前端 SPA 兜底（1）。
`/health/*`、`/internal/*` 未声明路由，不对外暴露。优先级 110 的三条路由不挂 `compress` 和请求缓冲：`/api/v1/ai/stream`（流式回答）、
AI 批量产物下载、智库文件的 `content` / `download`（大文件流式下发）；其余路由都挂 `compress`，xlsx/zip/图片在 `excludedContentTypes` 里排除。
请求体上限 `request-limit` 是 20MB+256KB，`/api/v1/thinktank` 用 `thinktank-limit`（50MB+256KB）。

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
- 导入、新建、编辑前用 `platform_common.columns.string_lengths(Model)` + `overlong_reasons` 按模型列宽校验，超长的写进校验说明 / 422；
  不校验的话撞到库里是 DataError，用户只看到「服务器内部错误」。信源的爬虫状态只收 `CRAWLER_STATUS_CHOICES`，别的写法会让配置统计分省合计对不上
- 导入查重按文件里的键分片查库（`existing_hashes` / `existing_relation_keys`），不整表拉哈希；信源导入分配网站编码用 `SiteCodeAllocator`，已有编码只扫一遍
- `build_workbook` 不经 openpyxl，由 `platform_common/xlsx_writer.py` 直接写只含文本的 xlsx（内联字符串，不会成公式）：
  2 万行信源 3.3 秒降到 0.5 秒。业务导出走它，不要为加样式改回逐格建对象
- 自己拼 Excel 时逐行用 `platform_common.excel.append_text_row`，别直接 `sheet.append`：openpyxl 会把 `=` 开头的
  字符串存成公式，导出的网站名、导入内容里带 `=HYPERLINK(...)` 就成了打开即执行的活公式

### 列表与导出共用一份筛选定义

仓储里的 `FILTER_COLUMNS` + `_conditions` 同时供 `list_items` / `count_filtered` / `list_filtered` 使用，
从结构上杜绝列表和导出条件走偏。未知字段直接 `KeyError`（API 层转 422），
不允许静默忽略——否则导出会悄悄变成导全表。
`tests/test_export_filter_parity.py` 会强制三者一致。

### 前端规范

改页面前读 `DESIGN.md`（界面规则，以及用户确认过、不要自行推翻的页面决定）和 `docs/guides/UI开发规范.md`（公共组件、接入步骤、验收）。
新增业务列表页照 `modules/policy/base-tags/BaseTagList.vue` 组装，不要在页面里自己拼抽屉、筛选项或下载。

前后端要一起守的约定：

- 几百万行的名称、标题字段（政策名称、政策原文名称）不出候选值，用 `FilterKeyword` 输入关键词，列上建 pg_trgm GIN 索引；政策类型的候选值取政策类型码表（`internal_clients.policy_type_names`，包含匹配，pg_trgm 索引），政策解读的一级行业、一级场景取行业场景码表（`scenario_l1_names`，精确匹配走 B 树索引），都不在政策表上去重
- 筛选一律多选：前端 query 字段默认 `[]`，`http` 按重复参数（`a=1&a=2`）提交；后端参数写
  `list[str] | None = Query(default=None)`，仓储用 `platform_common.filters` 的 `ilike_any`（模糊，同字段「或」）
  或 `in_any`（枚举精确）。只写 `str | None` 会让多选只剩最后一个值生效
- Excel 下载经 `useExcelExport`（底层 `downloadFile`），**不要用裸 fetch**——会绕开 401 自动续期和统一中文错误提示；
  导出传 `applied` 而非 `query`：`query` 是用户还没点查询的输入
- 改了界面规则同步 DESIGN.md，改了公共组件用法同步 UI开发规范.md

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
- 登录失败按账号 5 次、IP 20 次 / 300 秒限流，账号键是小写后的用户名；改密码时原密码输错也按这个计数（`api/auth.change_password`）。账号被锁在用户管理里点「解锁」；
  IP 维度的计数页面不管，探测后清理：`docker exec tx-zhongtai-redis-1 redis-cli del 'iam:login:ip:<IP>'`
- Element Plus 的原生 checkbox 是 `opacity:0; 0x0` 隐藏元素，e2e 里 `check()` 会一直等可见，
  改点可见标签；hover 才出现的清除图标用 `dispatchEvent('click')`，
  `click({force:true})` 会静默失效（测试变绿但实际没点到）
- e2e 里 `getByLabel('字段名')` 会同时命中列设置弹层的同名复选框，需限定 `.el-drawer` 作用域
- Excel 表头匹配一律走 `header_to_field`：它按**最长前缀**匹配，按列顺序取第一个会把「省份编码」错配成「省份」

## 已知限制

- 本期不执行生产部署；`deploy/gateway/traefik.prod.yml.example` 只是 HTTPS 模板
- `client_ip` 无条件信任 `X-Forwarded-For` 首段，成立前提是服务只能经网关访问
  （Traefik 会清洗客户端自带的该头）。服务端口 8001–8007 不得直接对外暴露，
  也不要在 Traefik 前再加一层不做同样清洗的代理
- 导出不分页，整个结果集读进内存再生成 Excel，靠 `export_max_rows` 兜底
- 筛选项服务端搜索最坏情况线性扫索引（20002 行约 5ms），到 20 万行量级再考虑 pg_trgm
