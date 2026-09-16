#!/bin/sh
# 在 postgres 容器内执行：为已有数据卷补建审计清理账号。
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${AUDIT_CLEANUP_DB_USER}') THEN CREATE ROLE \"${AUDIT_CLEANUP_DB_USER}\" LOGIN PASSWORD '${AUDIT_CLEANUP_DB_PASSWORD}'; END IF; END \$\$;"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$AUDIT_DB_NAME" \
  -c "GRANT CONNECT ON DATABASE \"${AUDIT_DB_NAME}\" TO \"${AUDIT_CLEANUP_DB_USER}\";"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$AUDIT_DB_NAME" \
  -c "GRANT USAGE ON SCHEMA public TO \"${AUDIT_CLEANUP_DB_USER}\";"
