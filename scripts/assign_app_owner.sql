-- 只改当前数据库 public 下的对象属主。不要对整个实例执行 REASSIGN OWNED。
SELECT set_config('tx.app_owner', :'app_owner', false);

DO $$
DECLARE
  owner_name text := current_setting('tx.app_owner');
  rec record;
BEGIN
  IF owner_name !~ '^[A-Za-z_][A-Za-z0-9_]*$' THEN
    RAISE EXCEPTION '非法应用账号名';
  END IF;
  FOR rec IN
    SELECT n.nspname, c.relname, c.relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
  LOOP
    IF rec.relkind = 'S' THEN
      EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO %I', rec.nspname, rec.relname, owner_name);
    ELSIF rec.relkind = 'v' THEN
      EXECUTE format('ALTER VIEW %I.%I OWNER TO %I', rec.nspname, rec.relname, owner_name);
    ELSIF rec.relkind = 'm' THEN
      EXECUTE format('ALTER MATERIALIZED VIEW %I.%I OWNER TO %I', rec.nspname, rec.relname, owner_name);
    ELSIF rec.relkind = 'f' THEN
      EXECUTE format('ALTER FOREIGN TABLE %I.%I OWNER TO %I', rec.nspname, rec.relname, owner_name);
    ELSE
      EXECUTE format('ALTER TABLE %I.%I OWNER TO %I', rec.nspname, rec.relname, owner_name);
    END IF;
  END LOOP;
  FOR rec IN
    SELECT n.nspname, p.proname, pg_get_function_identity_arguments(p.oid) AS args
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
  LOOP
    EXECUTE format(
      'ALTER FUNCTION %I.%I(%s) OWNER TO %I',
      rec.nspname, rec.proname, rec.args, owner_name
    );
  END LOOP;
  FOR rec IN
    SELECT n.nspname, t.typname
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    LEFT JOIN pg_class c ON c.oid = t.typrelid
    WHERE n.nspname = 'public'
      AND t.typtype IN ('e', 'd')
      AND c.oid IS NULL
  LOOP
    EXECUTE format('ALTER TYPE %I.%I OWNER TO %I', rec.nspname, rec.typname, owner_name);
  END LOOP;
END $$;
