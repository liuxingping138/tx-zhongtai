SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose -f deploy/compose/docker-compose.yml --env-file .env
PY_PACKAGES := packages/platform-common services/iam-service services/audit-service

.PHONY: help bootstrap dev-up dev-down migrate seed admin-create check \
        test-unit test-integration test-e2e smoke

help:
	@echo "可用命令："
	@echo "  make bootstrap        检查环境、安装依赖（不覆盖已有 .env）"
	@echo "  make dev-up           启动本地开发环境（Compose）"
	@echo "  make dev-down         停止本地开发环境（保留数据卷）"
	@echo "  make migrate          对已运行的 iam-service/audit-service 执行数据库迁移"
	@echo "  make seed             同步公共资源/动作/菜单清单（P2 阶段实现）"
	@echo "  make admin-create     交互式创建初始管理员（P2 阶段实现）"
	@echo "  make check            Python 静态检查 + 前端类型检查/构建/lint"
	@echo "  make test-unit        运行三个 Python 包 + 前端的单元测试"
	@echo "  make test-integration 真实依赖集成测试（P2+ 阶段补充用例）"
	@echo "  make test-e2e         浏览器端关键流程测试（P4 阶段补充用例）"
	@echo "  make smoke            经网关执行公共功能冒烟验证"

bootstrap:
	@echo "== 检查关键工具版本 =="
	@command -v uv >/dev/null || (echo "缺少 uv，请先安装：https://docs.astral.sh/uv/"; exit 1)
	@command -v pnpm >/dev/null || (echo "缺少 pnpm，请先安装：https://pnpm.io/installation"; exit 1)
	@command -v docker >/dev/null || (echo "缺少 docker"; exit 1)
	@uv --version
	@pnpm --version
	@docker --version
	@docker compose version
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "已从 .env.example 生成 .env，请检查并替换其中的示例密码。"; \
	else \
		echo ".env 已存在，未覆盖。"; \
	fi
	@echo "== 同步 Python 依赖（uv，Python 3.12 虚拟环境） =="
	@for pkg in $(PY_PACKAGES); do \
		echo "-- $$pkg --"; \
		(cd $$pkg && uv python pin 3.12 >/dev/null && uv sync --extra dev) || exit 1; \
	done
	@echo "== 同步前端依赖（pnpm） =="
	@(cd frontend && pnpm install)
	@echo "bootstrap 完成。"

dev-up:
	$(COMPOSE) up -d --build

dev-down:
	$(COMPOSE) down

migrate:
	@echo "== iam-service 迁移 =="
	$(COMPOSE) exec -T iam-service uv run alembic upgrade head
	@echo "== audit-service 迁移 =="
	$(COMPOSE) exec -T audit-service uv run alembic upgrade head

seed:
	@echo "尚未实现：资源/动作/菜单清单同步在 P2 阶段随 IAM 数据模型一起交付。" >&2
	@exit 1

admin-create:
	@echo "尚未实现：初始管理员创建 CLI 在 P2 阶段随账号模型一起交付。" >&2
	@exit 1

check:
	@echo "== Python 静态检查 =="
	@(cd packages/platform-common && uv run ruff check . && uv run mypy platform_common) || exit 1
	@(cd services/iam-service && uv run ruff check . && uv run mypy app) || exit 1
	@(cd services/audit-service && uv run ruff check . && uv run mypy app) || exit 1
	@echo "== 前端类型检查 =="
	@(cd frontend && pnpm run type-check)
	@echo "== 前端构建 =="
	@(cd frontend && pnpm run build)
	@echo "== 前端 lint =="
	@(cd frontend && pnpm run lint)

test-unit:
	@for pkg in $(PY_PACKAGES); do \
		echo "-- $$pkg --"; \
		(cd $$pkg && uv run pytest -q) || exit 1; \
	done
	@echo "前端单元测试（Vitest）尚未接入，P4 阶段随权限/组件逻辑一起补充。"

test-integration:
	@echo "未验证：真实 PostgreSQL/Redis 集成测试用例在 P2 阶段随账号/会话能力一起补充。" >&2
	@exit 1

test-e2e:
	@echo "未验证：Playwright 端到端用例在 P4 阶段随管理端页面一起补充。" >&2
	@exit 1

smoke:
	@echo "== 经网关冒烟验证（需要 make dev-up 已启动） =="
	@set -e; \
	GW=http://localhost$${GATEWAY_HTTP_PORT:+:$$GATEWAY_HTTP_PORT}; \
	GW=http://localhost:$$(grep -E '^GATEWAY_HTTP_PORT=' .env | cut -d= -f2 || echo 8080); \
	echo "网关地址: $$GW"; \
	echo "- 前端首页应为 200"; \
	curl -sS -o /dev/null -w "  status=%{http_code}\n" $$GW/; \
	echo "- 未接入业务前缀 /api/v1/policy 应为 404（网关拦截，不回退到前端 HTML）"; \
	curl -sS -o /dev/null -w "  status=%{http_code}\n" $$GW/api/v1/policy/anything; \
	echo "- IAM 前缀 /api/v1/auth 应可达 iam-service（当前阶段返回统一 404 JSON）"; \
	curl -sS -o /dev/null -w "  status=%{http_code}\n" -X POST $$GW/api/v1/auth/login; \
	echo "冒烟验证完成（P1 阶段：仅验证网关路由骨架，不代表业务功能已实现）。"
