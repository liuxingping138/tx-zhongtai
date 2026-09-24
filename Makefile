SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose -f deploy/compose/docker-compose.yml --env-file .env
P6_ENV := deploy/compose/.p6.env
P6_COMPOSE := docker compose -p tx-zhongtai-p6 -f deploy/compose/docker-compose.yml -f deploy/compose/docker-compose.p6.yml --env-file $(P6_ENV)
PY_PACKAGES := packages/platform-common services/iam-service services/audit-service services/codebook-service services/policy-service
JWT_KEYS_DIR := deploy/secrets/jwt
JWT_P6_DIR := deploy/secrets/jwt-p6

.PHONY: help bootstrap jwt-keys jwt-keys-p6 dev-up dev-down migrate migrate-check seed admin-create check \
        test-unit test-integration test-e2e smoke provision-audit-cleanup provision-codebook-db \
        seed-area-codes crawler-sync crawler-backfill crawler-v2-sync crawler-v2-backfill \
        provision-policy-db \
        outbox-replay audit-cleanup iam-session-cleanup p6-env p6-up p6-down p6-migrate p6-seed p6-admin \
        p6-backup p6-restore export-openapi scan-scope

help:
	@echo "可用命令："
	@echo "  make bootstrap        检查环境、安装依赖（不覆盖已有 .env）"
	@echo "  make dev-up           启动本地开发环境（Compose）"
	@echo "  make dev-down         停止本地开发环境（保留数据卷）"
	@echo "  make migrate          对已运行的四个服务执行数据库迁移"
	@echo "  make seed             幂等同步公共资源/动作/菜单与内置超级管理员角色"
	@echo "  make seed-area-codes  从 SQL 种子导入省市区编码表（按区县编码去重）"
	@echo "  make crawler-sync     同步爬虫采集量（日常按入库时间水位增量重算）"
	@echo "  make crawler-backfill 回填爬虫采集量，用 DAYS=365 指定窗口"
	@echo "  make crawler-v2-sync  爬虫监测 v2 日常同步（按入库时间水位增量）"
	@echo "  make crawler-v2-backfill 爬虫监测 v2 首次回填（从总表最早采集日起，建立水位）"
	@echo "  make admin-create     创建初始管理员（密码从 ADMIN_PASSWORD 读取，不进命令行参数）"
	@echo "  make check            Python 静态检查 + 前端类型检查/构建/lint"
	@echo "  make migrate-check    检查各服务 model 与数据库是否漂移（需开发栈已启动）"
	@echo "  make test-unit        运行三个 Python 包 + 前端的单元测试"
	@echo "  make test-integration 隔离栈 A01-A15 等真实依赖验收"
	@echo "  make test-e2e         Playwright 关键流程（需先 integration）"
	@echo "  make smoke            经网关执行公共功能冒烟验证"
	@echo "  make provision-audit-cleanup  为已有数据卷补建审计清理账号"
	@echo "  make outbox-replay    重放 dead/failed Outbox 事件"
	@echo "  make audit-cleanup    使用独立清理账号删除到期审计事件"
	@echo "  make iam-session-cleanup  清理已过期/已撤销的会话与刷新令牌"
	@echo "  make p6-up / p6-down  启动/销毁隔离验收栈（down 删除隔离卷）"
	@echo "  make export-openapi   从本地 FastAPI 应用导出 OpenAPI"
	@echo "  make scan-scope       检查业务目录占位与仓库密钥扫描"
	@echo "  make p6-backup / p6-restore  隔离库备份恢复"

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
	@$(MAKE) jwt-keys
	@echo "bootstrap 完成。"

jwt-keys:
	@mkdir -p $(JWT_KEYS_DIR)
	@cd services/iam-service && uv run python -c "from pathlib import Path; from app.core.jwt_keys import ensure_jwt_keys; ensure_jwt_keys(Path('../../$(JWT_KEYS_DIR)').resolve(), allow_generate=True)"
	@echo "JWT 开发密钥已就绪（目录 $(JWT_KEYS_DIR)，不入库）。"

dev-up: jwt-keys
	$(COMPOSE) up -d --build

dev-down:
	$(COMPOSE) down

migrate:
	@echo "== iam-service 迁移 =="
	$(COMPOSE) exec -T iam-service .venv/bin/alembic upgrade head
	@echo "== audit-service 迁移 =="
	$(COMPOSE) exec -T audit-service .venv/bin/alembic upgrade head
	@$(MAKE) provision-audit-cleanup
	@$(MAKE) provision-codebook-db
	@echo "== 授予审计清理权限 =="
	$(COMPOSE) exec -T audit-service .venv/bin/python -m app.cli.grant_cleanup
	@echo "== codebook-service 迁移 =="
	$(COMPOSE) exec -T codebook-service .venv/bin/alembic upgrade head
	@$(MAKE) provision-policy-db
	@echo "== policy-service 迁移 =="
	$(COMPOSE) exec -T policy-service .venv/bin/alembic upgrade head

migrate-check:
	@# alembic check 需要连真实库，进不了 make check，单独跑。
	@# model 改了但没写迁移、或迁移漏建索引/约束，都会在这里暴露。
	@set -e; for s in iam-service audit-service codebook-service policy-service; do \
		printf '%-20s ' "$$s"; \
		$(COMPOSE) exec -T $$s .venv/bin/alembic check 2>&1 | tail -1; \
	done

provision-audit-cleanup:
	@echo "== 补建审计清理账号（已有数据卷不会重跑 init） =="
	$(COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-audit-cleanup.sh

provision-codebook-db:
	@echo "== 补建码表库和账号（已有数据卷不会重跑 init） =="
	$(COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-codebook-db.sh

provision-policy-db:
	@echo "== 补建政策库和账号（已有数据卷不会重跑 init） =="
	$(COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-policy-db.sh

outbox-replay:
	$(COMPOSE) exec -T iam-service .venv/bin/python -m app.cli.outbox_replay

iam-session-cleanup:
	@echo "== 清理已失效的会话与刷新令牌 =="
	$(COMPOSE) exec -T iam-service .venv/bin/python -m app.cli.session_cleanup

audit-cleanup:
	@set -a && . ./.env && set +a && \
	$(COMPOSE) exec -T \
		-e AUDIT_CLEANUP_DATABASE_URL=postgresql+asyncpg://$$AUDIT_CLEANUP_DB_USER:$$AUDIT_CLEANUP_DB_PASSWORD@postgres:5432/$$AUDIT_DB_NAME \
		audit-service .venv/bin/python -m app.cli.cleanup

seed:
	$(COMPOSE) exec -T iam-service .venv/bin/python -m app.cli.seed

seed-area-codes:
	$(COMPOSE) exec -T codebook-service .venv/bin/python -m app.cli.seed_area_codes

# 爬虫监测：按入库时间水位找出受影响日期，再按采集日聚合到 policy_db。
crawler-sync:
	$(COMPOSE) exec -T policy-service .venv/bin/python -m app.cli.sync_crawler

# 回填历史窗口。整表聚合在爬虫库上跑不动，这里是按天分片查，365 天约 12 分钟。
crawler-backfill:
	$(COMPOSE) exec -T policy-service .venv/bin/python -m app.cli.sync_crawler --days $(or $(DAYS),365)

# 爬虫监测 v2：只读采集总表，按「网站名称 + 省份 + 地市」统计。首次必须先回填建立水位。
crawler-v2-sync:
	$(COMPOSE) exec -T policy-service .venv/bin/python -m app.cli.sync_crawler_v2

# 回填中断后用 ARGS=--skip-existing 续跑。
crawler-v2-backfill:
	$(COMPOSE) exec -T policy-service .venv/bin/python -m app.cli.sync_crawler_v2 --backfill $(ARGS)

admin-create:
	@if [ -z "$$ADMIN_PASSWORD" ]; then echo "请通过环境变量 ADMIN_PASSWORD 传入初始密码，不要写在命令行参数里。"; exit 2; fi
	$(COMPOSE) exec -T -e ADMIN_USERNAME -e ADMIN_PASSWORD -e ADMIN_DISPLAY_NAME iam-service .venv/bin/python -m app.cli.admin_create

check:
	@echo "== Python 静态检查 =="
	@(cd packages/platform-common && uv run ruff check . && uv run mypy platform_common) || exit 1
	@(cd services/iam-service && uv run ruff check . && uv run mypy app) || exit 1
	@(cd services/audit-service && uv run ruff check . && uv run mypy app) || exit 1
	@(cd services/codebook-service && uv run ruff check . && uv run mypy app) || exit 1
	@(cd services/policy-service && uv run ruff check . && uv run mypy app) || exit 1
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
	@(cd frontend && pnpm test)

p6-env:
	@if [ ! -f $(P6_ENV) ]; then cp deploy/compose/p6.env.example $(P6_ENV); echo "已生成 $(P6_ENV)"; fi

jwt-keys-p6:
	@mkdir -p $(JWT_P6_DIR)
	@cd services/iam-service && uv run python -c "from pathlib import Path; from app.core.jwt_keys import ensure_jwt_keys; ensure_jwt_keys(Path('../../$(JWT_P6_DIR)').resolve(), allow_generate=True)"

p6-up: p6-env jwt-keys-p6
	# 必须带 --build：Compose 的镜像按项目名隔离（tx-zhongtai-p6-*），
	# 不重建会拿到上一次验收留下的旧镜像，等于用过期代码做验收。
	$(P6_COMPOSE) up -d --build
	@echo "等待隔离网关..."
	@for i in $$(seq 1 60); do \
		if curl -sf -o /dev/null http://localhost:$$(grep -E '^GATEWAY_HTTP_PORT=' $(P6_ENV) | cut -d= -f2)/api/v1/auth/csrf; then break; fi; \
		sleep 2; \
	done
	@$(MAKE) p6-migrate
	@$(MAKE) p6-seed
	@$(MAKE) p6-admin

p6-down:
	$(P6_COMPOSE) down -v

p6-migrate:
	$(P6_COMPOSE) exec -T iam-service .venv/bin/alembic upgrade head
	$(P6_COMPOSE) exec -T audit-service .venv/bin/alembic upgrade head
	$(P6_COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-audit-cleanup.sh
	$(P6_COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-codebook-db.sh
	$(P6_COMPOSE) exec -T audit-service .venv/bin/python -m app.cli.grant_cleanup
	$(P6_COMPOSE) exec -T codebook-service .venv/bin/alembic upgrade head
	$(P6_COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-policy-db.sh
	$(P6_COMPOSE) exec -T policy-service .venv/bin/alembic upgrade head

p6-seed:
	$(P6_COMPOSE) exec -T iam-service .venv/bin/python -m app.cli.seed

p6-admin:
	@set -a && . ./$(P6_ENV) && set +a && \
	$(P6_COMPOSE) exec -T -e ADMIN_USERNAME -e ADMIN_PASSWORD -e ADMIN_DISPLAY_NAME iam-service .venv/bin/python -m app.cli.admin_create

p6-backup:
	@set -a && . ./$(P6_ENV) && set +a && \
	BACKUP_COMPOSE="$(P6_COMPOSE)" BACKUP_ENV_FILE="$(P6_ENV)" bash scripts/backup.sh

p6-restore:
	@test -n "$(BACKUP)" || (echo "请设置 BACKUP=deploy/backups/<stamp>"; exit 2)
	@set -a && . ./$(P6_ENV) && set +a && \
	BACKUP_COMPOSE="$(P6_COMPOSE)" BACKUP_ENV_FILE="$(P6_ENV)" RESTORE_CONFIRM=$$IAM_DB_NAME bash scripts/restore.sh "$(BACKUP)"

export-openapi:
	@(cd services/iam-service && uv run python ../../scripts/export_openapi.py iam)
	@(cd services/audit-service && uv run python ../../scripts/export_openapi.py audit)
	@(cd services/codebook-service && uv run python ../../scripts/export_openapi.py codebook)
	@(cd services/policy-service && uv run python ../../scripts/export_openapi.py policy)

scan-scope:
	python3 scripts/scan_scope.py

test-integration: p6-up
	@set -a && . ./$(P6_ENV) && set +a && \
	P6_GATEWAY=http://localhost:$$GATEWAY_HTTP_PORT \
	P6_COMPOSE="$(P6_COMPOSE)" \
	P6_RUNTIME_FILE=deploy/compose/.p6.runtime \
	python3 tests/p6/accept.py

test-e2e:
	@test -f deploy/compose/.p6.runtime || (echo "请先运行 make test-integration"; exit 2)
	@set -a && . ./deploy/compose/.p6.runtime && set +a && \
	export P6_GATEWAY=http://localhost:$$(grep -E '^GATEWAY_HTTP_PORT=' $(P6_ENV) | cut -d= -f2) && \
	(cd frontend && pnpm exec playwright test)

smoke:
	@echo "== 经网关冒烟验证（需要 make dev-up 已启动） =="
	@set -e; \
	GW=http://localhost$${GATEWAY_HTTP_PORT:+:$$GATEWAY_HTTP_PORT}; \
	GW=http://localhost:$$(grep -E '^GATEWAY_HTTP_PORT=' .env | cut -d= -f2 || echo 8080); \
	echo "网关地址: $$GW"; \
	echo "- 前端首页应为 200"; \
	curl -sS -o /dev/null -w "  status=%{http_code}\n" $$GW/; \
	echo "- 未接入业务前缀 /api/v1/customer 应为 404（网关拦截，不回退到前端 HTML）"; \
	curl -sS -o /dev/null -w "  status=%{http_code}\n" $$GW/api/v1/customer/anything; \
	echo "- GET /api/v1/auth/csrf 应为 200"; \
	curl -sS -o /dev/null -w "  status=%{http_code}\n" $$GW/api/v1/auth/csrf; \
	echo "- 错误密码登录应为 401"; \
	curl -sS -o /dev/null -w "  status=%{http_code}\n" -X POST $$GW/api/v1/auth/login -H 'Content-Type: application/json' -d '{"username":"nobody","password":"wrong-pass"}'; \
	echo "冒烟验证完成。"
