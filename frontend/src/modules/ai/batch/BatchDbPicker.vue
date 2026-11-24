<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Download } from '@element-plus/icons-vue'

import { type PromptTemplate, type RunVersion } from '@/api/ai'
import { previewBatchRows, type BatchRowsPayload, type BatchRowsSummary } from '@/api/aiSamples'
import { getTaggingSamples, type AiTaskCode, type ContractTask } from '@/api/aiTagging'
import { errorMessage } from '@/api/errors'
import CodebookFilterSelect from '../shared/CodebookFilterSelect.vue'
import { guessTask } from '../prompts/taskFit'

/** 从政策库取到、检查过的数据，带上是给哪个模板、哪一版检查的：父组件据此丢掉过时的结果。 */
export interface DbLoaded { payload: BatchRowsPayload; summary: BatchRowsSummary; note: string; templateId: string; version: RunVersion }

/** 批量任务「从政策库取数」面板：按打标步骤和条件拉取 1～500 条并复用预检，结果不写回正式政策表。 */
const props = defineProps<{
  template: PromptTemplate
  version: RunVersion
  tasks: ContractTask[]
  provinces?: string[]
  industries?: string[]
  disabled: boolean
}>()
const emit = defineEmits<{
  loaded: [result: DbLoaded]
  error: [message: string]
  loading: [busy: boolean]
}>()

const HINTS: Record<AiTaskCode, string> = {
  type: '从外部源库按采集日期拉取政策，与「政策类型判断」定时任务口径一致。',
  interpret: '从「政策基础标签表」拉取含信息化建设类（需要解读）的政策。',
  opportunity: '从「政策解读列表」按「一级行业 + 一级场景」逐组展开（一组一行），提供 @【一级行业】、@【一级场景】、@【政策正文】 等列。',
  scenario: '从「新增场景审核」拉取待审场景与同行业已有场景。',
  enrich: '从码表拉取待补描述的新增场景。',
}
const yesterday = () => new Date(Date.now() - 86_400_000).toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const task = ref<AiTaskCode>('type')
const day = ref(yesterday())
const limit = ref(20)
const province = ref('')
const keyword = ref('')
const industryL1 = ref('')
const busy = ref(false)
const showProvince = computed(() => ['type', 'interpret', 'opportunity'].includes(task.value))
const showKeyword = computed(() => ['interpret', 'opportunity'].includes(task.value))
const columns = computed(() => props.tasks.find(item => item.code === task.value)?.columns ?? [])
const activeFields = computed(() => (props.version === 'release' && props.template.release
  ? props.template.release.fields
  : props.template.fields))
// 每次换模板、换版本、面板被卸载都作废在途的请求：慢的旧结果回来时不再交给父组件。
let token = 0

watch(() => props.template.id, () => {
  task.value = guessTask(props.tasks, activeFields.value)
  day.value = yesterday()
  province.value = ''
  keyword.value = ''
  industryL1.value = ''
}, { immediate: true })
watch(() => [props.version, props.tasks.length], () => {
  task.value = guessTask(props.tasks, activeFields.value)
})
watch(task, next => {
  if (!showProvince.value) province.value = ''
  if (!showKeyword.value) keyword.value = ''
  if (next !== 'opportunity') industryL1.value = ''
})
watch(() => [props.template.id, props.version], () => {
  token++
  busy.value = false
})
onBeforeUnmount(() => { token++ })

async function fetchAndPreview(): Promise<void> {
  if (busy.value || props.disabled) return
  const current = ++token
  const asked = { templateId: props.template.id, version: props.version }
  busy.value = true
  emit('loading', true)
  emit('error', '')
  try {
    const sample = await getTaggingSamples(task.value, day.value, limit.value, {
      province: province.value,
      keyword: keyword.value,
      industry_l1: industryL1.value,
    })
    if (current !== token) return
    const payload: BatchRowsPayload = { file_name: sample.file_name, headers: sample.headers, rows: sample.rows }
    const summary = await previewBatchRows(asked.templateId, asked.version, payload)
    if (current === token) emit('loaded', { payload, summary, note: sample.note, ...asked })
  } catch (error) {
    if (current === token) emit('error', errorMessage(error, '从政策库拉取数据失败，请调整条件后重试'))
  } finally {
    if (current === token) {
      busy.value = false
      emit('loading', false)
    }
  }
}
</script>

<template>
  <div class="db-pick">
    <div class="db-pick__radios">
      <el-radio-group
        v-model="task"
        size="small"
        :disabled="disabled || busy"
      >
        <el-radio-button
          v-for="item in tasks"
          :key="item.code"
          :value="item.code"
        >
          {{ item.name }}
        </el-radio-button>
      </el-radio-group>
    </div>
    <p class="db-pick__hint">
      {{ HINTS[task] }}
    </p>
    <div class="db-pick__fields">
      <label v-if="task === 'type'">
        <span>采集日期</span>
        <el-date-picker
          v-model="day"
          type="date"
          size="small"
          value-format="YYYY-MM-DD"
          :clearable="false"
          :disabled="disabled || busy"
          :disabled-date="(value: Date) => value.getTime() > Date.now()"
        />
      </label>
      <label>
        <span>抽取条数</span>
        <el-input-number
          v-model="limit"
          size="small"
          :min="1"
          :max="500"
          :disabled="disabled || busy"
          controls-position="right"
        />
      </label>
      <label v-if="showProvince">
        <span>省份（可选）</span>
        <CodebookFilterSelect
          v-model="province"
          size="small"
          :options="provinces"
          placeholder="搜索或选择省份"
          :disabled="disabled || busy"
        />
      </label>
      <label v-if="task === 'opportunity'">
        <span>一级行业（可选）</span>
        <CodebookFilterSelect
          v-model="industryL1"
          size="small"
          :options="industries"
          placeholder="搜索或选择一级行业"
          :disabled="disabled || busy"
        />
      </label>
      <label v-if="showKeyword">
        <span>政策关键词（可选）</span>
        <el-input
          v-model="keyword"
          size="small"
          placeholder="政策名称关键词"
          clearable
          :disabled="disabled || busy"
        />
      </label>
    </div>
    <div class="db-pick__bar">
      <el-button
        type="primary"
        plain
        :icon="Download"
        :loading="busy"
        :disabled="disabled"
        @click="fetchAndPreview"
      >
        拉取并检查数据
      </el-button>
      <span class="db-pick__cols">提供列：{{ columns.map(name => `@【${name}】`).join('、') }}</span>
    </div>
  </div>
</template>

<style scoped>
.db-pick { display: grid; gap: 10px; padding: 12px; border: 1px solid var(--zt-border); border-radius: 6px; background: var(--zt-surface-subtle); }
.db-pick__radios { display: flex; flex-wrap: wrap; }
.db-pick__hint { margin: 0; color: var(--zt-ink-700); font-size: 12px; line-height: 1.5; }
.db-pick__fields { display: flex; flex-wrap: wrap; gap: 8px 12px; }
.db-pick__fields label { display: flex; flex-direction: column; gap: 4px; color: var(--zt-ink-700); font-size: 12px; }
.db-pick__fields :deep(.el-date-editor), .db-pick__fields :deep(.el-input-number), .db-pick__fields :deep(.el-input), .db-pick__fields :deep(.el-select) { width: 150px; }
.db-pick__bar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; }
.db-pick__cols { flex: 1 1 200px; color: var(--zt-ink-500); font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
</style>
