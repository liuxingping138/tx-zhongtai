<script setup lang="ts">
import { ref } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'

import type { BatchRun, RunFileKind } from '@/api/ai'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { RUN_SOURCE_TEXT, RUN_STATUS_TEXT, formatYuan, isActive, roundText, runModeText } from '../shared/aiText'
import { shortTime, versionLabel } from '../prompts/sampleView'
import { RUN_FILES, deleteRun, downloadRunFile, retryRun, runAllRun, stopRun } from './runActions'

/** 批量任务列表。点一行看详情（逐行结果、冻结的提示词）；常用的下载、停止、重跑、删除也留在操作列。 */
const props = defineProps<{
  items: BatchRun[]
  total: number
  loading: boolean
  canRun: boolean
  canExport: boolean
  filtered: boolean
  /** 能编辑的模板类型：停止、重跑、删除都按任务所属类型判断 */
  editableCategories: string[]
}>()
const canManage = (run: BatchRun) => props.canRun && props.editableCategories.includes(run.prompt_category)
const hasFiles = (run: BatchRun) => props.canExport && Object.values(run.files).some(Boolean)
const hasMoreActions = (run: BatchRun) => canManage(run) && (run.can_retry || run.can_run_all || run.can_delete)
const page = defineModel<number>('page', { required: true })
const emit = defineEmits<{ changed: []; open: [run: BatchRun] }>()
const busyId = ref('')

type MoreCommand = 'retry' | 'runAll' | 'delete'

function runMoreCommand(run: BatchRun, command: MoreCommand): void {
  if (command === 'retry') void act(retryRun, run)
  else if (command === 'runAll') void act(runAllRun, run)
  else if (command === 'delete') void act(deleteRun, run)
}

async function act(action: (run: BatchRun) => Promise<boolean>, run: BatchRun): Promise<void> {
  if (busyId.value) return
  busyId.value = run.id
  try {
    if (await action(run)) emit('changed')
  } finally {
    busyId.value = ''
  }
}

function statusTone(run: BatchRun): 'running' | 'done' | 'warn' | 'muted' {
  if (isActive(run.status)) return 'running'
  if (run.status === 'cancelled') return 'muted'
  return run.failed_count > 0 ? 'warn' : 'done'
}

function statusTooltip(run: BatchRun): string {
  const parts = [`${RUN_STATUS_TEXT[run.status]} ${run.done_count}/${run.total_count || '?'}`]
  if (run.failed_count) {
    const formats = run.format_failed_count ? `（格式不对 ${run.format_failed_count}）` : ''
    parts.push(`失败 ${run.failed_count}${formats}`)
  }
  const round = roundText(run)
  if (round) parts.push(round)
  if (run.error_message) parts.push(run.error_message)
  return parts.join(' · ')
}
</script>

<template>
  <div class="history">
    <TableSkeleton
      v-if="loading && items.length === 0"
      :columns="7"
      :has-actions="true"
    />
    <el-table
      v-else
      :data="items"
      row-key="id"
      class="data-table history__table"
      :class="{ 'is-refreshing': loading }"
      :empty-text="filtered ? '没有符合条件的任务' : '还没有批量任务'"
      height="100%"
      @row-click="(row: BatchRun) => emit('open', row)"
    >
      <el-table-column
        label="发起时间"
        width="108"
      >
        <template #default="{ row }">
          <span
            class="history__time"
            :title="row.created_at"
          >{{ shortTime(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="prompt_title"
        label="模板名称"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column
        label="状态"
        width="216"
      >
        <template #default="{ row }">
          <div
            class="history__status-wrap"
            :title="statusTooltip(row)"
          >
            <div class="history__status">
              <span
                class="history__badge"
                :class="`is-${statusTone(row)}`"
              >{{ RUN_STATUS_TEXT[row.status as BatchRun['status']] }}</span>
              <span class="history__metrics">
                <span>{{ row.done_count }}/{{ row.total_count || '?' }}</span><span
                  v-if="row.failed_count"
                  class="history__failed"
                >，失败 {{ row.failed_count }}</span>
              </span>
              <span
                v-if="row.retry_round > 1"
                class="history__round-pill"
              >{{ row.retry_round }}轮</span>
            </div>
            <div
              v-if="isActive(row.status)"
              class="history__bar"
            >
              <span :style="{ width: `${row.percent}%` }" />
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        label="跑的版本"
        width="136"
      >
        <template #default="{ row }">
          <span
            class="history__version"
            :class="{ 'is-draft': row.release_no === null && row.draft_saved_at }"
          >{{ versionLabel(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column
        label="来源"
        width="84"
      >
        <template #default="{ row }">
          {{ RUN_SOURCE_TEXT[row.source as 'manual' | 'pipeline'] ?? '页面发起' }}
        </template>
      </el-table-column>
      <el-table-column
        label="输入文件"
        min-width="136"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          {{ row.input_name || '—' }}
        </template>
      </el-table-column>
      <el-table-column
        label="运行范围"
        width="84"
      >
        <template #default="{ row }">
          {{ runModeText(row) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="model_name"
        label="模型"
        min-width="144"
        show-overflow-tooltip
      />
      <el-table-column
        label="总消耗(千token)"
        width="116"
        align="right"
      >
        <template #default="{ row }">
          {{ row.total_tokens_kilo.toFixed(3) }}
        </template>
      </el-table-column>
      <el-table-column
        label="推理费用"
        width="88"
        align="right"
      >
        <template #default="{ row }">
          {{ formatYuan(row.inference_cost) }}
        </template>
      </el-table-column>
      <el-table-column
        label="联网费用"
        width="88"
        align="right"
      >
        <template #default="{ row }">
          {{ formatYuan(row.search_cost) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="created_by_name"
        label="发起人"
        width="96"
        show-overflow-tooltip
      />
      <el-table-column
        label="操作"
        width="212"
        fixed="right"
      >
        <template #default="{ row }">
          <!-- 行末最多 3 个等高胶囊：详情、下载、停止/更多，避免一排 5 个按钮过宽且参差不齐 -->
          <div
            class="row-actions"
            @click.stop
          >
            <button
              type="button"
              class="row-action"
              @click="emit('open', row)"
            >
              详情
            </button>
            <el-dropdown
              v-if="hasFiles(row)"
              trigger="click"
              @command="(kind: RunFileKind) => downloadRunFile(row, kind)"
            >
              <button
                type="button"
                class="row-action"
              >
                下载<el-icon class="history__arrow">
                  <ArrowDown />
                </el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="file in RUN_FILES.filter(item => row.files[item.kind])"
                    :key="file.kind"
                    :command="file.kind"
                  >
                    {{ file.label }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <button
              v-if="canManage(row) && row.can_stop"
              type="button"
              class="row-action row-action--primary"
              :disabled="busyId === row.id || row.status === 'stopping'"
              @click="act(stopRun, row)"
            >
              停止
            </button>
            <el-dropdown
              v-if="hasMoreActions(row)"
              trigger="click"
              @command="(command: MoreCommand) => runMoreCommand(row, command)"
            >
              <button
                type="button"
                class="row-action"
                :disabled="busyId === row.id"
              >
                更多<el-icon class="history__arrow">
                  <ArrowDown />
                </el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-if="row.can_retry"
                    command="retry"
                    :title="`重新提问失败和没跑到的 ${row.pending_count} 条`"
                  >
                    重跑失败
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-if="row.can_run_all"
                    command="runAll"
                    title="这次只跑了前几行：用同一份数据、同一版提示词跑全部"
                  >
                    跑全部
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-if="row.can_delete"
                    command="delete"
                    :divided="row.can_retry || row.can_run_all"
                  >
                    删除
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-model:current-page="page"
      class="history__pager"
      layout="total, prev, pager, next"
      :page-size="15"
      :total="total"
      hide-on-single-page
    />
  </div>
</template>

<style scoped>
.history { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.history__table { flex: 1; min-height: 0; }
.history__table :deep(.el-table__row) { cursor: pointer; }
/* 和业务列表一样左右各 12px：标准表格的 16px 会把「总消耗(千token)」表头、「草稿 11-03 17:20」挤成两行 */
.history__table :deep(.cell) { padding: 0 12px; }
.history__status-wrap { position: relative; display: flex; align-items: center; }
.history__status { display: flex; align-items: center; gap: 8px; width: 100%; min-width: 0; font-size: 13px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.history__badge { display: inline-flex; align-items: center; gap: 6px; flex: none; color: var(--zt-ink-900); font-weight: 500; }
.history__badge::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--zt-muted-mark); }
.history__badge.is-done::before { background: var(--zt-success); }
.history__badge.is-warn::before { background: var(--zt-warning); }
.history__badge.is-running { color: var(--zt-blue-600); }
.history__badge.is-running::before { background: var(--zt-blue-600); }
.history__badge.is-danger { color: var(--zt-danger-text); }
.history__badge.is-danger::before { background: var(--zt-danger-text); }
.history__badge.is-muted { color: var(--zt-ink-500); }
.history__metrics { min-width: 0; overflow: hidden; text-overflow: ellipsis; color: var(--zt-ink-700); }
.history__failed { color: var(--zt-danger-text); font-weight: 500; }
.history__round-pill { flex: none; padding: 1px 6px; border-radius: 999px; background: var(--zt-surface-subtle); color: var(--zt-ink-500); font-size: 11px; line-height: 1.4; }
.history__bar { position: absolute; left: 0; right: 0; bottom: -5px; height: 2px; border-radius: 999px; background: var(--zt-surface-subtle); overflow: hidden; }
.history__bar span { display: block; height: 100%; background: var(--zt-blue-600); transition: width 0.25s ease; }
.history__time { font-variant-numeric: tabular-nums; white-space: nowrap; }
.history__pager { justify-content: flex-end; padding: 10px 16px; }
.history__version { color: var(--zt-blue-700); font-variant-numeric: tabular-nums; white-space: nowrap; }
.history__version.is-draft { color: var(--zt-ink-700); }
.history__arrow { font-size: 11px; }
</style>
