#!/bin/sh
# 在 postgres 容器内执行：为已有数据卷补建审计清理账号。
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v cleanup_user="$AUDIT_CLEANUP_DB_USER" -v cleanup_pass="$AUDIT_CLEANUP_DB_PASSWORD" <<'EOSQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'cleanup_user', :'cleanup_pass')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = :'cleanup_user') \gexec
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$AUDIT_DB_NAME" \
  -v cleanup_user="$AUDIT_CLEANUP_DB_USER" -v audit_db="$AUDIT_DB_NAME" <<'EOSQL'
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'audit_db', :'cleanup_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'cleanup_user') \gexec
EOSQL
