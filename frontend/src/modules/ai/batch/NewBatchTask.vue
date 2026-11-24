<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { missingFieldsWarning } from '../shared/outputFields'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheckFilled, Download, Upload } from '@element-plus/icons-vue'

import { previewBatchInput, startBatchRun, type AiModel, type PromptTemplate, type RunVersion } from '@/api/ai'
import { startBatchRunFromRows, type BatchRowsPayload, type BatchRowsSummary } from '@/api/aiSamples'
import { errorMessage } from '@/api/errors'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { estimateCost } from '../prompts/sampleView'
import { formatYuan } from '../shared/aiText'
import { downloadBatchInputTemplate } from '../shared/downloads'
import BatchDbPicker, { type DbLoaded } from './BatchDbPicker.vue'
import BatchVersionPick from './BatchVersionPick.vue'
import { confirmedLabel, defaultVersion, runSpec } from './batchVersion'
import { useSampleTasks } from './useSampleTasks'

/**
 * 新建批量任务：选模板和跑哪一版（线上版本或当前草稿），上传 Excel 或从政策库取数，选跑全部还是先跑几条。
 * 发起时把这一版的提示词、输出字段、模型和码表冻结进任务，之后改模板、上线新版本都不影响它；模板的测试样本不参与。
 */
const props = defineProps<{ templates: PromptTemplate[]; models: AiModel[] }>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ created: [] }>()
const templateId = ref('')
const version = ref<RunVersion>('release')
const thinking = ref(false)
const inputMode = ref<'upload' | 'db'>('upload')
const file = ref<File | null>(null)
const dbPayload = ref<BatchRowsPayload | null>(null)
const dbNote = ref('')
const summary = ref<BatchRowsSummary | null>(null)
const { tasks: sampleTasks, provinces: sampleProvinces, industries: sampleIndustries, ensure: ensureContract } = useSampleTasks()
const testRowsMax = computed(() => (summary.value ? Math.max(summary.value.rows - 1, 1) : 100000)) // 输入框按它做 key：Element Plus 只在挂载时写 aria-valuemax
const previewing = ref(false)
const downloading = ref(false)
const starting = ref(false)
const failure = ref('')
const scope = ref<'all' | 'test'>('all')
const testRows = ref(10)
const picker = ref<HTMLInputElement>()
let sequence = 0

const template = computed(() => props.templates.find(item => item.id === templateId.value))
const canPickFromDb = computed(() => template.value?.category === 'policy' && sampleTasks.value.length > 0)
const spec = computed(() => runSpec(template.value, version.value, props.models))
const model = computed(() => spec.value?.model)
/** 没选模板时「跑哪一版」那步不显示，后面的步骤号跟着往前挪，不跳号。 */
const stepNo = (step: number) => (spec.value ? step : step - 1)
const uploadHint = computed(() => (spec.value?.columns.length
  ? '先下载数据模板，表头就是这一版要的列，不要改名；每行填一条数据，可以加别的列，会原样留在结果里。选好后先检查列，不会调用模型。'
  : '第一行是表头，每行问一次。选好后先检查列，不会调用模型。'))
const count = computed(() => (scope.value === 'test' ? Math.min(testRows.value || 1, summary.value?.rows ?? 0) : summary.value?.rows ?? 0))
// 样本试跑跑的是草稿：跑上线版本时只有草稿和线上一样才拿它估。
const draftMatchesRun = computed(() => version.value === 'draft' || !template.value?.release?.unreleased_changes.length)
const estimate = computed(() => (summary.value
  ? estimateCost(template.value?.sample, count.value, {
      thinking: thinking.value && Boolean(model.value?.supports_thinking),
      draftMatchesRun: draftMatchesRun.value,
    })
  : null))
const noFields = computed(() => (spec.value ? missingFieldsWarning(spec.value.content, spec.value.fields) : ''))
const hasData = computed(() => Boolean(summary.value && (file.value || dbPayload.value)))
const blocker = computed(() => {
  if (!template.value || !spec.value) return '选一个模板'
  if (spec.value.problem) return spec.value.problem
  if (previewing.value) return '正在检查数据…'
  if (!hasData.value) return inputMode.value === 'db' ? '先从政策库拉取并检查数据' : '上传这次要跑的数据'
  return ''
})

function clearData(): void {
  sequence++
  file.value = null
  dbPayload.value = null
  dbNote.value = ''
  summary.value = null
  failure.value = ''
  previewing.value = false
}

watch(open, value => {
  clearData()
  if (!value) return
  templateId.value = ''
  thinking.value = false
  inputMode.value = 'upload'
  scope.value = 'all'
  testRows.value = 10
  void ensureContract()
}, { flush: 'sync' })
// 只选了模板不算没保存的工作；选好的数据丢了要重新找，离开前提醒。
useUnsavedForm(open, () => file.value?.name ?? dbPayload.value?.file_name ?? '', starting)
watch(templateId, () => {
  version.value = defaultVersion(template.value)
  if (template.value?.category !== 'policy') inputMode.value = 'upload'
})
// 换了模板、版本或数据来源，要的列可能不同：已选的数据要重新检查。
watch([templateId, version, inputMode], clearData)

function onDbLoaded(result: DbLoaded): void {
  // 慢的旧结果：检查它时的模板、版本已经换了，或者已经切回上传，丢掉（面板自己也会作废在途请求）。
  if (inputMode.value !== 'db' || result.templateId !== templateId.value || result.version !== version.value) return
  file.value = null
  dbPayload.value = result.payload
  dbNote.value = result.note
  summary.value = result.summary
  failure.value = ''
  testRows.value = Math.max(Math.min(10, result.summary.rows - 1), 1)
  if (result.summary.rows <= 1) scope.value = 'all'
}

async function pick(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const chosen = input.files?.[0]
  input.value = ''
  if (!chosen || !template.value) return
  const current = ++sequence
  file.value = null
  summary.value = null
  failure.value = ''
  previewing.value = true
  try {
    const result = await previewBatchInput(template.value.id, version.value, chosen)
    if (current !== sequence) return
    file.value = chosen
    summary.value = result
    testRows.value = Math.max(Math.min(10, result.rows - 1), 1)
    if (result.rows <= 1) scope.value = 'all'
  } catch (error) {
    if (current === sequence) failure.value = errorMessage(error, '这份数据没通过检查，请换一个文件')
  } finally {
    if (current === sequence) previewing.value = false
  }
}

/** 表头就是这一版要的列：照着填好再传，不用对着页面上的列名自己建表。 */
async function downloadTemplate(): Promise<void> {
  if (!template.value || !spec.value || downloading.value) return
  downloading.value = true
  try {
    const label = version.value === 'draft' ? '草稿' : spec.value.label.replaceAll(' ', '')
    await downloadBatchInputTemplate(template.value.id, version.value, `${template.value.title}-${label}数据模板.xlsx`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败，请重试'))
  } finally {
    downloading.value = false
  }
}

/** 开始前的确认：用哪个模型、哪一版、处理多少条、大概多少钱；没设输出字段的再提醒一句 */
function confirmText(title: string, data: NonNullable<typeof summary.value>, rows: number): string {
  const cost = estimate.value ? `，预计约 ${formatYuan(estimate.value.total)}` : ''
  const warn = noFields.value ? `\n注意：${noFields.value}。` : ''
  return `用「${model.value!.name}」按「${title}」${confirmedLabel(spec.value!, data)}处理「${data.name}」${rows === data.rows ? '全部' : '前'} ${rows} 条，会产生模型费用${cost}。${warn}`
}

async function start(): Promise<void> {
  if (blocker.value || starting.value) return
  const selected = template.value!
  const data = summary.value!
  const rows = count.value
  const ok = await ElMessageBox.confirm(
    confirmText(selected.title, data, rows),
    '开始运行？',
    { confirmButtonText: '开始运行', cancelButtonText: '取消', type: 'warning', customClass: 'confirm-lines' },
  ).then(() => true, () => false)
  if (!ok) return
  starting.value = true
  try {
    const useThinking = thinking.value && Boolean(model.value?.supports_thinking)
    const req = { prompt_id: selected.id, version: version.value, thinking: useThinking, limit: rows === data.rows ? 0 : rows }
    if (dbPayload.value) await startBatchRunFromRows(req, dbPayload.value)
    else await startBatchRun(req, file.value!)
    ElMessage.success(`已加入队列，共 ${rows} 条`)
    open.value = false
    emit('created')
  } catch (error) {
    failure.value = errorMessage(error, '没能创建任务，数据还在，可以重试')
  } finally {
    starting.value = false
  }
}

function close(done: () => void): void {
  if (starting.value) return
  if (!file.value && !dbPayload.value) { done(); return }
  void ElMessageBox.confirm('选好的数据还没提交，关闭后要重新选。', '关闭新建任务？', { confirmButtonText: '关闭', cancelButtonText: '继续填写' })
    .then(() => { sequence++; done() }, () => {})
}
</script>

<template>
  <el-drawer
    v-model="open"
    title="新建批量任务"
    size="min(680px, 100vw)"
    class="editor-overlay new-task"
    :before-close="close"
    :close-on-click-modal="false"
    :close-on-press-escape="!starting"
  >
    <fieldset
      class="new-task__steps"
      :disabled="starting"
      :aria-busy="starting"
    >
      <BatchVersionPick
        v-model:template-id="templateId"
        v-model:version="version"
        :templates="templates"
        :template="template"
        :spec="spec"
        :disabled="starting || previewing"
      />
      <!-- 没设输出字段只提醒、不拦：一选模板就写出来，不等上传完文件（底部那行会被「上传数据」挡住） -->
      <p
        v-if="noFields"
        class="new-task__warn"
        role="status"
      >
        {{ noFields }}
      </p>
      <section class="new-task__step">
        <div class="new-task__step-head">
          <h3><span>{{ stepNo(3) }}</span>选择这次的数据</h3>
          <el-radio-group
            v-if="canPickFromDb"
            v-model="inputMode"
            size="small"
            :disabled="starting || previewing"
          >
            <el-radio-button value="upload">
              上传 Excel
            </el-radio-button>
            <el-radio-button value="db">
              从政策库取数
            </el-radio-button>
          </el-radio-group>
        </div>
        <input
          ref="picker"
          type="file"
          accept=".xlsx"
          hidden
          aria-label="选择数据文件"
          @change="pick"
        >
        <div
          v-if="summary"
          class="new-task__file"
        >
          <el-icon><CircleCheckFilled /></el-icon>
          <div>
            <strong>{{ summary.name }}</strong>
            <span>{{ dbNote || `${summary.rows.toLocaleString()} 行数据 · ${summary.headers.length} 列，模板要的列都有` }}</span>
            <em v-if="summary.warning">{{ summary.warning }}</em>
          </div>
          <el-button
            size="small"
            :disabled="starting"
            @click="inputMode === 'db' ? clearData() : picker?.click()"
          >
            {{ inputMode === 'db' ? '重新抽取' : '换一个' }}
          </el-button>
        </div>
        <BatchDbPicker
          v-else-if="inputMode === 'db' && canPickFromDb && template"
          :template="template"
          :version="version"
          :tasks="sampleTasks"
          :provinces="sampleProvinces"
          :industries="sampleIndustries"
          :disabled="!spec || Boolean(spec.problem) || starting"
          @loaded="onDbLoaded"
          @error="msg => failure = msg"
          @loading="busy => previewing = busy"
        />
        <template v-else>
          <div class="new-task__upload">
            <el-button
              :icon="Upload"
              :loading="previewing"
              :disabled="!spec || Boolean(spec.problem) || starting"
              @click="picker?.click()"
            >
              选择 .xlsx 文件
            </el-button>
            <el-button
              v-if="spec?.columns.length"
              :icon="Download"
              :loading="downloading"
              :disabled="starting"
              @click="downloadTemplate"
            >
              下载数据模板
            </el-button>
          </div>
          <p class="new-task__hint">
            {{ uploadHint }}
          </p>
        </template>
      </section>

      <section class="new-task__step">
        <h3><span>{{ stepNo(4) }}</span>跑多少</h3>
        <el-radio-group
          v-model="scope"
          class="new-task__scope"
          aria-label="跑多少"
          :disabled="!summary"
        >
          <el-radio value="all">
            全部{{ summary ? ` ${summary.rows.toLocaleString()} 条` : '' }}
          </el-radio>
          <el-radio
            value="test"
            :disabled="!summary || summary.rows <= 1"
          >
            先跑前几条看看
          </el-radio>
        </el-radio-group>
        <div
          v-if="scope === 'test'"
          class="new-task__test-rows"
        >
          <label for="batch-test-rows">先跑前</label>
          <el-input-number
            id="batch-test-rows"
            :key="testRowsMax"
            v-model="testRows"
            size="small"
            :min="1"
            :max="testRowsMax"
            controls-position="right"
          />
          <span>条，满意了再跑全部</span>
        </div>
        <el-switch
          v-if="model?.supports_thinking"
          v-model="thinking"
          active-text="深度思考"
        />
      </section>
    </fieldset>
    <el-alert
      v-if="failure"
      :title="failure"
      type="error"
      :closable="false"
      show-icon
    />
    <template #footer>
      <div class="new-task__footer">
        <p
          v-if="blocker"
          role="status"
        >
          {{ blocker }}
        </p>

        <p
          v-else-if="estimate"
          class="new-task__estimate"
        >
          <b>预计约 {{ formatYuan(estimate.total) }}</b>
          <span>按最近一次样本试跑平均每条 {{ formatYuan(estimate.perRow) }} 估算，实际以账单为准</span>
        </p>
        <span v-else />
        <el-button
          type="primary"
          :loading="starting"
          :disabled="Boolean(blocker)"
          @click="start"
        >
          开始运行{{ summary && !blocker ? ` ${count.toLocaleString()} 条` : '' }}
        </el-button>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped src="./new-batch-task.css"></style>
