<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheckFilled, Download, Upload } from '@element-plus/icons-vue'

import { previewBatchInput, startBatchRun, type AiModel, type BatchInputSummary, type PromptTemplate } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { downloadBatchInputTemplate } from '../shared/downloads'

/**
 * 新建批量任务：选一个已上线的模板，上传这次的数据，选跑全部还是先跑几条。
 * 任务按上线版本跑（和定时任务一样），模板草稿上没上线的改动、模板的测试样本都不参与。
 */
const props = defineProps<{ templates: PromptTemplate[]; models: AiModel[] }>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ created: [] }>()
const templateId = ref('')
const thinking = ref(false)
const file = ref<File | null>(null)
const summary = ref<BatchInputSummary | null>(null)
const previewing = ref(false)
const downloading = ref(false)
const starting = ref(false)
const failure = ref('')
const scope = ref<'all' | 'test'>('all')
const testRows = ref(10)
const picker = ref<HTMLInputElement>()
let sequence = 0

/** 能选的排前面；不能选的也列出来，写清原因，免得找不到模板以为丢了。 */
const options = computed(() => props.templates
  .map(item => ({ item, reason: !item.release ? '未上线' : !item.editable ? '只能查看' : '' }))
  .sort((a, b) => Number(Boolean(a.reason)) - Number(Boolean(b.reason))))
const template = computed(() => props.templates.find(item => item.id === templateId.value))
const release = computed(() => template.value?.release ?? null)
const model = computed(() => props.models.find(item => item.id === release.value?.model_id))
const uploadHint = computed(() => (release.value?.variables.length
  ? '先下载数据模板，表头就是这一版要的列，不要改名；每行填一条数据，可以加别的列，会原样留在结果里。选好后先检查列，不会调用模型。'
  : '第一行是表头，每行问一次。选好后先检查列，不会调用模型。'))
const count = computed(() => (scope.value === 'test' ? Math.min(testRows.value || 1, summary.value?.rows ?? 0) : summary.value?.rows ?? 0))
const modelProblem = computed(() => {
  if (!release.value) return ''
  if (!model.value) return `第 ${release.value.release_no} 版用的模型「${release.value.model_name}」已停用，请在模板里换模型并重新上线`
  if (!model.value.available) return `「${model.value.name}」的接口密钥还没配置，暂时不能跑`
  return ''
})
const blocker = computed(() => {
  if (!template.value) return '选一个已上线的模板'
  if (modelProblem.value) return modelProblem.value
  if (previewing.value) return '正在检查数据…'
  if (!summary.value || !file.value) return '上传这次要跑的数据'
  return ''
})

watch(open, value => {
  sequence++
  if (!value) return
  templateId.value = ''
  thinking.value = false
  file.value = null
  summary.value = null
  failure.value = ''
  scope.value = 'all'
  testRows.value = 10
}, { flush: 'sync' })
// 只选了模板不算没保存的工作；选好的数据文件丢了要重新找，离开前提醒。
useUnsavedForm(open, () => file.value?.name ?? '', starting)
watch(templateId, () => {
  sequence++
  file.value = null
  summary.value = null
  failure.value = ''
  previewing.value = false
})

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
    const result = await previewBatchInput(template.value.id, chosen)
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

/** 表头就是上线版本要的列：照着填好再传，不用对着页面上的列名自己建表。 */
async function downloadTemplate(): Promise<void> {
  if (!template.value || !release.value || downloading.value) return
  downloading.value = true
  try {
    await downloadBatchInputTemplate(template.value.id, `${template.value.title}-第${release.value.release_no}版数据模板.xlsx`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败，请重试'))
  } finally {
    downloading.value = false
  }
}

async function start(): Promise<void> {
  if (blocker.value || starting.value) return
  const selected = template.value!
  const input = file.value!
  const data = summary.value!
  const rows = count.value
  const ok = await ElMessageBox.confirm(
    `用「${model.value!.name}」按「${selected.title}」第 ${data.release_no} 版处理「${data.name}」${rows === data.rows ? '全部' : '前'} ${rows} 条，会产生模型费用。`,
    '开始运行？',
    { confirmButtonText: '开始运行', cancelButtonText: '取消', type: 'warning' },
  ).then(() => true, () => false)
  if (!ok) return
  starting.value = true
  try {
    const useThinking = thinking.value && Boolean(model.value?.supports_thinking)
    await startBatchRun({ prompt_id: selected.id, thinking: useThinking, limit: rows === data.rows ? 0 : rows }, input)
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
  if (!file.value) { done(); return }
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
      <section class="new-task__step">
        <h3><span>1</span>选模板</h3>
        <el-select
          v-model="templateId"
          filterable
          placeholder="搜索模板名称"
          aria-label="任务模板"
          :disabled="starting"
        >
          <el-option
            v-for="{ item, reason } in options"
            :key="item.id"
            :value="item.id"
            :label="item.title"
            :disabled="Boolean(reason)"
          >
            <span class="new-task__option">
              <span>{{ item.title }}</span>
              <small>{{ reason || `${item.category_name} · 第 ${item.release?.release_no} 版` }}</small>
            </span>
          </el-option>
        </el-select>
        <p class="new-task__hint">
          只能选已上线的模板，任务按上线版本跑；还在调的模板请先在「提示词模板」试跑、上线。
        </p>
        <div
          v-if="release"
          class="new-task__release"
        >
          <p class="new-task__release-title">
            第 {{ release.release_no }} 版 · {{ release.released_by_name }} {{ release.released_at }} 上线
          </p>
          <dl>
            <dt>数据要有</dt>
            <dd class="new-task__columns">
              <template v-if="release.variables.length">
                <span
                  v-for="column in release.variables"
                  :key="column"
                >{{ column }}</span>
              </template>
              <template v-else>
                不引用列，任意 .xlsx 都行
              </template>
            </dd>
            <dt>模型</dt><dd>{{ release.model_name }}</dd>
            <dt>输出字段</dt>
            <dd
              class="new-task__fields"
              :title="release.fields.join('、')"
            >
              {{ release.fields.length ? `${release.fields.length} 个：${release.fields.join('、')}` : '未设置，保留模型原话' }}
            </dd>
            <dt>码表</dt><dd>{{ release.code || '不用码表' }}</dd>
          </dl>
          <p
            v-if="release.unreleased_changes.length"
            class="new-task__note"
          >
            模板草稿改了{{ release.unreleased_changes.join('、') }}，还没上线；这次按第 {{ release.release_no }} 版跑。
          </p>
          <details>
            <summary>看第 {{ release.release_no }} 版的提示词</summary>
            <pre>{{ release.content }}</pre>
          </details>
        </div>
        <p
          v-if="modelProblem"
          class="new-task__problem"
        >
          {{ modelProblem }}
        </p>
      </section>

      <section class="new-task__step">
        <h3><span>2</span>上传这次的数据</h3>
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
            <span>{{ summary.rows.toLocaleString() }} 行数据 · {{ summary.headers.length }} 列，模板要的列都有</span>
          </div>
          <el-button
            size="small"
            :disabled="starting"
            @click="picker?.click()"
          >
            换一个
          </el-button>
        </div>
        <div
          v-else
          class="new-task__upload"
        >
          <el-button
            :icon="Upload"
            :loading="previewing"
            :disabled="!release || Boolean(modelProblem) || starting"
            @click="picker?.click()"
          >
            选择 .xlsx 文件
          </el-button>
          <el-button
            v-if="release?.variables.length"
            :icon="Download"
            :loading="downloading"
            :disabled="starting"
            @click="downloadTemplate"
          >
            下载数据模板
          </el-button>
        </div>
        <p
          v-if="!summary"
          class="new-task__hint"
        >
          {{ uploadHint }}
        </p>
      </section>

      <section class="new-task__step">
        <h3><span>3</span>跑多少</h3>
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
            v-model="testRows"
            size="small"
            :min="1"
            :max="summary ? Math.max(summary.rows - 1, 1) : 100000"
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

<style scoped>
.new-task__steps { min-width: 0; margin: 0; padding: 0; border: 0; }
.new-task__step { padding: 4px 0 22px; margin-bottom: 20px; border-bottom: 1px solid var(--zt-border); }
.new-task__step:last-child { margin-bottom: 0; border-bottom: 0; }
.new-task__step h3 { display: flex; align-items: center; gap: 10px; margin: 0 0 12px; color: var(--zt-ink-900); font-size: 15px; font-weight: 650; }
.new-task__step h3 span { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: var(--zt-blue-600); color: var(--el-color-white); font-size: 12px; }
.new-task__step .el-select { width: 100%; }
.new-task__option { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.new-task__option small { color: var(--zt-ink-500); font-size: 12px; }
.new-task__hint { margin: 8px 0 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }
.new-task__release { margin-top: 12px; padding: 14px 16px; border-radius: 6px; background: var(--zt-soft); font-size: 13px; }
.new-task__release-title { margin: 0 0 10px; color: var(--zt-ink-700); font-weight: 600; }
.new-task__release dl { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 8px 12px; margin: 0; }
.new-task__release dt { color: var(--zt-ink-500); }
.new-task__release dd { margin: 0; overflow-wrap: anywhere; }
.new-task__columns { display: flex; flex-wrap: wrap; gap: 6px; }
.new-task__fields { display: -webkit-box; overflow: hidden; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.new-task__columns span { padding: 0 8px; border-radius: 4px; background: var(--el-color-primary-light-9); color: var(--zt-blue-700); line-height: 22px; }
.new-task__note { margin: 10px 0 0; color: var(--zt-warning-text); }
.new-task__release summary { margin-top: 10px; color: var(--zt-blue-600); cursor: pointer; }
.new-task__release pre { max-height: 260px; overflow: auto; margin: 8px 0 0; padding: 10px 12px; border-radius: 6px; background: var(--zt-panel); font: inherit; font-size: 13px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.new-task__problem { margin: 10px 0 0; color: var(--el-color-danger); font-size: 13px; }
.new-task__upload { display: flex; flex-wrap: wrap; gap: 8px; }
.new-task__upload .el-button { margin: 0; }
.new-task__file { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid var(--zt-success-border); border-radius: 6px; background: var(--zt-success-soft); }
.new-task__file > .el-icon { flex: none; color: var(--zt-success); font-size: 20px; }
.new-task__file div { display: flex; flex: 1; flex-direction: column; min-width: 0; }
.new-task__file strong { overflow: hidden; color: var(--zt-ink-900); text-overflow: ellipsis; white-space: nowrap; }
.new-task__file span { color: var(--zt-ink-500); font-size: 12px; }
.new-task__scope { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; margin-bottom: 8px; }
.new-task__test-rows { display: flex; align-items: center; gap: 8px; margin: 0 0 12px 24px; color: var(--zt-ink-700); font-size: 13px; }
.new-task__test-rows .el-input-number { width: 100px; }
.new-task__footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.new-task__footer p { margin: 0; color: var(--zt-ink-500); font-size: 13px; text-align: left; }
.new-task__footer .el-button { margin: 0; }
</style>
