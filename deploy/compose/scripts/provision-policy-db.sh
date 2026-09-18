#!/bin/sh
# 在 postgres 容器内执行：为已有数据卷补建政策库和账号。
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${POLICY_DB_USER}') THEN CREATE ROLE \"${POLICY_DB_USER}\" LOGIN PASSWORD '${POLICY_DB_PASSWORD}'; END IF; END \$\$;"

if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '${POLICY_DB_NAME}'" | grep -q 1; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -c "CREATE DATABASE \"${POLICY_DB_NAME}\" OWNER \"${POLICY_DB_USER}\";"
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POLICY_DB_NAME" \
  -c "REVOKE ALL ON DATABASE \"${POLICY_DB_NAME}\" FROM PUBLIC;"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POLICY_DB_NAME" \
  -c "GRANT ALL PRIVILEGES ON SCHEMA public TO \"${POLICY_DB_USER}\";"
