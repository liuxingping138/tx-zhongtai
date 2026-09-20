# 业务数据运营平台

面向政策、客户、招投标和标准码表的业务数据运营平台，采用 Vue 前端和 Python 微服务后端。当前公共框架已做到 **P6（完整集成验收）**：
账号/会话/RBAC、Outbox Worker、审计查询、隔离验收、备份恢复与 OpenAPI 已交付。
码表管理（政策类型、行业场景）与政策三个子模块（信源、基础标签、解读）已按用户提供的 Excel 接入。客户、招投标仍仅目录占位。

产品展示名称统一为“业务数据运营平台”；仓库、包名及部署标识继续使用 `tx-zhongtai`，与现有开发环境保持兼容。

详见：
- [`docs/业务数据运营平台公共基础框架设计.md`](docs/业务数据运营平台公共基础框架设计.md) —— 架构设计
- [`docs/Cursor公共框架开发计划.md`](docs/Cursor公共框架开发计划.md) —— 分阶段开发计划
- [`docs/开发进度.md`](docs/开发进度.md) —— 当前实际进度与验证记录
- [`docs/实现决策.md`](docs/实现决策.md) —— 端口、数据库、技术选型等实施细节
- [`docs/业务表主键与导入导出分析.md`](docs/业务表主键与导入导出分析.md) —— 六张业务表的现状、限制与待业务确认事项；暂维持现有规则
- [`docs/开发约定.md`](docs/开发约定.md) —— 必须遵守的开发约定（ORM 中文 comment、开发栈/P6）
- [`docs/配置说明.md`](docs/配置说明.md) / [`docs/部署与维护.md`](docs/部署与维护.md)
- [`docs/openapi/`](docs/openapi/) —— 从运行中服务导出的 OpenAPI

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
│   ├── policy-service/       # 政策：信源、基础标签、解读
│   ├── customer-service/     # 业务占位目录，仅 .gitkeep
│   ├── tender-service/       # 业务占位目录，仅 .gitkeep
│   └── codebook-service/     # 码表：政策类型、行业场景
├── packages/platform-common/ # 公共协议、异常、日志、健康检查等基础代码包
├── deploy/
│   ├── gateway/               # Traefik 静态/动态配置
│   └── compose/               # docker-compose.yml、Postgres 初始化脚本
├── docs/                      # 架构设计、开发计划、进度、实施决策
├── Makefile
├── .env.example
└── .gitignore / .dockerignore
```

## 本机环境要求

- Python 3.12（通过 `uv` 管理，不依赖系统 Python 版本）
- Node.js ≥ 20.19（本机验证环境：Node 24 + pnpm 12）
- Docker + Docker Compose v2
- `uv`（Python 依赖与虚拟环境管理）：<https://docs.astral.sh/uv/>
- `pnpm`：<https://pnpm.io/installation>

## 快速开始

```bash
# 1. 检查环境、安装依赖、生成 .env（不会覆盖已存在的 .env）
make bootstrap

# 2. 按需修改 .env（尤其是各数据库密码；本机已有 PostgreSQL/Redis 时
#    可调整 POSTGRES_HOST_PORT / REDIS_HOST_PORT 避免端口冲突）

# 3. 启动本地环境（含 iam-worker）
make dev-up

# 4. 执行数据库迁移，并补建审计清理账号
make migrate

# 5. 冒烟验证网关路由
make smoke

# 6. 打开浏览器访问网关地址（默认 http://localhost:8080）

# 7. 隔离验收（独立库/卷，不会清掉开发数据；测完必须停掉）
make test-integration
make test-e2e
make p6-down
```

停止开发环境（不删除数据卷）：`make dev-down`。  
P6 只用于隔离验收，日常不要开着；详见 [`docs/开发约定.md`](docs/开发约定.md)。

## 各服务本地开发（不经 Docker）

```bash
# platform-common / iam-service / audit-service 任一目录下：
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
`seed`、`admin-create`、`test-integration`、`test-e2e` 已可在隔离栈上使用。

## 开发约定（必须遵守）

新建或修改数据库表时，ORM model **必须**写中文 `comment`：

- 表：`__table_args__ = {"comment": "中文表名"}`（有约束时把该字典放在 `__table_args__` tuple 最后一项）
- 列：每个 `mapped_column(..., comment="中文列名")`，与页面/Excel 表头对齐
- Alembic 建表、加列时同步带上 comment，方便 Navicat 直接看到业务含义

日常只用 `make dev-up`。P6 是隔离验收栈，测完必须 `make p6-down`，不要常开。

完整说明见 [`docs/开发约定.md`](docs/开发约定.md)。

## 已知限制

- 本期不执行生产部署；`deploy/gateway/traefik.prod.yml.example` 只是 HTTPS 模板。
- 最后管理员并发保护已有行锁实现，验收覆盖了禁用唯一管理员返回 403，未做双客户端压测。
- 业务表、业务 API、业务页面仍未开发，等待后续需求。
