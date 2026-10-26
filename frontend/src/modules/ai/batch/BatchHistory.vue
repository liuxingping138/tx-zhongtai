<script setup lang="ts">
import { ArrowDown } from '@element-plus/icons-vue'

import type { BatchRun, RunFileKind } from '@/api/ai'
import { RUN_SOURCE_TEXT, RUN_STATUS_TEXT, formatYuan, isActive, runModeText, runStatusType } from '../shared/aiText'
import { RUN_FILES, deleteRun, downloadRunFile, retryRun, stopRun } from './runActions'

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
const page = defineModel<number>('page', { required: true })
const emit = defineEmits<{ changed: []; open: [run: BatchRun] }>()

async function act(action: (run: BatchRun) => Promise<boolean>, run: BatchRun): Promise<void> {
  if (await action(run)) emit('changed')
}

function progressText(run: BatchRun): string {
  const formats = run.format_failed_count ? `（格式不对 ${run.format_failed_count}）` : ''
  const failed = run.failed_count ? `，失败 ${run.failed_count}${formats}` : ''
  return `${run.done_count}/${run.total_count || '?'}${failed}`
}
</script>

<template>
  <div class="history">
    <el-table
      v-loading="loading"
      :data="items"
      row-key="id"
      class="history__table"
      :empty-text="filtered ? '没有符合条件的任务' : '还没有批量任务'"
      height="100%"
      @row-click="(row: BatchRun) => emit('open', row)"
    >
      <el-table-column
        prop="created_at"
        label="发起时间"
        width="176"
      />
      <el-table-column
        prop="prompt_title"
        label="模板名称"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column
        label="状态"
        width="200"
      >
        <template #default="{ row }">
          <div class="history__status">
            <el-tag
              :type="runStatusType(row.status)"
              size="small"
            >
              {{ RUN_STATUS_TEXT[row.status as BatchRun['status']] }}
            </el-tag>
            <span>{{ progressText(row) }}</span>
          </div>
          <el-progress
            v-if="isActive(row.status)"
            :percentage="row.percent"
            :show-text="false"
            :stroke-width="4"
          />
          <p
            v-if="row.error_message"
            class="history__error"
            :title="row.error_message"
          >
            {{ row.error_message }}
          </p>
        </template>
      </el-table-column>
      <el-table-column
        label="版本"
        width="80"
      >
        <template #default="{ row }">
          {{ row.release_no ? `第 ${row.release_no} 版` : '—' }}
        </template>
      </el-table-column>
      <el-table-column
        label="来源"
        width="90"
      >
        <template #default="{ row }">
          {{ RUN_SOURCE_TEXT[row.source as 'manual' | 'pipeline'] ?? '页面发起' }}
        </template>
      </el-table-column>
      <el-table-column
        label="输入文件"
        min-width="160"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          {{ row.input_name || '—' }}
        </template>
      </el-table-column>
      <el-table-column
        label="运行范围"
        width="90"
      >
        <template #default="{ row }">
          {{ runModeText(row) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="model_name"
        label="模型"
        min-width="150"
        show-overflow-tooltip
      />
      <el-table-column
        label="总消耗(千token)"
        width="124"
        align="right"
      >
        <template #default="{ row }">
          {{ row.total_tokens_kilo.toFixed(3) }}
        </template>
      </el-table-column>
      <el-table-column
        label="推理费用"
        width="96"
        align="right"
      >
        <template #default="{ row }">
          {{ formatYuan(row.inference_cost) }}
        </template>
      </el-table-column>
      <el-table-column
        label="联网费用"
        width="96"
        align="right"
      >
        <template #default="{ row }">
          {{ formatYuan(row.search_cost) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="created_by_name"
        label="发起人"
        width="120"
        show-overflow-tooltip
      />
      <el-table-column
        label="操作"
        width="232"
        fixed="right"
      >
        <template #default="{ row }">
          <div
            class="history__ops"
            @click.stop
          >
            <el-button
              link
              type="primary"
              @click="emit('open', row)"
            >
              详情
            </el-button>
            <el-dropdown
              v-if="canExport && Object.values(row.files).some(Boolean)"
              trigger="click"
              @command="(kind: RunFileKind) => downloadRunFile(row, kind)"
            >
              <el-button
                link
                type="primary"
              >
                下载<el-icon class="el-icon--right">
                  <ArrowDown />
                </el-icon>
              </el-button>
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
            <el-button
              v-if="canManage(row) && row.can_stop"
              link
              type="warning"
              :disabled="row.status === 'stopping'"
              @click="act(stopRun, row)"
            >
              停止
            </el-button>
            <el-button
              v-if="canManage(row) && row.can_retry"
              link
              type="primary"
              :title="`重新提问失败和没跑到的 ${row.pending_count} 条`"
              @click="act(retryRun, row)"
            >
              重跑失败
            </el-button>
            <el-button
              v-if="canManage(row) && row.can_delete"
              link
              type="danger"
              @click="act(deleteRun, row)"
            >
              删除
            </el-button>
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
.history__status { display: flex; align-items: center; gap: 8px; font-variant-numeric: tabular-nums; font-size: 13px; }
.history__status + .el-progress { margin-top: 6px; }
.history__error { margin: 4px 0 0; color: var(--el-color-danger); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history__ops { display: flex; align-items: center; gap: 10px; }
.history__ops .el-button { margin: 0; }
.history__pager { justify-content: flex-end; padding: 10px 16px; }
</style>
