#!/usr/bin/env bash
# Compose 启动 postgres 容器时执行一次：为 IAM、审计、码表、政策、AI提问各建立独立数据库和账号。
# 依赖的环境变量由 docker-compose.yml 传入本容器：
# IAM_DB_NAME / IAM_DB_USER / IAM_DB_PASSWORD、AUDIT_DB_NAME / AUDIT_DB_USER / AUDIT_DB_PASSWORD、
# AUDIT_CLEANUP_DB_USER / AUDIT_CLEANUP_DB_PASSWORD。
set -euo pipefail

create_db_and_user() {
  local db_name="$1"
  local db_user="$2"
  local db_password="$3"

  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" \
    -v db_name="$db_name" -v db_user="$db_user" -v db_pwd="$db_password" <<-'EOSQL'
    SELECT format(
      $sql$
      DO $do$
      BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = %L) THEN
          CREATE ROLE %I LOGIN PASSWORD %L;
        END IF;
      END
      $do$;
      $sql$,
      :'db_user', :'db_user', :'db_pwd'
    ) \gexec
    SELECT format(
      'CREATE DATABASE %I OWNER %I;',
      :'db_name', :'db_user'
    )
    WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_name') \gexec
EOSQL

  # 独立服务不得跨库读表：不额外授予除自身数据库外的任何权限。
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${db_name}" \
    -v db_name="$db_name" -v db_user="$db_user" <<-'EOSQL'
    SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC;', :'db_name') \gexec
    SELECT format('GRANT ALL PRIVILEGES ON SCHEMA public TO %I;', :'db_user') \gexec
EOSQL
}

create_db_and_user "${IAM_DB_NAME}" "${IAM_DB_USER}" "${IAM_DB_PASSWORD}"
create_db_and_user "${AUDIT_DB_NAME}" "${AUDIT_DB_USER}" "${AUDIT_DB_PASSWORD}"
create_db_and_user "${CODEBOOK_DB_NAME}" "${CODEBOOK_DB_USER}" "${CODEBOOK_DB_PASSWORD}"
create_db_and_user "${POLICY_DB_NAME}" "${POLICY_DB_USER}" "${POLICY_DB_PASSWORD}"
create_db_and_user "${AI_DB_NAME}" "${AI_DB_USER}" "${AI_DB_PASSWORD}"
if [ -n "${THINKTANK_DB_NAME:-}" ] && [ -n "${THINKTANK_DB_USER:-}" ] && [ -n "${THINKTANK_DB_PASSWORD:-}" ]; then
  create_db_and_user "${THINKTANK_DB_NAME}" "${THINKTANK_DB_USER}" "${THINKTANK_DB_PASSWORD}"
fi

# 清理账号只建登录与 CONNECT，表级 DELETE 在迁移后由 deploy/compose/scripts/secure-audit-db.sh 授予（make migrate-audit）。
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" \
  -v cleanup_user="$AUDIT_CLEANUP_DB_USER" -v cleanup_pwd="$AUDIT_CLEANUP_DB_PASSWORD" <<-'EOSQL'
  SELECT format(
    $sql$
    DO $do$
    BEGIN
      IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = %L) THEN
        CREATE ROLE %I LOGIN PASSWORD %L;
      END IF;
    END
    $do$;
    $sql$,
    :'cleanup_user', :'cleanup_user', :'cleanup_pwd'
  ) \gexec
EOSQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${AUDIT_DB_NAME}" \
  -v audit_db="$AUDIT_DB_NAME" -v cleanup_user="$AUDIT_CLEANUP_DB_USER" <<-'EOSQL'
  SELECT format('GRANT CONNECT ON DATABASE %I TO %I;', :'audit_db', :'cleanup_user') \gexec
  SELECT format('GRANT USAGE ON SCHEMA public TO %I;', :'cleanup_user') \gexec
EOSQL
