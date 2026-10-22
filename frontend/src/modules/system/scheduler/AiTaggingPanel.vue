<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

import { aiTaggingOverview, listAiTaggingRuns, updateAiTaggingConfig, type AiTaggingOverview, type AiTaggingRun } from '@/api/aiTagging'
import { errorMessage } from '@/api/errors'
import { formatYuan, runStatusText, runStatusType } from './aiTagging'

/** 政策 AI 打标的设置、花费和每批明细。执行由上面的任务列表「立即执行」或每日计划触发。 */
const props = defineProps<{ canManage: boolean }>()
const overview = ref<AiTaggingOverview | null>(null)
const runs = ref<AiTaggingRun[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const saving = ref(false)
const loadError = ref('')
const form = reactive({
  type_prompt_id: '',
  interpret_prompt_id: '',
  opportunity_prompt_id: '',
  batch_size: 1000,
  content_max_chars: 15000,
  daily_cost_limit: '100',
  cursor_date: '',
  version: 1,
})
const config = computed(() => overview.value?.config)
const running = computed(() => runs.value.some(run => run.status === 'running'))
const STEPS = [
  { key: 'type_prompt_id', label: '政策类型判断', hint: '结果写入「政策基础标签」，信息化建设类标为需要解读' },
  { key: 'interpret_prompt_id', label: '政策解读', hint: '对需要解读的政策逐条解读，写入「政策解读列表」' },
  { key: 'opportunity_prompt_id', label: '政策市场机会', hint: '按解读出的行业场景补「政策市场机会」' },
] as const

async function load(quiet = false): Promise<void> {
  loading.value = !quiet
  try {
    const [data, history] = await Promise.all([aiTaggingOverview(), listAiTaggingRuns(page.value)])
    overview.value = data
    runs.value = history.items
    total.value = history.total
    if (!quiet || !saving.value) Object.assign(form, { ...data.config })
    loadError.value = ''
  } catch (error) {
    loadError.value = errorMessage(error, '政策 AI 打标设置加载失败')
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  saving.value = true
  try {
    await updateAiTaggingConfig({ ...form, daily_cost_limit: String(form.daily_cost_limit) })
    ElMessage.success('设置已保存，下一批按新设置执行')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败，请重试'))
  } finally {
    saving.value = false
  }
}

let timer: ReturnType<typeof setTimeout> | undefined
function poll(): void {
  timer = setTimeout(async () => {
    if (running.value && !document.hidden) await load(true)
    poll()
  }, 10_000)
}
onMounted(async () => { await load(); poll() })
onBeforeUnmount(() => clearTimeout(timer))

async function turnPage(next: number): Promise<void> {
  page.value = next
  await load(true)
}
</script>

<template>
  <section
    v-loading="loading"
    class="ai-tagging"
    aria-labelledby="ai-tagging-title"
  >
    <header class="ai-tagging__head">
      <div>
        <h2 id="ai-tagging-title">
          政策 AI 打标
        </h2>
        <p v-if="overview">
          今天已花 <strong>{{ formatYuan(overview.spent_today) }}</strong> / 每日上限 {{ formatYuan(overview.config.daily_cost_limit) }}
          · 本月 {{ formatYuan(overview.spent_month) }} · 读取进度：{{ config?.cursor_date }} {{ config?.cursor_content_id || '（当日第一条）' }}
        </p>
      </div>
      <el-button
        :icon="Refresh"
        @click="load()"
      >
        刷新
      </el-button>
    </header>
    <el-alert
      v-if="loadError || overview?.templates_error"
      :title="loadError || overview?.templates_error"
      type="error"
      :closable="false"
      show-icon
    />
    <el-form
      v-if="overview"
      class="ai-tagging__form"
      label-position="top"
      :disabled="!props.canManage || saving"
      @submit.prevent="save"
    >
      <el-form-item
        v-for="step in STEPS"
        :key="step.key"
        :label="`${step.label}模板`"
      >
        <el-select
          v-model="form[step.key]"
          clearable
          :placeholder="overview.templates.length ? '选择已上线的政策类模板' : '还没有已上线的政策类模板'"
        >
          <el-option
            v-for="item in overview.templates"
            :key="item.prompt_id"
            :label="`${item.title}（第 ${item.release_no} 版）`"
            :value="item.prompt_id"
          />
        </el-select>
        <span class="ai-tagging__hint">{{ step.hint }}</span>
      </el-form-item>
      <el-form-item label="每批打标条数">
        <el-input-number
          v-model="form.batch_size"
          :min="1"
          :max="20000"
          :step="100"
          controls-position="right"
        />
        <span class="ai-tagging__hint">一次执行读这么多条源政策；先用几十条试跑</span>
      </el-form-item>
      <el-form-item label="正文截取字数">
        <el-input-number
          v-model="form.content_max_chars"
          :min="500"
          :max="30000"
          :step="1000"
          controls-position="right"
        />
        <span class="ai-tagging__hint">正文是整页文字，超出部分不发给模型，控制费用</span>
      </el-form-item>
      <el-form-item label="每日费用上限（元）">
        <el-input
          v-model="form.daily_cost_limit"
          inputmode="decimal"
        />
        <span class="ai-tagging__hint">当天累计到上限就停，剩下的第二天接着打；按低优档计价</span>
      </el-form-item>
      <el-form-item label="从哪天的采集数据开始">
        <el-date-picker
          v-model="form.cursor_date"
          type="date"
          value-format="YYYY-MM-DD"
          :clearable="false"
        />
        <span class="ai-tagging__hint">改了就从这天第一条重新读；要补历史就往前调</span>
      </el-form-item>
      <div
        v-if="props.canManage"
        class="ai-tagging__actions"
      >
        <el-button
          type="primary"
          native-type="submit"
          :loading="saving"
        >
          保存设置
        </el-button>
      </div>
    </el-form>
    <el-table
      :data="runs"
      class="data-table"
      row-key="id"
      empty-text="还没有执行过"
    >
      <el-table-column
        prop="started_at"
        label="开始时间"
        width="170"
      />
      <el-table-column
        label="状态"
        width="90"
      >
        <template #default="{ row }">
          <el-tag
            :type="runStatusType(row.status)"
            size="small"
          >
            {{ runStatusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="source_rows"
        label="读取"
        width="70"
        align="right"
      />
      <el-table-column
        prop="tagged_rows"
        label="写入标签"
        width="90"
        align="right"
      />
      <el-table-column
        prop="type_failed"
        label="类型待人工"
        width="100"
        align="right"
      />
      <el-table-column
        prop="interpret_rows"
        label="解读行"
        width="80"
        align="right"
      />
      <el-table-column
        prop="interpret_failed"
        label="解读失败"
        width="90"
        align="right"
      />
      <el-table-column
        label="费用"
        width="100"
        align="right"
      >
        <template #default="{ row }">
          {{ formatYuan(row.cost) }}
        </template>
      </el-table-column>
      <el-table-column
        label="说明"
        min-width="320"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          {{ row.error_message || row.note || '—' }}
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-if="total > 10"
      class="ai-tagging__pager"
      layout="prev, pager, next, total"
      :total="total"
      :page-size="10"
      :current-page="page"
      @current-change="turnPage"
    />
  </section>
</template>

<style scoped>
.ai-tagging { margin-top: 16px; padding: 16px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); }
.ai-tagging__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.ai-tagging__head h2 { margin: 0 0 4px; font-size: 16px; }
.ai-tagging__head p { margin: 0; color: var(--zt-ink-500); font-size: 13px; }
.ai-tagging__form { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 0 16px; margin: 12px 0; }
.ai-tagging__form :deep(.el-select), .ai-tagging__form :deep(.el-input-number), .ai-tagging__form :deep(.el-date-editor) { width: 100%; }
.ai-tagging__hint { display: block; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }
.ai-tagging__actions { grid-column: 1 / -1; }
.ai-tagging__pager { margin-top: 12px; justify-content: flex-end; }
</style>
