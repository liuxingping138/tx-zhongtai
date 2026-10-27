<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'

import { getBatchRunRows, type BatchRun, type RunFileKind, type RunRows as Rows } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { RUN_SOURCE_TEXT, RUN_STATUS_TEXT, formatYuan, isActive, runModeText, runStatusType } from '../shared/aiText'
import RunRows from '../shared/RunRows.vue'
import { RUN_FILES, deleteRun, downloadRunFile, retryRun, stopRun } from './runActions'

/** 一个批量任务的详情：进度和费用、按哪一版跑的、逐行结果（前 50 行），以及发起时冻结的提示词。 */
const props = defineProps<{ run: BatchRun | null; canManage: boolean; canExport: boolean }>()
const emit = defineEmits<{ changed: []; close: [] }>()
const rows = ref<Rows | null>(null)
const rowsError = ref('')
const loadingRows = ref(false)
const failedOnly = ref(false)
const PROGRESS_RELOAD_MS = 10_000
let sequence = 0
let loadedAt = 0
let loadedFailed = 0

const open = computed({ get: () => props.run !== null, set: value => { if (!value) emit('close') } })
const run = computed(() => props.run)
const failedText = computed(() => {
  const current = run.value
  if (!current?.failed_count) return '无'
  return `${current.failed_count} 条${current.format_failed_count ? `（格式不对 ${current.format_failed_count}）` : ''}`
})

async function loadRows(): Promise<void> {
  const current = run.value
  if (!current) return
  const ticket = ++sequence
  loadingRows.value = true
  loadedAt = Date.now()
  loadedFailed = current.failed_count
  try {
    const data = await getBatchRunRows(current.id, failedOnly.value)
    if (ticket === sequence) { rows.value = data; rowsError.value = '' }
  } catch (error) {
    if (ticket === sequence) { rows.value = null; rowsError.value = errorMessage(error, '结果加载失败，请重试') }
  } finally {
    if (ticket === sequence) loadingRows.value = false
  }
}

// 换任务从头看；同一个任务跑完、停止、重跑（状态变了）或切换「只看失败」马上重读。
// 换任务时状态也跟着变，只认同一个任务，否则一打开就读两次。
watch(() => run.value?.id, () => { failedOnly.value = false; rows.value = null; rowsError.value = ''; void loadRows() })
watch(() => [run.value?.id, run.value?.status, failedOnly.value], (next, previous) => {
  if (run.value && next[0] === previous[0] && next.join() !== previous.join()) void loadRows()
})
// 跑着的任务列表每 2 秒刷新一次进度，逐行结果不跟着每次重读：这里只列前 50 行，这几行都有结果了，
// 再往后跑也不变；只看失败时跟着失败数走。至少隔 10 秒读一次，几十万行的任务读结果文件不便宜。
watch(() => run.value?.done_count, () => {
  const current = run.value
  if (!current || loadingRows.value || Date.now() - loadedAt < PROGRESS_RELOAD_MS) return
  const stale = failedOnly.value
    ? current.failed_count !== loadedFailed
    : rows.value?.items.some(item => item.status === 'pending') ?? true
  if (stale) void loadRows()
})

async function act(action: (current: BatchRun) => Promise<boolean>, close = false): Promise<void> {
  const current = run.value
  if (!current || !await action(current)) return
  emit('changed')
  if (close) emit('close')
}
</script>

<template>
  <el-drawer
    v-model="open"
    :title="run ? run.prompt_title : ''"
    size="min(760px, 100vw)"
    class="editor-overlay run-detail"
  >
    <template v-if="run">
      <div class="run-detail__status">
        <el-tag :type="runStatusType(run.status)">
          {{ RUN_STATUS_TEXT[run.status] }}
        </el-tag>
        <strong>{{ run.done_count }}/{{ run.total_count || '?' }} 条</strong>
        <span>{{ run.percent }}%</span>
        <span class="run-detail__spacer" />
        <el-dropdown
          v-if="canExport && Object.values(run.files).some(Boolean)"
          trigger="click"
          @command="(kind: RunFileKind) => downloadRunFile(run!, kind)"
        >
          <el-button size="small">
            下载<el-icon class="el-icon--right">
              <ArrowDown />
            </el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="file in RUN_FILES.filter(item => run!.files[item.kind])"
                :key="file.kind"
                :command="file.kind"
              >
                {{ file.label }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <template v-if="canManage">
          <el-button
            v-if="run.can_stop"
            size="small"
            :disabled="run.status === 'stopping'"
            @click="act(stopRun)"
          >
            停止
          </el-button>
          <el-button
            v-if="run.can_retry"
            size="small"
            type="primary"
            plain
            @click="act(retryRun)"
          >
            重跑失败的 {{ run.pending_count }} 条
          </el-button>
          <el-button
            v-if="run.can_delete"
            size="small"
            text
            type="danger"
            @click="act(deleteRun, true)"
          >
            删除
          </el-button>
        </template>
      </div>
      <el-progress
        v-if="isActive(run.status)"
        :percentage="run.percent"
        :show-text="false"
        :stroke-width="4"
      />
      <el-alert
        v-if="run.error_message"
        class="run-detail__error"
        :title="run.error_message"
        type="error"
        :closable="false"
        show-icon
      />

      <dl class="run-detail__facts">
        <dt>模板版本</dt><dd>{{ run.release_no ? `第 ${run.release_no} 版` : '发起时的草稿' }}</dd>
        <dt>来源</dt><dd>{{ RUN_SOURCE_TEXT[run.source as 'manual' | 'pipeline'] ?? '页面发起' }}</dd>
        <dt>输入文件</dt><dd>{{ run.input_name || '—' }}</dd>
        <dt>运行范围</dt><dd>{{ runModeText(run) }}</dd>
        <dt>模型</dt><dd>{{ run.model_name }}{{ run.thinking ? '（深度思考）' : '' }}</dd>
        <dt>失败</dt><dd :class="{ 'is-bad': run.failed_count }">
          {{ failedText }}
        </dd>
        <dt>费用</dt><dd>{{ formatYuan(run.inference_cost + run.search_cost) }} · {{ run.total_tokens_kilo.toFixed(3) }} 千 token</dd>
        <dt>发起</dt><dd>{{ run.created_by_name }} · {{ run.created_at }}</dd>
        <dt>结束</dt><dd>{{ run.finished_at || '—' }}</dd>
      </dl>

      <section class="run-detail__section">
        <h3>逐行结果</h3>
        <p
          v-if="rowsError"
          class="run-detail__muted"
        >
          {{ rowsError }}
        </p>
        <RunRows
          v-else
          v-model:failed-only="failedOnly"
          :rows="rows"
          :loading="loadingRows"
          empty="还没有跑完的行"
        />
      </section>

      <section class="run-detail__section">
        <details>
          <summary>发起时冻结的提示词和输出字段</summary>
          <p class="run-detail__muted">
            之后再改模板、重新上线，都不影响这个任务和它的重跑。
          </p>
          <p class="run-detail__fields">
            输出字段：{{ run.output_fields.split('|').filter(Boolean).join('、') || '未设置' }}
          </p>
          <pre>{{ run.prompt_content }}</pre>
        </details>
      </section>
    </template>
  </el-drawer>
</template>

<style scoped>
.run-detail__status { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; font-variant-numeric: tabular-nums; }
.run-detail__status .el-button { margin: 0; }
.run-detail__status span { color: var(--zt-ink-500); font-size: 13px; }
.run-detail__spacer { flex: 1; }
.run-detail .el-progress { margin-top: 10px; }
.run-detail__error { margin-top: 12px; }
.run-detail__facts { display: grid; grid-template-columns: 72px minmax(0, 1fr) 72px minmax(0, 1fr); gap: 10px 12px; margin: 16px 0 0; padding: 14px 16px; border-radius: 6px; background: var(--zt-soft); font-size: 13px; }
.run-detail__facts dt { color: var(--zt-ink-500); }
.run-detail__facts dd { margin: 0; overflow-wrap: anywhere; }
.run-detail__facts dd.is-bad { color: var(--el-color-danger); }
.run-detail__section { margin-top: 20px; }
.run-detail__section h3 { margin: 0 0 10px; color: var(--zt-ink-900); font-size: 14px; font-weight: 650; }
.run-detail__section summary { color: var(--zt-blue-600); font-size: 13px; cursor: pointer; }
.run-detail__muted { margin: 8px 0; color: var(--zt-ink-500); font-size: 13px; }
.run-detail__fields { margin: 0 0 8px; color: var(--zt-ink-700); font-size: 13px; }
.run-detail pre { max-height: 50vh; overflow: auto; margin: 0; padding: 12px; border-radius: 6px; background: var(--zt-soft); font: inherit; font-size: 13px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 720px) { .run-detail__facts { grid-template-columns: 72px minmax(0, 1fr); } }
</style>
