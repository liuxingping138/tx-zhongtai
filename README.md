# 业务数据运营平台

一体化业务数据平台，Vue 管理端 + Python 微服务后端。已上线的模块：

| 模块 | 内容 |
| --- | --- |
| 政策 | 信源、基础标签、解读，支持 Excel 导入导出 |
| 码表管理 | 政策类型、行业场景、省市区编码 |
| 爬虫监测 | 按网站统计采集情况的只读页面，数据每天从外部爬虫库同步汇总 |
| 系统管理 | 用户、角色与权限、操作日志、任务调度 |

客户、招投标还没有开发，只有占位目录。产品名称统一为「业务数据运营平台」，仓库、包名和部署标识沿用 `tx-zhongtai`。

运行环境：`https://1.119.196.77`（开发部署机）。

## 文档

- [`CLAUDE.md`](CLAUDE.md)：架构要点、硬性开发约定、排查提示，动手前先读
- [工程规范](docs/guides/工程规范.md)：服务划分、代码标准、迁移兼容、日志、自动检查与评审清单
- [UI 视觉规范](DESIGN.md) / [交互契约](UX-CONTRACT.md)：新增或修改前端页面必读
- [部署与维护](docs/guides/部署与维护.md)：同步、构建、数据库、备份恢复
- [`docs/README.md`](docs/README.md)：其余文档的索引（设计决策、操作手册、OpenAPI、原始 Excel）

## 技术栈

- 前端：Vue 3 + TypeScript + Vite + Element Plus + Vue Router + Pinia + Axios，pnpm 管理依赖
- 后端：Python 3.12 + FastAPI + SQLAlchemy 2（异步）+ Alembic，uv 管理依赖
- 数据库与缓存：PostgreSQL 17 + Redis 7，每个服务一个独立的库
- 网关：Traefik 3（文件 Provider）
- 容器：Docker Compose，镜像版本全部锁定，不用 `latest`

## 目录结构

```text
tx-zhongtai/
├── frontend/                  # Vue 管理端
├── services/
│   ├── iam-service/           # 账号、会话、角色权限、菜单；iam-worker 共用此镜像
│   ├── audit-service/         # 操作日志的写入、查询与到期清理
│   ├── policy-service/        # 政策、爬虫监测、任务调度；policy-worker 共用此镜像
│   ├── codebook-service/      # 码表
│   ├── customer-service/      # 占位
│   └── tender-service/        # 占位
├── packages/platform-common/  # 跨服务公共包：响应与异常、鉴权、Outbox、审计、Excel、筛选等
├── deploy/
│   ├── gateway/               # Traefik 配置
│   └── compose/               # docker-compose.yml、Postgres 初始化脚本
├── tests/                     # 跨服务验收（P6）与越权、并发探针
├── scripts/                   # 同步到服务器、隔离验收、备份恢复、代码规则检查等
├── docs/                      # 设计决策与操作手册
├── .githooks/                 # 提交与推送前的自动检查
├── CLAUDE.md / DESIGN.md / UX-CONTRACT.md
├── Makefile
├── ruff.toml                  # 全部 Python 包共用的 lint 配置
└── .env.example
```

## 开始开发

本机需要：uv（<https://docs.astral.sh/uv/>）、pnpm（<https://pnpm.io/installation>）、Node.js ≥ 20.19。
Python 3.12 由 uv 自动管理。Docker 要装（`make bootstrap` 会检查），但日常不用启动。

克隆后执行一次：

```bash
make bootstrap   # 安装 Python 和前端依赖、生成 .env（已有的不覆盖）、启用 git 钩子
```

日常流程：在 Mac 上改代码，提交并推送到 GitLab，再把源码同步到服务器构建：

```bash
bash scripts/sync-to-server.sh
```

服务器上重建哪些服务、迁移和冒烟怎么跑，见[部署与维护](docs/guides/部署与维护.md)的「发布一次改动」。
不要在服务器上 `git pull`，也不要在本机 `make dev-up`。

## 常用命令

| 命令 | 作用 |
| --- | --- |
| `make check` | 质量门：Python ruff + mypy + 分层契约，前端类型检查、构建、lint，文件行数与忽略注释、密钥扫描、OpenAPI 一致性 |
| `make test-unit` | 后端 pytest + 前端 vitest，带覆盖率下限 |
| `make hooks` | 启用 git 钩子（`make bootstrap` 已包含） |
| `make audit-deps` | 依赖漏洞扫描（需要外网） |
| `bash scripts/p6-on-server.sh` | 在服务器上跑隔离的集成测试和 e2e，结束自动销毁 |
| `make export-openapi` | 从 FastAPI 应用导出 OpenAPI |

git 钩子会在提交前检查代码规则和提交信息格式，推送前跑完整的 `make check` + `make test-unit` 和依赖漏洞扫描。

单个测试怎么跑、提交信息格式、数据库表必须写中文注释等约定，见 [`CLAUDE.md`](CLAUDE.md)。

## 已知限制

- 服务器只能按 IP 访问，HTTPS 用文件 Provider 的 `deploy/gateway/traefik.https.yml`，不要换成 Docker Provider 的旧模板。
- 「最后一个管理员不能被停用」靠行锁保证，验收覆盖了返回 403 的情况，没做过双客户端压测。
- 导出不分页，整个结果集读进内存再生成 Excel，单次上限 10 万行。
