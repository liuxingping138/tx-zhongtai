#!/bin/sh
# 一次性：给 2026-11-11 之前的 AI提问 审计事件补「业务线」（操作日志的「类型」）。在 postgres 容器内用超级用户执行：
#   $DC exec -T postgres sh < deploy/compose/scripts/backfill-audit-business-line.sh
#
# 那之前 ai-service 入队时没记模板类型，迁移 a6d4e0f5c705 补不出来。事件的目标ID 是模板ID或任务ID：
# 从 ai 库导出「ID -> 模板类型」（现存模板取当前类型；删掉的模板按它留下的任务快照的类型；任务取发起时快照的类型），
# 再更新审计库里还没有业务线的 AI 事件。两个库之间不直连，这里用超级用户分别读写，只补分类标签，不动事件内容。
# 模板删了、又没留下任务的查不到，保持为空。只改 business_line 为空的行，可重复执行。
set -eu

MAP=$(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$AI_DB_NAME" -tA -F '|' <<'SQL'
SELECT id, category FROM ai_prompt_templates
UNION
SELECT DISTINCT ON (prompt_id) prompt_id, prompt_category FROM ai_batch_runs
  WHERE prompt_id NOT IN (SELECT id FROM ai_prompt_templates)
UNION
SELECT id, prompt_category FROM ai_batch_runs;
SQL
)
[ -n "$MAP" ] || { echo "ai 库里没有模板和任务，不用补"; exit 0; }

printf '%s\n' "$MAP" | psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$AUDIT_DB_NAME" \
  -c "CREATE TEMP TABLE ai_targets (id text, category text)" \
  -c "COPY ai_targets FROM STDIN WITH (FORMAT text, DELIMITER '|')" -c "
UPDATE audit_events AS e SET business_line = t.category
FROM ai_targets AS t
WHERE e.business_line IS NULL AND split_part(e.module_code, '.', 1) = 'ai'
  AND e.target_id = t.id AND t.category IN ('policy', 'customer', 'tender');
" -c "
SELECT coalesce(business_line, '(空)') AS business_line, count(*) FROM audit_events
WHERE split_part(module_code, '.', 1) = 'ai' GROUP BY 1 ORDER BY 1;
"
