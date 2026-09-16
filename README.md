# tx-zhongtai 中台系统

Vue 前端 + Python 微服务后端的中台管理系统。当前处于 **P1（工程骨架）** 阶段：
公共服务骨架、网关、数据库迁移入口、容器部署已落地并通过验证；账号、认证、
角色、权限等业务能力从 P2 阶段起逐步实现。业务模块（政策、客户、招投标、
码表管理）仅保留目录占位，不在本期开发范围内。

详见：
- [`docs/中台系统公共基础框架设计.md`](docs/中台系统公共基础框架设计.md) —— 架构设计
- [`docs/Cursor公共框架开发计划.md`](docs/Cursor公共框架开发计划.md) —— 分阶段开发计划
- [`docs/开发进度.md`](docs/开发进度.md) —— 当前实际进度与验证记录
- [`docs/实现决策.md`](docs/实现决策.md) —— 端口、数据库、技术选型等实施细节

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
│   ├── iam-service/          # 身份权限服务（P2/P3 起实现账号、认证、权限）
│   ├── audit-service/        # 审计日志服务（P5 起实现事件接收与查询）
│   ├── policy-service/       # 业务占位目录，仅 .gitkeep
│   ├── customer-service/     # 业务占位目录，仅 .gitkeep
│   ├── tender-service/       # 业务占位目录，仅 .gitkeep
│   └── codebook-service/     # 业务占位目录，仅 .gitkeep
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

# 3. 启动本地环境（Postgres、Redis、iam-service、audit-service、frontend、gateway）
make dev-up

# 4. 执行数据库迁移（当前阶段迁移链为空，仅验证迁移入口可用）
make migrate

# 5. 冒烟验证网关路由
make smoke

# 6. 打开浏览器访问网关地址（默认 http://localhost:8080）
```

停止环境（不删除数据卷）：`make dev-down`。

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
`seed`、`admin-create`、`test-integration`、`test-e2e` 依赖 P2/P4 阶段的账号、
权限、页面能力，当前阶段调用会明确提示"尚未实现"，不会假装成功。

## 已知限制（P1 阶段）

- 账号、登录、角色、权限功能尚未实现，`/api/v1/auth`、`/api/v1/system` 当前
  只有工程骨架（统一响应/异常/健康检查），实际业务路由在 P2/P3 阶段加入。
- 审计事件接收、Outbox 消费、日志查询在 P2（写入基础）与 P5（消费/查询）阶段实现。
- 前端登录页、系统管理页面、权限树等在 P4 阶段实现；当前只有布局骨架和占位首页。
- 生产 HTTPS、备份恢复、监控接入等在 P6 阶段完成，当前仅提供配置模板
  （见 `deploy/gateway/traefik.prod.yml.example`）。
