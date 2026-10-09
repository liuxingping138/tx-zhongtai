#!/usr/bin/env bash
# 用一次性 Postgres 容器验证：恢复后的属主脚本能让应用账号执行 ALTER。
# 不连接业务库，容器在退出时删除。
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
name="txzt-owner-$$"
docker rm -f "$name" >/dev/null 2>&1 || true
docker run -d --name "$name" -e POSTGRES_PASSWORD=test -e POSTGRES_USER=postgres postgres:17.2-alpine >/dev/null
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
ready=0
for _ in $(seq 1 40); do
  if docker exec "$name" pg_isready -U postgres >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "临时 Postgres 没有就绪" >&2
  exit 1
fi
docker exec "$name" psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE USER app_user LOGIN PASSWORD 'test';" >/dev/null
docker exec "$name" psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE appdb OWNER postgres;" >/dev/null
docker exec "$name" psql -U postgres -d appdb -v ON_ERROR_STOP=1 -c "CREATE TABLE kept (id int); CREATE SEQUENCE kept_id_seq;" >/dev/null
docker exec -i "$name" psql -U postgres -d appdb -v ON_ERROR_STOP=1 -v app_owner=app_user < "$root/scripts/assign_app_owner.sql" >/dev/null
owner="$(docker exec "$name" psql -U postgres -d appdb -At -c "SELECT tableowner FROM pg_tables WHERE tablename='kept';")"
seq_owner="$(docker exec "$name" psql -U postgres -d appdb -At -c "SELECT r.rolname FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE c.relname = 'kept_id_seq';")"
if [ "$owner" != "app_user" ] || [ "$seq_owner" != "app_user" ]; then
  echo "属主未改到应用账号: table=$owner sequence=$seq_owner" >&2
  exit 1
fi
docker exec "$name" psql -U postgres -d appdb -v ON_ERROR_STOP=1 -c "SET ROLE app_user; ALTER TABLE kept ADD COLUMN extra int;" >/dev/null
echo "restore_owner_ok"
