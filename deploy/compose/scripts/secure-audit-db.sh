#!/bin/sh
# 在 postgres 容器内用超级用户执行：审计库收归超级用户所有，应用账号对 audit_events 只剩查和插，删除只给清理账号。
#
# 原来审计库、public schema 和 audit_events 的属主都是应用账号：「收回删改权」防不住被攻破的应用账号，
# 属主可以把权限再授给自己，还能直接删表、删库。属主换成超级用户后，迁移也要用超级用户跑（见 Makefile 的
# migrate-audit），每次迁移后重跑本脚本：新建的表靠默认权限给应用账号，audit_events 的权限每次收紧一遍。
# 可重复执行。
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$AUDIT_DB_NAME" <<SQL
ALTER DATABASE "${AUDIT_DB_NAME}" OWNER TO "${POSTGRES_USER}";
ALTER SCHEMA public OWNER TO "${POSTGRES_USER}";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM "${AUDIT_DB_USER}";
GRANT USAGE ON SCHEMA public TO "${AUDIT_DB_USER}", "${AUDIT_CLEANUP_DB_USER}";
REVOKE ALL ON DATABASE "${AUDIT_DB_NAME}" FROM PUBLIC;
GRANT CONNECT ON DATABASE "${AUDIT_DB_NAME}" TO "${AUDIT_DB_USER}", "${AUDIT_CLEANUP_DB_USER}";

DO \$\$
DECLARE item record;
BEGIN
  FOR item IN
    SELECT c.relname, c.relkind
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'S', 'v', 'm')
      AND pg_get_userbyid(c.relowner) <> current_user
  LOOP
    EXECUTE format(
      'ALTER %s public.%I OWNER TO %I',
      CASE item.relkind WHEN 'S' THEN 'SEQUENCE' WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' ELSE 'TABLE' END,
      item.relname,
      current_user
    );
  END LOOP;
END
\$\$;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "${AUDIT_DB_USER}";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "${AUDIT_DB_USER}";
ALTER DEFAULT PRIVILEGES FOR ROLE "${POSTGRES_USER}" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "${AUDIT_DB_USER}";
ALTER DEFAULT PRIVILEGES FOR ROLE "${POSTGRES_USER}" IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "${AUDIT_DB_USER}";

REVOKE ALL ON TABLE audit_events FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE audit_events FROM "${AUDIT_DB_USER}";
GRANT SELECT, INSERT ON TABLE audit_events TO "${AUDIT_DB_USER}";
REVOKE ALL ON TABLE audit_events FROM "${AUDIT_CLEANUP_DB_USER}";
GRANT SELECT, DELETE ON TABLE audit_events TO "${AUDIT_CLEANUP_DB_USER}";
SQL

echo "audit_db_secured db=${AUDIT_DB_NAME} owner=${POSTGRES_USER}"
