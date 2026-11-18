SHELL := /bin/bash
.DEFAULT_GOAL := help

# 服务器上（SERVER=1）只有独立的 docker-compose，业务栈还叠了 HTTPS 那份：make SERVER=1 outbox-replay
ifeq ($(SERVER),1)
COMPOSE := docker-compose -f deploy/compose/docker-compose.yml -f deploy/compose/docker-compose.https.yml --env-file .env
else
COMPOSE := docker compose -f deploy/compose/docker-compose.yml --env-file .env
endif
P6_ENV := deploy/compose/.p6.env
# 服务器上跑 P6（scripts/p6-on-server.sh 传 P6_SERVER=1）：那里只有独立的 docker-compose，没有 docker compose 插件。
ifeq ($(P6_SERVER),1)
P6_DOCKER := docker
P6_DOCKER_COMPOSE := docker-compose
else
P6_DOCKER := docker
P6_DOCKER_COMPOSE := docker compose
endif
P6_COMPOSE := $(P6_DOCKER_COMPOSE) -p tx-zhongtai-p6 -f deploy/compose/docker-compose.yml -f deploy/compose/docker-compose.p6.yml --env-file $(P6_ENV)
PY_PACKAGES := packages/platform-common services/iam-service services/audit-service services/codebook-service services/policy-service services/ai-service services/tender-service services/thinktank-service
JWT_KEYS_DIR := deploy/secrets/jwt
JWT_P6_DIR := deploy/secrets/jwt-p6

.PHONY: p6-logs help bootstrap jwt-keys jwt-keys-p6 dev-up dev-down migrate migrate-check seed admin-create check \
        test-unit test-integration test-e2e smoke migrate-audit provision-audit-cleanup provision-codebook-db \
        seed-area-codes crawler-sync crawler-backfill \
        provision-policy-db provision-ai-db \
        outbox-replay audit-cleanup iam-session-cleanup p6-env p6-up p6-down p6-migrate p6-seed p6-admin \
        p6-backup p6-restore p6-fixtures export-openapi scan-scope hooks audit-deps

help:
	@echo "可用命令："
	@echo "  make bootstrap        检查环境、安装依赖、启用 git 钩子（不覆盖已有 .env）"
	@echo "  make hooks            启用 .githooks（提交前代码规则 + ruff，提交信息格式，推送前完整质量门）"
	@echo "  make dev-up           启动本地开发环境（Compose）"
	@echo "  make dev-down         停止本地开发环境（保留数据卷）"
	@echo "  make migrate          对已运行的各服务执行数据库迁移"
	@echo "  make seed             幂等同步公共资源/动作/菜单与内置超级管理员角色"
	@echo "  make seed-area-codes  从 SQL 种子导入省市区编码表（按区县编码去重）"
	@echo "  make crawler-sync     爬虫监测日常同步（按入库时间水位增量）"
	@echo "  make crawler-backfill 爬虫监测首次回填（从总表最早采集日起，建立水位）"
	@echo "  make admin-create     创建初始管理员（密码从 ADMIN_PASSWORD 读取，不进命令行参数）"
	@echo "  make check            Python 静态检查 + 前端类型检查/构建/lint"
	@echo "  make migrate-check    检查各服务 model 与数据库是否漂移（需开发栈已启动）"
	@echo "  make test-unit        运行全部 Python 包（platform-common + iam/audit/codebook/policy/ai）+ 前端的单元测试"
	@echo "  make test-integration 隔离栈 A01-A15 等真实依赖验收"
	@echo "  make test-e2e         Playwright 关键流程（需先 integration）"
	@echo "  make smoke            经网关执行公共功能冒烟验证"
	@echo "  make migrate-audit    用超级用户迁移审计库并收紧权限（服务器上 make SERVER=1 migrate-audit）"
	@echo "  make provision-audit-cleanup  为已有数据卷补建审计清理账号"
	@echo "  make outbox-replay    重放 iam/policy/codebook/ai 的 dead/failed Outbox 事件"
	@echo "  make audit-cleanup    使用独立清理账号删除到期审计事件"
	@echo "  make iam-session-cleanup  清理已过期/已撤销的会话与刷新令牌"
	@echo "  make p6-up / p6-down  启动/销毁隔离验收栈（down 删除隔离卷）"
	@echo "  make export-openapi   从本地 FastAPI 应用导出 OpenAPI"
	@echo "  make scan-scope       检查业务目录占位与仓库密钥扫描"
	@echo "  make audit-deps       依赖漏洞扫描（pip-audit + pnpm audit，需要外网）"
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
	@$(MAKE) hooks
	@echo "bootstrap 完成。"

hooks:
	@git config core.hooksPath .githooks
	@echo "已启用 .githooks；紧急情况可用 --no-verify 跳过，事后补跑 make check / make test-unit。"

jwt-keys:
	@mkdir -p $(JWT_KEYS_DIR)
	@cd services/iam-service && uv run python -c "from pathlib import Path; from app.core.jwt_keys import ensure_jwt_keys; ensure_jwt_keys(Path('../../$(JWT_KEYS_DIR)').resolve(), allow_generate=True)"
	@echo "JWT 开发密钥已就绪（目录 $(JWT_KEYS_DIR)，不入库）。"

dev-up: jwt-keys
	$(COMPOSE) up -d --build

dev-down:
	$(COMPOSE) down

# 审计库归超级用户所有（deploy/compose/scripts/secure-audit-db.sh）：应用账号不是属主、改不了表结构，
# 迁移用超级用户跑，跑完重新收紧 audit_events 的权限。$(1) 是 compose 命令，$(2) 是带超级用户密码的 env 文件。
# 超级用户口令只有 postgres 容器和这里用，各服务 Settings 的示例密钥检查管不到它；5433 对公网开放，
# 它能进全部五个库。生产环境还是示例值（或空）就拒绝往下走。
define migrate_audit
	@set -a && . ./$(2) && set +a && case "$${ENVIRONMENT:-development}:$${POSTGRES_SUPERUSER_PASSWORD:-}" in \
		production:|production:dev-only-*|production:p6-only-*|production:change-me*) \
		echo "生产环境的 POSTGRES_SUPERUSER_PASSWORD 为空或还是示例值：先在库里改掉超级用户口令，再同步写进 .env" >&2; exit 1;; \
	esac
	@set -a && . ./$(2) && set +a && $(1) exec -T \
		-e AUDIT_DATABASE_URL="postgresql+asyncpg://$${POSTGRES_SUPERUSER:-postgres}:$${POSTGRES_SUPERUSER_PASSWORD}@postgres:5432/$${AUDIT_DB_NAME}" \
		audit-service .venv/bin/alembic upgrade head
	$(1) exec -T postgres sh < deploy/compose/scripts/secure-audit-db.sh
endef

migrate:
	@echo "== iam-service 迁移 =="
	$(COMPOSE) exec -T iam-service .venv/bin/alembic upgrade head
	@$(MAKE) provision-audit-cleanup
	@$(MAKE) migrate-audit
	@$(MAKE) provision-codebook-db
	@echo "== codebook-service 迁移 =="
	$(COMPOSE) exec -T codebook-service .venv/bin/alembic upgrade head
	@$(MAKE) provision-policy-db
	@echo "== policy-service 迁移 =="
	$(COMPOSE) exec -T policy-service .venv/bin/alembic upgrade head
	@$(MAKE) provision-ai-db
	@echo "== ai-service 迁移 =="
	$(COMPOSE) exec -T ai-service .venv/bin/alembic upgrade head
	@$(MAKE) provision-thinktank-db
	@echo "== thinktank-service 迁移 =="
	$(COMPOSE) exec -T thinktank-service .venv/bin/alembic upgrade head

migrate-check:
	@# alembic check 需要连真实库，进不了 make check，单独跑。
	@# model 改了但没写迁移、或迁移漏建索引/约束，都会在这里暴露。
	@# 失败必须原样返回非零退出码，不能再把检查结果送进 tail。
	COMPOSE_CMD="$(COMPOSE)" bash scripts/migrate_check.sh

migrate-audit:
	@echo "== audit-service 迁移（超级用户）并收紧审计库权限 =="
	$(call migrate_audit,$(COMPOSE),.env)

provision-audit-cleanup:
	@echo "== 补建审计清理账号（已有数据卷不会重跑 init） =="
	$(COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-audit-cleanup.sh

provision-codebook-db:
	@echo "== 补建码表库和账号（已有数据卷不会重跑 init） =="
	$(COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-codebook-db.sh

provision-policy-db:
	@echo "== 补建政策库和账号（已有数据卷不会重跑 init） =="
	$(COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-policy-db.sh

provision-ai-db:
	@echo "== 补建 AI提问库和账号（已有数据卷不会重跑 init） =="
	$(COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-ai-db.sh

provision-thinktank-db:
	@echo "== 补建智库数据库和账号（已有数据卷不会重跑 init） =="
	$(COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-thinktank-db.sh

# iam、policy、codebook、ai、thinktank 各有一张 Outbox 表，逐个重放。只重放某一个：make outbox-replay OUTBOX_SERVICES=policy-service
OUTBOX_SERVICES ?= iam-service policy-service codebook-service ai-service thinktank-service
outbox-replay:
	@set -e; for s in $(OUTBOX_SERVICES); do \
		echo "== $$s =="; \
		$(COMPOSE) exec -T $$s .venv/bin/python -m app.cli.outbox_replay; \
	done

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

seed-knowledge:
	$(COMPOSE) exec -T thinktank-service .venv/bin/python -m app.cli.seed_knowledge

# 爬虫监测：只读采集总表，按「网站名称 + 省份 + 地市」统计。首次必须先回填建立水位。
crawler-sync:
	$(COMPOSE) exec -T policy-service .venv/bin/python -m app.cli.sync_crawler

# 回填中断后用 ARGS=--skip-existing 续跑。
crawler-backfill:
	$(COMPOSE) exec -T policy-service .venv/bin/python -m app.cli.sync_crawler --backfill $(ARGS)

admin-create:
	@if [ -z "$$ADMIN_PASSWORD" ]; then echo "请通过环境变量 ADMIN_PASSWORD 传入初始密码，不要写在命令行参数里。"; exit 2; fi
	$(COMPOSE) exec -T -e ADMIN_USERNAME -e ADMIN_PASSWORD -e ADMIN_DISPLAY_NAME iam-service .venv/bin/python -m app.cli.admin_create

check:
	@echo "== Python 静态检查 =="
	@(cd packages/platform-common && uv run ruff format --check . && uv run ruff check . && uv run mypy platform_common) || exit 1
	@(cd services/iam-service && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run lint-imports) || exit 1
	@(cd services/audit-service && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run lint-imports) || exit 1
	@(cd services/codebook-service && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run lint-imports) || exit 1
	@(cd services/policy-service && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run lint-imports) || exit 1
	@(cd services/ai-service && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run lint-imports) || exit 1
	@(cd services/tender-service && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run lint-imports) || exit 1
	@(cd services/thinktank-service && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run lint-imports) || exit 1
	@echo "== 前端类型检查 =="
	@(cd frontend && pnpm run type-check)
	@echo "== 前端构建 =="
	@(cd frontend && pnpm run build)
	@echo "== 前端 lint =="
	@(cd frontend && pnpm run lint)
	@echo "== 范围与密钥扫描 =="
	@python3 scripts/scan_scope.py
	@python3 scripts/test_scan_scope.py
	@echo "== 文件行数与忽略注释原因 =="
	@python3 scripts/check_code_rules.py
	@python3 scripts/test_check_code_rules.py
	@bash scripts/test_migrate_check.sh
	@echo "== OpenAPI 与应用对象一致 =="
	@bash scripts/check_openapi.sh

test-unit:
	@for pkg in $(PY_PACKAGES); do \
		echo "-- $$pkg --"; \
		(cd $$pkg && uv run pytest -q --cov --cov-report=) || exit 1; \
	done
	@(cd frontend && pnpm test)
	@python3 scripts/test_scan_scope.py
	@python3 scripts/test_check_code_rules.py
	@bash scripts/test_migrate_check.sh

p6-env:
	@if [ ! -f $(P6_ENV) ]; then cp deploy/compose/p6.env.example $(P6_ENV); echo "已生成 $(P6_ENV)"; fi
	@# 网关默认绑 0.0.0.0；P6 的账号密码是明文样例，在服务器上不能对外暴露，旧的 .p6.env 也补上。
	@grep -q '^GATEWAY_BIND_ADDR=' $(P6_ENV) || echo 'GATEWAY_BIND_ADDR=127.0.0.1' >> $(P6_ENV)
	@# 新增服务的库配置：已有的 .p6.env 不会重新从样例生成，缺什么补什么。
	@grep -q '^AI_DB_NAME=' $(P6_ENV) || printf 'AI_DB_NAME=ai_p6_db\nAI_DB_USER=ai_p6\nAI_DB_PASSWORD=p6-only-change-me-ai\n' >> $(P6_ENV)
	@grep -q '^THINKTANK_DB_NAME=' $(P6_ENV) || printf 'THINKTANK_DB_NAME=thinktank_p6_db\nTHINKTANK_DB_USER=thinktank_p6\nTHINKTANK_DB_PASSWORD=p6-only-change-me-thinktank\n' >> $(P6_ENV)

jwt-keys-p6:
	@bash scripts/gen-jwt-keys.sh $(JWT_P6_DIR)

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

# 验收失败时看现场：各服务状态与最近日志。
p6-logs:
	-$(P6_COMPOSE) ps
	-$(P6_COMPOSE) logs --tail 40 iam-service gateway

p6-migrate:
	$(P6_COMPOSE) exec -T iam-service .venv/bin/alembic upgrade head
	$(P6_COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-audit-cleanup.sh
	$(call migrate_audit,$(P6_COMPOSE),$(P6_ENV))
	$(P6_COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-codebook-db.sh
	$(P6_COMPOSE) exec -T codebook-service .venv/bin/alembic upgrade head
	$(P6_COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-policy-db.sh
	$(P6_COMPOSE) exec -T policy-service .venv/bin/alembic upgrade head
	$(P6_COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-ai-db.sh
	$(P6_COMPOSE) exec -T ai-service .venv/bin/alembic upgrade head
	$(P6_COMPOSE) exec -T postgres sh < deploy/compose/scripts/provision-thinktank-db.sh
	$(P6_COMPOSE) exec -T thinktank-service .venv/bin/alembic upgrade head

p6-seed:
	$(P6_COMPOSE) exec -T iam-service .venv/bin/python -m app.cli.seed
	$(P6_COMPOSE) exec -T thinktank-service .venv/bin/python -m app.cli.seed_knowledge

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
	@(cd services/ai-service && uv run python ../../scripts/export_openapi.py ai)
	@(cd services/tender-service && uv run python ../../scripts/export_openapi.py tender)
	@(cd services/thinktank-service && uv run python ../../scripts/export_openapi.py thinktank)

scan-scope:
	python3 scripts/scan_scope.py

audit-deps:
	@bash scripts/audit_deps.sh

test-integration: p6-up
	@set -a && . ./$(P6_ENV) && set +a && \
	P6_GATEWAY=http://localhost:$$GATEWAY_HTTP_PORT \
	P6_COMPOSE="$(P6_COMPOSE)" \
	P6_RUNTIME_FILE=deploy/compose/.p6.runtime \
	sh -c 'python3 tests/p6/accept.py \
	  && set -a && . ./deploy/compose/.p6.runtime && set +a \
	  && (python3 -c "import httpx, openpyxl" >/dev/null 2>&1 && python3 tests/p6/upload_limits.py \
	      || $(P6_DOCKER) run --rm --network host -e P6_GATEWAY -e IAM_DB_NAME -e AUDIT_DB_NAME -e POLICY_DB_NAME -e CODEBOOK_DB_NAME -e ADMIN_USERNAME -e ADMIN_PASSWORD -v "$$(pwd)/tests/p6:/p6:ro" -w /p6 tx-zhongtai-p6-codebook-service /srv/services/codebook-service/.venv/bin/python /p6/upload_limits.py) \
	  && python3 tests/p6/business_patch.py'
	@P6_COMPOSE="$(P6_COMPOSE)" DOCKER="$(P6_DOCKER)" P6_SERVER="$(P6_SERVER)" bash scripts/scheduler-integration.sh
	@P6_COMPOSE="$(P6_COMPOSE)" DOCKER="$(P6_DOCKER)" P6_SERVER="$(P6_SERVER)" bash scripts/ai-integration.sh

p6-fixtures:
	$(P6_COMPOSE) exec -T policy-service .venv/bin/python < tests/p6/seed_crawler.py

test-e2e: p6-fixtures
	@test -f deploy/compose/.p6.runtime || (echo "请先运行 make test-integration"; exit 2)
	@set -a && . ./deploy/compose/.p6.runtime && set +a && \
	export P6_GATEWAY=http://localhost:$$(grep -E '^GATEWAY_HTTP_PORT=' $(P6_ENV) | cut -d= -f2) && \
	if [ "$(P6_SERVER)" = "1" ]; then DOCKER="$(P6_DOCKER)" bash scripts/e2e-docker.sh; \
	else (cd frontend && pnpm exec playwright test); fi

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
