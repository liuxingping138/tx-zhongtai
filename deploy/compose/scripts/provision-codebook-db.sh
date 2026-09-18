#!/bin/sh
# 在 postgres 容器内执行：为已有数据卷补建码表库和账号。
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${CODEBOOK_DB_USER}') THEN CREATE ROLE \"${CODEBOOK_DB_USER}\" LOGIN PASSWORD '${CODEBOOK_DB_PASSWORD}'; END IF; END \$\$;"

if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '${CODEBOOK_DB_NAME}'" | grep -q 1; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -c "CREATE DATABASE \"${CODEBOOK_DB_NAME}\" OWNER \"${CODEBOOK_DB_USER}\";"
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$CODEBOOK_DB_NAME" \
  -c "REVOKE ALL ON DATABASE \"${CODEBOOK_DB_NAME}\" FROM PUBLIC;"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$CODEBOOK_DB_NAME" \
  -c "GRANT ALL PRIVILEGES ON SCHEMA public TO \"${CODEBOOK_DB_USER}\";"
