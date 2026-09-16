#!/usr/bin/env bash
# Compose 启动 postgres 容器时执行一次：为 IAM、审计各建立独立数据库和账号。
# 依赖的环境变量由 docker-compose.yml 传入本容器：
# IAM_DB_NAME / IAM_DB_USER / IAM_DB_PASSWORD、AUDIT_DB_NAME / AUDIT_DB_USER / AUDIT_DB_PASSWORD。
set -euo pipefail

create_db_and_user() {
  local db_name="$1"
  local db_user="$2"
  local db_password="$3"

  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL
    DO \$\$
    BEGIN
      IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${db_user}') THEN
        CREATE ROLE "${db_user}" LOGIN PASSWORD '${db_password}';
      END IF;
    END
    \$\$;
EOSQL

  if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" -tAc \
      "SELECT 1 FROM pg_database WHERE datname = '${db_name}'" | grep -q 1; then
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" \
      -c "CREATE DATABASE \"${db_name}\" OWNER \"${db_user}\";"
  fi

  # 独立服务不得跨库读表：不额外授予除自身数据库外的任何权限。
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${db_name}" \
    -c "REVOKE ALL ON DATABASE \"${db_name}\" FROM PUBLIC;"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${db_name}" \
    -c "GRANT ALL PRIVILEGES ON SCHEMA public TO \"${db_user}\";"
}

create_db_and_user "${IAM_DB_NAME}" "${IAM_DB_USER}" "${IAM_DB_PASSWORD}"
create_db_and_user "${AUDIT_DB_NAME}" "${AUDIT_DB_USER}" "${AUDIT_DB_PASSWORD}"
