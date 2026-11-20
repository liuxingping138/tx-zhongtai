# Post-remediation review: `eafb716^..58c4c6d`

- **Reviewed commit:** `58c4c6d` (`origin/main`, clean working tree)
- **Compared against:** `docs/project-audit-and-optimization-report.md` and its remediation log (section 4)
- **Method:** read-only code review. `make check` and pytest were not run because the review host has no `python` / `uv`. Every conclusion comes from reading the code, migrations, compose, gateway and script files. Items tagged "plausible" need confirmation on P6 or the server.
- **Out of scope by agreement:** P0-1 (port 5433 / security group), P2-12, P2-20, P2-21.

## 1. Overall verdict

**Not ready for production; follow-up fixes needed.** Most items really did land. Two regressions affect production writes and exports and should go first:

- **The new default-order index** puts a B-tree back on `policy_name` (Text). That index was deliberately removed earlier for exactly this reason (B1).
- **The shared engine factory** applies a 120 s idle-in-transaction timeout to every process, workers included, and there is no way to turn it off. Long requests, such as policy exports with content, get cut off (B2).

Several items the remediation log marks as done are only partly done: P1-3, P1-7, P0-2, P2-15 and P1-6.

## 2. Audit checklist

| Item | Status | Note |
|---|---|---|
| P0-1 / P2-12 / P2-20 / P2-21 | Deferred | external or postponed by agreement |
| P0-2 | PARTIAL | thinktank DB and files are backed up; neither `restore.sh` nor the manual restores `thinktank-files.tar.gz` |
| P1-1 | PASS | all subclass validators renamed (iam and audit included); thinktank DB password is `:?` required in compose |
| P1-2 | PASS | `user_guard.py` rule is correct; `manageable_ids` is N+1 |
| P1-3 | **ISSUE** | idempotency key added, but the orphan-run race remains and the template lock was removed entirely (H3) |
| P1-4 | PASS | |
| P1-5 | PARTIAL | cleaning moved to a thread and source failures return 503; no row cap for content exports, and it now hits the idle-in-transaction timeout (B2) |
| P1-6 | PARTIAL | path fixed and only `load` is called; polling still diffs a current-page snapshot and gives up after about 3 minutes (M4) |
| P1-7 | PARTIAL | exports are audited, **content views are not**; `.env.example` audit caller JSON is missing tender-service (H1, H2) |
| P1-8 | **ISSUE** | the engine factory applies one timeout policy to workers too (B2); no connection-budget doc |
| P1-9 | **ISSUE** | wrong index column, and a failed build leaves an invalid index behind (B1); the COUNT-skip logic is correct |
| P1-10 / P1-11 / P1-12 | PASS | P1-12 still needs a DBA to confirm the source account is SELECT-only |
| P2-1 / 4 / 5 / 7 / 8 / 10 / 11 / 13 / 14 / 17 / 18 | PASS | |
| P2-2 | PARTIAL | heartbeat retries, but never checks that the lock is still held (M2) |
| P2-3 | PASS | the leader exits on the first `SELECT 1` failure, so it never continues on a new connection |
| P2-6 | PASS | commit is inside the compensation block; no scheduled reconcile job |
| P2-9 | PARTIAL | unbuffered routes only for AI batch files and thinktank files; policy, tender and codebook exports and sample-run files still go through buffering |
| P2-15 | PARTIAL | `OnFailure=` alert added; `check_ip_cert_expiry.sh` isn't attached to any timer, so it never runs (M3) |
| P2-16 | PASS | the allowlist includes test values `real-prod-pass` / `R3alPass` (minor) |
| P2-19 | PASS | every wheel event calls `getComputedStyle` on each ancestor, which has some cost |
| P2-22 | PASS | the `LifoQueue` pool is correct; `ping(reconnect=True)` drops the session's read-only setting after a reconnect |
| P3-1 | PARTIAL | `iam.user.exported` is not registered in `_EVENT_META` (M5) |
| P3-2 / 3 / 4 / 10 / 11 / 13 / 14 / 15 / 17 / 18 / 19 / 20 / 21 / 28 | PASS | |
| P3-7 | PARTIAL | only the CSRF constant-time compare, which matches the remediation log |
| P3-8 | PASS | locks taken in a fixed id order, hashes looked up in bulk; the bulk lookup uses a pre-batch snapshot, so a few rows can be wrongly treated as duplicates (Low) |
| P3-25 | **ISSUE** | introduced a keyboard regression (M6) |
| P3-5 / 6 / 9 / 12 / 16 / 22 / 23 / 24 / 26 / 27 | Not claimed in this range | not counted |

## 3. Findings

### Blocker

#### B1. The default-order index brings back a B-tree on `policy_name`, so a long title rolls back a whole tagging batch or import

- **Where:** `services/policy-service/migrations/versions/b1c2d3e4f5a6_base_tag_default_order_idx.py:21-29`, `services/policy-service/app/policy/domain/models.py:111`.
- **Scenario:**
  - `policy_name` is a Text column. `a5b6c7d8e692_drop_policy_name_btree.py:3-4` explains why the old index was dropped: a B-tree index entry is capped at about 2704 bytes, and the source database has rows whose "title" is a whole script. Such a row can't be written, so the entire tagging batch or import rolls back. The composite index `(province_code, policy_name, id)` brings that risk back.
  - If an oversized title already exists, `CREATE INDEX CONCURRENTLY` fails and leaves an INVALID index. Postgres still maintains an invalid index on every write, and `if_not_exists=True` makes re-running the migration skip it, so it never gets fixed.
  - Separately, the session-level `SET lock_timeout='5s'` in `env.py` carries into `autocommit_block`. CONCURRENTLY has to wait for existing transactions on the table, and that wait is limited by lock_timeout, so it fails after 5 s. The result is the same invalid index.
- **Check on the server first:**

  ```sql
  SELECT indisvalid FROM pg_index WHERE indexrelid = 'ix_policy_base_tags_default_order'::regclass;
  SELECT max(octet_length(policy_name)) FROM policy_base_tags;
  ```

- **Fix:**
  - Use an expression index `(province_code, left(policy_name, 200), id)` and make `_ORDER` sort by the same expression, or sort by `(province_code, id)` instead.
  - In the migration, run `DROP INDEX CONCURRENTLY IF EXISTS` first, then `SET lock_timeout = 0` inside `autocommit_block` before building. That matches the repo's other CONCURRENTLY migrations.

#### B2. `create_service_engine` puts a statement timeout and a 120 s idle-in-transaction timeout on every process, workers included, and they can't be disabled

- **Where:** `packages/platform-common/platform_common/database.py:28-56`. Defaults are `statement_timeout_ms=60_000` and `idle_in_transaction_timeout_ms=120_000`; `_env_int` treats 0 as unset and falls back to the default. The policy and ai engines pass `statement_timeout_ms=300_000` explicitly. Compose sets no overrides.
- **Scenario 1: policy export with content.** In `services/policy-service/app/policy/application/base_tags.py:279-300`, `list_filtered` runs inside the request transaction. Then `attach_policy_contents` reads the MySQL source in batches of 200. For 100k rows that's 500 batches with a 20 s read timeout each, and no Postgres statement runs the whole time. After 120 s Postgres kills the connection, the final commit fails, and the user gets a 500. Before this change these exports were just slow; now they fail. The content-export row cap that P1-5 recommended was never added.
- **Scenario 2: crawler sync** (plausible). At `services/policy-service/app/crawler/application/crawler_sync.py:291`, `plan()` has already opened a transaction on the session when it calls `to_thread(fetch_affected_days)` against MySQL. If that query takes more than 2 minutes behind the proxy, the connection that gets killed is the one holding the crawler sync advisory lock.
- **Scenario 3: other long jobs.** Long CLIs and worker jobs (AI tagging, crawler backfill) have no way to opt out of the timeouts.
- **Fix:**
  - Let `_env_int` accept 0 as "not set", and give the env vars a per-service prefix or read them from Settings.
  - Set the timeouts to 0 for every `*-worker` in compose.
  - In exports, `commit()` after the Postgres reads and before fetching content, and add a row cap for content exports.
  - Write the connection budget and timeouts into `docs/design/实现决策.md`.

### High

#### H1. Viewing tender content is still not audited (P1-7 half-done)

- **Where:** the `/{record_id}/content` route in `services/tender-service/app/api/routes.py` is unchanged.
- **Scenario:** opening content leaves no audit trail, so a data leak can't be traced.
- **Fix:** do what the export path does: after reading the content, report the audit event synchronously and return 503 if it can't be written.

#### H2. The audit caller-secret template is missing tender-service

- **Where:** the `AUDIT_INTERNAL_CALLER_SECRETS` JSON at `.env.example:59` has no `"tender-service"` entry. In compose, `TENDER_AUDIT_INGEST_SECRET` defaults to `dev-only-change-me-ingest`.
- **Scenario:** in an environment configured from the template, audit-service returns 401 to tender-service and every tender export becomes a 503. If production misses this secret, the demo default makes tender-service refuse to start. The remediation log lists this as "set in `.env` at deploy time".
- **Fix:**
  - Confirm on the server that `AUDIT_INTERNAL_CALLER_SECRETS` in `.env` includes tender-service.
  - Fill in `.env.example`.
  - Add a P6 acceptance check that an admin tender export returns 200.

#### H3. P1-3: the orphan AI run race is still there, and the template lock was removed entirely

- **Where:** `services/policy-service/app/aitag/application/pipeline.py:170-202`, `services/ai-service/app/application/pipeline_runs.py:147-201`.
- **Scenario:**
  1. On the ai-service side, writing a 56 MB snapshot, reading the previous run's raw output twice and fetching the system code table can take more than 180 s.
  2. Policy's POST times out first and calls `stop_quietly(client_run_id)`. The run row doesn't exist yet, so stop gets a 404, which is swallowed.
  3. ai-service then inserts and commits the row; the worker picks it up and starts spending money.
  4. If the next batch's `_settled` also lands in that window, it gets a 404 too and returns None, so the orphan is never stopped and never counted toward the day's spend.
- **Compounding issue 1:** ai-service holds a read transaction open for the whole file I/O, which hits B2's 120 s idle-in-transaction timeout. The flush fails, the directory is left behind, and large batches keep failing.
- **Compounding issue 2:** `prompts.require(..., lock=False)` drops the template row lock entirely. The report only recommended releasing the lock before file I/O, not removing it.
- **Fix:**
  - When stop or status sees an unknown key, insert a cancelled placeholder (tombstone) run row. The primary-key conflict then makes the late `create` lose the race.
  - After reading the released version, `commit()` to release the lock and transaction before doing file I/O.

### Medium

#### M1. No restore path for thinktank files (P0-2 not closed)

- **Where:** `scripts/restore.sh` restores only databases; `docs/guides/部署与维护.md` has a restore command for `ai-files` only.
- **Fix:** add `tar -C /data/thinktank -xzf - < thinktank-files.tar.gz`, and update the backup format version and the restore-verification script to match.

#### M2. A scheduler heartbeat retry may "stay alive" on a new connection (plausible)

- **Where:** `heartbeat` in `packages/platform-common/platform_common/scheduler/runner.py`.
- **Scenario:** after a disconnect the code calls `rollback()` and retries. After invalidation plus rollback, SQLAlchemy picks up a fresh DBAPI connection, which doesn't hold the leader lock. The heartbeat write succeeds and the process still thinks it's leader, while another worker can grab the lock, so jobs run twice.
- **Fix:** check `connection.invalidated` before retrying, or just exit the way the AI worker does. Alternatively, as the report suggested, check `pg_locks` to confirm the lock is still on this connection.

#### M3. The certificate expiry check is never scheduled

- **Where:** `scripts/check_ip_cert_expiry.sh`.
- **Scenario:** no timer or doc references it, so the `-checkend` check never runs. Only the `OnFailure=` half of P2-15 is in place.
- **Fix:** add a daily `.timer` that runs it, with the same `OnFailure=` alert on failure.

#### M4. Retag polling still uses a current-page snapshot

- **Where:** `frontend/src/modules/policy/base-tags/retag.ts:55-127`.
- **Scenario:**
  - If the user changes page, or the tracked rows aren't on the current page, `snapshot` returns null and completion is never detected.
  - Re-interpreting replaces the old interpretation rows, so on the interpretation list the tracked rows disappear and completion is never detected either.
  - A change in any single row is reported as "done" while others are still processing.
  - It gives up after about 3 minutes (10×3 s + 10×5 s + 10×10 s), while AI batches usually take several minutes, so it often stops too early.
- **Fix:** fetch the tracked rows one by one by id (a 404 counts as processed), count completions and failures, and extend the window to about 15 minutes.

#### M5. `iam.user.exported` has no event metadata

- **Where:** `services/iam-service/app/application/event_map.py:18-28`.
- **Scenario:** the event is stored with module `iam` and the raw event name as its action, so filtering the audit log by the user-management module doesn't show it.
- **Fix:** add `("system.users", "export", "user", "导出用户")` to `_EVENT_META`.

#### M6. Keyboard regression in SamplePreviewTable

- **Where:** `frontend/src/modules/ai/prompts/SamplePreviewTable.vue:51-58` and `:95-104`.
- **Scenario:** the whole `<tr role="button">` has `@keydown.enter.prevent`. When focus is on the row's "试发" button and the user presses Enter or Space, the keydown bubbles up to the row and preventDefault cancels the button's activation. The row detail opens instead, so keyboard users can't trigger "试发". A button nested inside `role="button"` is also an accessibility violation.
- **Fix:** use `@keydown.enter.self.prevent` / `@keydown.space.self.prevent`, or make only the row number a button.

### Low

- **Thinktank streaming can hold a storage connection:** the `StreamingResponse` in `services/thinktank-service/app/knowledge/api/routes.py` has no `BackgroundTask`. If the client disconnects before streaming starts, the MinIO streamed response is never closed and holds a connection in the httpx pool until garbage collection.
- **Read-only setting lost on reconnect:** in `services/tender-service/app/core/source.py`, `ping(reconnect=True)` drops the session read-only setting. Instead, discard the connection on a failed ping, open a new one, and run `SET SESSION TRANSACTION READ ONLY` again.
- **Bulk hash lookup uses a pre-batch snapshot:** `services/policy-service/app/aitag/application/tagging.py`. If one row in a batch changes away from its old hash and a later row computes that old hash, the later row is wrongly skipped as a duplicate. That means fewer writes, not a rollback.
- **Connection pool is close to the limit:** pools default to 5+10, so about 10 processes plus the IAM side pool reach about 180 connections against `max_connections=200`. There's no budget table.
- **`manageable_ids` is N+1:** `services/iam-service/app/application/user_guard.py:47-58` queries each candidate's permissions separately, so the user list makes N queries per page.

## 4. Verified clean

- **Auth and security:** `cookie_secure` is enforced in production (inside IAM's own validator, so no name clash); `/login` checks Origin; CSRF uses `hmac.compare_digest`; unknown-user login failures are masked; a missing thinktank module level caps at NONE, so it fails closed; CSP has `frame-src 'self' blob:`; `.dockerignore` uses recursive `**/.env.*`; the gateway now depends on tender; the iam and audit workers have `init: true`.
- **Backend:** the scheduler job list fetches each job's latest run in one window-function query; the AI worker heartbeat is tied to the lock-holding connection; P2-4 parses large request bodies in a thread; the pagination COUNT-skip logic is correct.
- **Frontend:** `useCandidateExtras` calls `markShown` before the `setTimeout(0)` fallback toast fires; concurrent 403s reload the profile only once.
