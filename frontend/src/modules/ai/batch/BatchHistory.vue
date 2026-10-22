<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'

import { deleteBatchRun, retryBatchRun, stopBatchRun, type BatchRun, type RunFileKind } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { RUN_MODE_TEXT, RUN_STATUS_TEXT, formatYuan, isActive, runStatusType } from '../shared/aiText'
import { downloadBatchFile } from '../shared/downloads'

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
const emit = defineEmits<{ changed: [] }>()
const viewing = ref<BatchRun | null>(null)

const FILES: { kind: RunFileKind; label: string }[] = [
  { kind: 'result', label: '结果 Excel' },
  { kind: 'raw', label: '原始返回 CSV' },
  { kind: 'failed', label: '失败清单' },
  { kind: 'log', label: '运行日志' },
]
const FILE_NAMES: Record<RunFileKind, string> = { result: '结果.xlsx', raw: '原始返回.csv', failed: '失败清单.csv', log: '运行日志.log' }

async function download(run: BatchRun, kind: RunFileKind): Promise<void> {
  try {
    await downloadBatchFile(run.id, kind, `${run.prompt_title}-${FILE_NAMES[kind]}`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败，请重试'))
  }
}

async function stop(run: BatchRun): Promise<void> {
  const ok = await ElMessageBox.confirm('已完成的行会保留并生成结果，进行中的请求返回后停止。', '停止这个任务？', {
    type: 'warning', confirmButtonText: '停止', cancelButtonText: '继续运行',
  }).then(() => true, () => false)
  if (!ok) return
  try {
    await stopBatchRun(run.id)
    emit('changed')
  } catch (error) {
    ElMessage.error(errorMessage(error, '停止失败，请重试'))
  }
}

async function remove(run: BatchRun): Promise<void> {
  const ok = await ElMessageBox.confirm('记录和结果文件都会删除，不能恢复。', '删除这条记录？', {
    type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
  }).then(() => true, () => false)
  if (!ok) return
  try {
    await deleteBatchRun(run.id)
    emit('changed')
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败，请重试'))
  }
}

async function retry(run: BatchRun): Promise<void> {
  const parts = [
    run.failed_count ? `失败 ${run.failed_count} 条` : '',
    run.total_count > run.done_count ? `没跑到 ${run.total_count - run.done_count} 条` : '',
  ].filter(Boolean).join('、')
  const message = `将用「${run.model_name}」重新提问 ${run.pending_count} 条（${parts}），会产生模型费用。已成功的行保留，结果合并回这条记录。`
  const ok = await ElMessageBox.confirm(message, '重跑失败的行？', {
    type: 'warning', confirmButtonText: '开始重跑', cancelButtonText: '取消',
  }).then(() => true, () => false)
  if (!ok) return
  try {
    await retryBatchRun(run.id)
    ElMessage.success(`已加入队列，重跑 ${run.pending_count} 条`)
    emit('changed')
  } catch (error) {
    ElMessage.error(errorMessage(error, '重跑失败，请重试'))
  }
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
      :empty-text="filtered ? '没有符合条件的记录' : '还没有批量提问记录'"
      height="100%"
    >
      <el-table-column
        prop="created_at"
        label="发起时间"
        width="160"
      />
      <el-table-column
        prop="prompt_category_name"
        label="类型"
        width="80"
      />
      <el-table-column
        prop="prompt_title"
        label="提问标题"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column
        prop="model_name"
        label="模型"
        min-width="150"
        show-overflow-tooltip
      />
      <el-table-column
        label="运行方式"
        width="100"
      >
        <template #default="{ row }">
          <el-tag
            :type="row.run_mode === 'test' ? 'info' : 'primary'"
            effect="plain"
            size="small"
          >
            {{ row.run_mode === 'test' ? `测试 ${row.row_limit} 条` : RUN_MODE_TEXT.all }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        label="状态"
        width="220"
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
        width="96"
        show-overflow-tooltip
      />
      <el-table-column
        label="操作"
        width="250"
        fixed="right"
      >
        <template #default="{ row }">
          <div class="history__ops">
            <el-button
              link
              type="primary"
              @click="viewing = row"
            >
              内容
            </el-button>
            <el-dropdown
              v-if="canExport && Object.values(row.files).some(Boolean)"
              trigger="click"
              @command="(kind: RunFileKind) => download(row, kind)"
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
                    v-for="file in FILES.filter(item => row.files[item.kind])"
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
              @click="stop(row)"
            >
              停止
            </el-button>
            <el-button
              v-if="canManage(row) && row.can_retry"
              link
              type="primary"
              :title="`重新提问失败和没跑到的 ${row.pending_count} 条`"
              @click="retry(row)"
            >
              重跑失败
            </el-button>
            <el-button
              v-if="canManage(row) && row.can_delete"
              link
              type="danger"
              @click="remove(row)"
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
    <el-dialog
      :model-value="viewing !== null"
      :title="viewing ? `${viewing.prompt_title} · 发起时的提示词` : ''"
      width="720px"
      @close="viewing = null"
    >
      <p
        v-if="viewing?.output_fields"
        class="history__fields"
      >
        输出字段：{{ viewing.output_fields }}
      </p>
      <pre class="history__content">{{ viewing?.prompt_content }}</pre>
    </el-dialog>
  </div>
</template>

<style scoped>
.history { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.history__table { flex: 1; min-height: 0; }
.history__status { display: flex; align-items: center; gap: 8px; font-variant-numeric: tabular-nums; font-size: 13px; }
.history__status + .el-progress { margin-top: 6px; }
.history__error { margin: 4px 0 0; color: var(--el-color-danger); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history__ops { display: flex; align-items: center; gap: 10px; }
.history__ops .el-button { margin: 0; }
.history__pager { justify-content: flex-end; padding: 10px 16px; }
.history__fields { margin: 0 0 8px; color: var(--zt-ink-700); font-size: 13px; }
.history__content { max-height: 60vh; overflow: auto; margin: 0; padding: 12px; border-radius: 6px; background: var(--zt-soft); font: inherit; font-size: 13px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
</style>
