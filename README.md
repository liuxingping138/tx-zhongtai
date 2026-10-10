# 业务数据运营平台

面向政策、客户、招投标和标准码表的业务数据运营平台，采用 Vue 前端和 Python 微服务后端。当前公共框架已做到 **P6（完整集成验收）**：
账号/会话/RBAC、Outbox Worker、审计查询、隔离验收、备份恢复与 OpenAPI 已交付。
码表管理（政策类型、行业场景、省市区编码）与政策三个子模块（信源、基础标签、解读）已按用户提供的 Excel 接入；
爬虫监测（按网站统计）为只读统计页，数据由同步脚本从外部爬虫库按天聚合。客户、招投标仍仅目录占位。

产品展示名称统一为“业务数据运营平台”；仓库、包名及部署标识继续使用 `tx-zhongtai`，与现有开发环境保持兼容。

文档入口：

- [`CLAUDE.md`](CLAUDE.md) —— 架构要点、硬性开发约定、排查提示，动手前先读
- [UI 视觉规范](DESIGN.md) / [交互契约](UX-CONTRACT.md) —— 新增、修改前端页面必读
- [`docs/README.md`](docs/README.md) —— 其余文档的分类索引：设计与决策（`design/`）、操作手册（`guides/`）、
  OpenAPI、原始 Excel

## 技术栈

- 前端：Vue 3 + TypeScript + Vite + Element Plus + Vue Router + Pinia + Axios + pnpm
- 后端：Python 3.12 + FastAPI + SQLAlchemy 2（异步）+ Alembic + uv
- 数据库/缓存：PostgreSQL 17 + Redis 7
- 网关：Traefik 3（文件 Provider，静态路由配置）
- 容器：Docker + Docker Compose（镜像版本均已锁定，不使用 `latest`）

## 目录结构

```text
tx-zhongtai/
├── frontend/                 # Vue 管理端
├── services/
│   ├── iam-service/          # 身份权限服务；Compose 中 iam-worker 共用此镜像
│   ├── audit-service/        # 审计写入、查询与到期清理
│   ├── policy-service/       # 政策：信源、基础标签、解读、爬虫监测；任务调度（policy-worker 共用此镜像）
│   ├── customer-service/     # 业务占位目录，仅 .gitkeep
│   ├── tender-service/       # 业务占位目录，仅 .gitkeep
│   └── codebook-service/     # 码表：政策类型、行业场景、省市区编码
├── packages/platform-common/ # 跨服务公共包：响应与异常、鉴权依赖、Outbox、审计入队、Excel、筛选等
├── deploy/
│   ├── gateway/               # Traefik 静态/动态配置
│   └── compose/               # docker-compose.yml、Postgres 初始化脚本
├── scripts/                   # 同步到服务器、P6 验收、备份恢复、OpenAPI 导出等脚本
├── docs/                      # 设计决策、操作手册、OpenAPI、原始 Excel（索引见 docs/README.md）
├── Makefile
├── .env.example
└── .gitignore / .dockerignore
```

## 本机环境要求

- Python 3.12（通过 `uv` 管理，不依赖系统 Python 版本）
- Node.js ≥ 20.19（本机验证环境：Node 24 + pnpm 12）
- Docker + Docker Compose（只在临时隔离验收时用；服务器上是独立的 `docker-compose` 程序）
- `uv`（Python 依赖与虚拟环境管理）：<https://docs.astral.sh/uv/>
- `pnpm`：<https://pnpm.io/installation>

## 快速开始

日常在 Mac 上改代码，按 [部署与维护](docs/guides/部署与维护.md) 同步到服务器构建。入口以该文档为准。不要在服务器上 `git pull`，也不要把本机 Compose 当成日常环境。

首次在一台空的隔离环境里初始化时：

```bash
make bootstrap
# 编辑 .env 里的密码
make dev-up
make migrate
make seed
make seed-area-codes
ADMIN_PASSWORD='...' make admin-create
```

本机 Compose 和 P6 只用于临时隔离验收。测完执行 `make p6-down`，不要把隔离栈一直开着。详见 [`CLAUDE.md`](CLAUDE.md)。

## 各服务本地开发（不经 Docker）

```bash
# packages/platform-common 或 services/ 下任一服务目录：
cd services/iam-service
uv python pin 3.12
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8001   # 需要先设置 IAM_DATABASE_URL / IAM_REDIS_URL

# 前端：
cd frontend
pnpm install
pnpm dev   # 默认代理 /api 到 http://localhost:8080（网关）
```

## 常用命令

参见 `make help`。关键命令：`bootstrap`、`dev-up`、`dev-down`、`migrate`、
`check`（Python 静态检查 + 前端类型检查/构建/lint）、`test-unit`、`smoke`。
集成测试和 e2e 在服务器 P6 上跑：`bash scripts/p6-on-server.sh`。

## 开发约定（必须遵守）

新建或修改数据库表时，ORM model **必须**写中文 `comment`：

- 表：`__table_args__ = {"comment": "中文表名"}`（有约束时把该字典放在 `__table_args__` tuple 最后一项）
- 列：每个 `mapped_column(..., comment="中文列名")`，与页面/Excel 表头对齐
- Alembic 建表、加列时同步带上 comment，方便 Navicat 直接看到业务含义
- 业务列表默认展示全部字段，用「列设置」隐藏；显示全部 / 恢复默认都回到全字段
- 账号在侧栏底部（显示名 + 角色）；列表结果区常显横/纵滚动条，默认每页 20 条可滚完全页
- 桌面筛选一次展开，点查询后生效；登录页保持现稿，不要自行改装饰

日常发布走服务器上的 Compose。本机 `make dev-up` 不是日常入口。P6 是隔离验收栈，测完必须 `make p6-down`。

完整说明见 [`CLAUDE.md`](CLAUDE.md) 的「硬性开发约定」。

## 已知限制

- 服务器按地址访问。HTTPS 使用文件 Provider 的 `deploy/gateway/traefik.https.yml`，不要拿 Docker Provider 的旧模板直接替换。
- 最后管理员并发保护已有行锁实现，验收覆盖了禁用唯一管理员返回 403，未做双客户端压测。
- 政策三张表、码表三张表、爬虫监测和任务调度已经接入。客户、招投标仍是占位目录。
