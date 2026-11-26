#!/bin/sh
# 在 postgres 容器内执行：为已有数据卷补建 AI提问库和账号。
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v db_user="$AI_DB_USER" -v db_pass="$AI_DB_PASSWORD" -v db_name="$AI_DB_NAME" <<'EOSQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'db_user', :'db_pass')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = :'db_user') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'db_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db_name') \gexec
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$AI_DB_NAME" \
  -v db_user="$AI_DB_USER" -v db_name="$AI_DB_NAME" <<'EOSQL'
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db_name') \gexec
SELECT format('GRANT ALL PRIVILEGES ON SCHEMA public TO %I', :'db_user') \gexec
EOSQL
