<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'

import { createPrompt, deletePrompt, listPrompts, updatePrompt, type AiModel, type BatchRun, type PromptTemplate, type SystemCodeTable, type TemplateCategory } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { useAuthStore } from '@/stores/auth'
import { appendBlock, outputFormatBlock, splitFields } from '../shared/aiText'
import { defaultCategory } from '../shared/categories'
import { useAnswerStream } from '../shared/useAnswerStream'
import FlowBar from './FlowBar.vue'
import PromptEditor from './PromptEditor.vue'
import PromptSettings from './PromptSettings.vue'
import ReleaseDrawer from './ReleaseDrawer.vue'
import TestPanel from './TestPanel.vue'
import { fitSummary } from './taskFit'
import { flowSteps, sampleFromRun, type StepKey } from './templateStatus'
import { useTaskFit } from './useTaskFit'
import '../shared/ai.css'

/**
 * 编辑一个模板：顶部三步（写提示词 → 样本试跑 → 上线）告诉人现在到哪一步、下一步做什么；
 * 左边写提示词和设置，右边试发一条、样本试跑。上线由管理员在上线抽屉里审核。
 */
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const canEditPage = computed(() => auth.canFull('ai.prompts'))
const canExport = computed(() => auth.canExport('ai.prompts'))
const canRelease = computed(() => auth.canFull('ai.releases'))
const models = ref<AiModel[]>([])
const categories = ref<TemplateCategory[]>([])
const codeTables = ref<SystemCodeTable[]>([])
const selected = ref<PromptTemplate | null>(null)
const loading = ref(false)
const loadError = ref('')
const saving = ref(false)
const thinking = ref(false)
const testTab = ref<'trial' | 'sample'>('trial')
const releasing = ref(false)
const form = reactive({ title: '', category: '', content: '', output_fields: '', model_id: '', code_table: '' })
const unsaved = useUnsavedForm(ref(true), () => ({ ...form }), saving)
unsaved.markSaved()
const answer = useAnswerStream()
const taskFit = useTaskFit(form)
watch(() => form.category, category => { if (category === 'policy') void taskFit.load() }, { immediate: true })
const releaseFit = computed(() => fitSummary(taskFit.results.value))

// 新建的地址是 /ai/prompts/new，保存后换成模板 ID：同一条路由，页面不重建，试发记录也还在。
const routeId = computed(() => (typeof route.params.id === 'string' && route.params.id !== 'new' ? route.params.id : ''))
const editableCategories = computed(() => categories.value.filter(item => item.editable))
// 能不能改看两层：页面本身的编辑权，加这个模板所属类型的编辑权；新模板只要有一个能编辑的类型就行。
const canEdit = computed(() => canEditPage.value && (selected.value ? selected.value.editable : editableCategories.value.length > 0))
/** 类型下拉：能编辑的类型；只读模板也要显示它自己的类型。 */
const categoryOptions = computed(() => {
  const own = categories.value.find(item => item.code === selected.value?.category)
  return own && !own.editable ? [own, ...editableCategories.value] : editableCategories.value
})
const trialModelId = computed(() => form.model_id || models.value.find(item => item.available)?.id || '')
const trialModel = computed(() => models.value.find(item => item.id === trialModelId.value))
const dirty = computed(() => unsaved.dirty.value || !selected.value)

const steps = computed(() => flowSteps(selected.value, dirty.value, canRelease.value))
const toneOf = (key: StepKey) => steps.value.find(step => step.key === key)?.tone
/** 流程条上的按钮：试跑那一步是下一步时给「去试跑」；上线那一步给管理员「上线第 N 版」，别人只能看。 */
const stepActions = computed<Partial<Record<StepKey, string>>>(() => {
  const template = selected.value
  if (!template) return {}
  // 只能看的模板：不引导去试跑，上线那一步只给「查看上线内容」。
  if (!canEdit.value) return template.release ? { release: '查看上线内容' } : {}
  const actions: Partial<Record<StepKey, string>> = {}
  const testTone = toneOf('test')
  if ((testTone === 'current' || testTone === 'warn') && testTab.value !== 'sample') actions.test = '去试跑'
  const label = releaseAction(template, toneOf('release') === 'current')
  if (label) actions.release = label
  return actions
})

function releaseAction(template: PromptTemplate, isNext: boolean): string {
  if (!canRelease.value) return isNext || template.release ? '查看上线内容' : ''
  // 版本号只增不减：线上那一版就是最新的；下线后不知道下一个号，抽屉里按上线记录写准。
  if (isNext) return template.release ? `上线第 ${template.release.release_no + 1} 版` : '上线'
  // 不是下一步时（没有要上线的改动、或前面还有步骤没做）：看线上版本、上线记录，在里面下线。
  return template.release ? '上线管理' : ''
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listPrompts()
    models.value = data.models
    categories.value = data.categories
    codeTables.value = data.code_tables
    const found = routeId.value ? data.items.find(item => item.id === routeId.value) : null
    loadError.value = routeId.value && !found ? '模板不存在或已被删除' : ''
    fill(found ?? null)
  } catch (error) {
    loadError.value = errorMessage(error, '模板加载失败，请刷新重试')
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(routeId, id => { if (id !== (selected.value?.id ?? '')) void load() })
onBeforeUnmount(answer.stop)

function fill(template: PromptTemplate | null): void {
  selected.value = template
  const wanted = typeof route.query.category === 'string' ? route.query.category : ''
  const { title, category, content, output_fields, model_id, code_table } = template
    ?? { title: '', category: defaultCategory(editableCategories.value, wanted), content: '', output_fields: '', model_id: '', code_table: '' }
  Object.assign(form, { title, category, content, output_fields, model_id, code_table })
  unsaved.markSaved()
}

/** 上传、删除附件，上线、下线，试跑开始和结束：只换模板信息，不动没保存的草稿。 */
function replace(template: PromptTemplate): void {
  selected.value = template
}

function sampleChanged(run: BatchRun): void {
  const template = selected.value
  if (!template) return
  const sample = sampleFromRun(run, template)
  if (JSON.stringify(sample) !== JSON.stringify(template.sample)) selected.value = { ...template, sample }
}

function appendFields(): void {
  form.content = appendBlock(form.content, outputFormatBlock(splitFields(form.output_fields)))
}

async function save(): Promise<void> {
  if (!canEdit.value) return
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('请填写模板名称和提示词')
    return
  }
  if (!form.category) {
    ElMessage.warning('请选择模板类型')
    return
  }
  saving.value = true
  try {
    const creating = !selected.value
    const payload = { ...form, version: selected.value?.version }
    const saved = selected.value ? await updatePrompt(selected.value.id, payload) : await createPrompt(payload)
    fill(saved)
    ElMessage.success('模板已保存')
    if (creating) await router.replace({ name: 'ai-prompt-edit', params: { id: saved.id } })
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败，请重试'))
  } finally {
    saving.value = false
  }
}

async function remove(): Promise<void> {
  const target = selected.value
  if (!target) return
  const ok = await ElMessageBox.confirm(`删除「${target.title}」和它的测试样本、码表文件。已发起的任务和结果不受影响。`, '删除模板？', {
    type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
  }).then(() => true, () => false)
  if (!ok) return
  try {
    await deletePrompt(target.id)
    unsaved.markSaved()
    ElMessage.success('模板已删除')
    await router.push({ name: 'ai-prompts' })
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败，请重试'))
  }
}

async function trial(): Promise<void> {
  if (!form.content.trim()) {
    ElMessage.warning('提示词内容不能为空')
    return
  }
  testTab.value = 'trial'
  const useThinking = thinking.value && Boolean(trialModel.value?.supports_thinking)
  const shown = selected.value ? `［${selected.value.title}］\n${form.content}` : form.content
  await answer.send('/ai/stream/ask', {
    content: form.content,
    model_id: trialModelId.value,
    thinking: useThinking,
    prompt_id: selected.value?.id ?? null,
  }, shown, useThinking)
}

function onStep(key: StepKey): void {
  if (key === 'test') testTab.value = 'sample'
  if (key === 'release') releasing.value = true
}
</script>

<template>
  <section class="prompt-page">
    <h1 class="ai-sr-only">
      {{ selected ? selected.title : '新建提示词模板' }}
    </h1>
    <header class="ai-panel prompt-page__head">
      <div class="prompt-page__title-row">
        <router-link
          class="prompt-page__back"
          aria-label="返回模板列表"
          :to="{ name: 'ai-prompts' }"
        >
          <el-icon><ArrowLeft /></el-icon>提示词模板
        </router-link>
        <input
          v-model="form.title"
          class="prompt-page__title"
          maxlength="255"
          aria-label="模板名称"
          :placeholder="selected ? '模板名称' : '给新模板起个名字'"
          :readonly="!canEdit"
        >
        <el-tag
          v-if="unsaved.dirty.value"
          type="warning"
          size="small"
          effect="plain"
        >
          未保存
        </el-tag>
        <el-tag
          v-if="selected && !canEdit"
          type="info"
          size="small"
          effect="plain"
        >
          只读
        </el-tag>
        <span class="prompt-page__spacer" />
        <el-tooltip
          v-if="canEdit && selected"
          :disabled="!selected.release"
          content="已上线的模板先下线再删除"
        >
          <span>
            <el-button
              text
              type="danger"
              aria-label="删除模板"
              :disabled="Boolean(selected.release)"
              @click="remove"
            >
              删除
            </el-button>
          </span>
        </el-tooltip>
        <el-button
          v-if="canEdit"
          type="primary"
          :loading="saving"
          title="Ctrl/⌘ + S"
          @click="save"
        >
          保存
        </el-button>
      </div>
      <FlowBar
        :steps="steps"
        :actions="stepActions"
        :primary="canEdit || canRelease"
        @step="onStep"
      />
    </header>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
    />

    <div
      v-loading="loading"
      class="prompt-page__body"
    >
      <form
        class="ai-panel prompt-page__main"
        aria-label="编写模板"
        @submit.prevent="save"
      >
        <div class="prompt-page__scroll">
          <PromptEditor
            v-model="form.content"
            :headers="selected?.excel_headers ?? []"
            :has-code="Boolean(form.code_table || selected?.code_name)"
            :disabled="!canEdit"
            @run="trial"
            @save="save"
          />
          <PromptSettings
            v-model:category="form.category"
            v-model:model-id="form.model_id"
            v-model:output-fields="form.output_fields"
            v-model:code-table="form.code_table"
            :template="selected"
            :categories="categoryOptions"
            :models="models"
            :code-tables="codeTables"
            :can-edit="canEdit"
            :can-export="canExport"
            :sample-tasks="taskFit.sampleTasks.value"
            :show-fit="taskFit.visible.value"
            :fit="taskFit.results.value"
            @append-format="appendFields"
            @files-changed="replace"
          />
        </div>
      </form>

      <TestPanel
        v-model:tab="testTab"
        v-model:thinking="thinking"
        class="prompt-page__test"
        :answer="answer"
        :template="selected"
        :model="trialModel"
        :can-run="canEdit"
        :can-export="canExport"
        :dirty="unsaved.dirty.value"
        @run="trial"
        @sample-changed="sampleChanged"
      />
    </div>

    <ReleaseDrawer
      v-if="selected"
      v-model="releasing"
      :template="selected"
      :can-release="canRelease"
      :dirty="unsaved.dirty.value"
      :fit="form.category === 'policy' ? releaseFit : ''"
      @changed="replace"
    />
  </section>
</template>

<style scoped>
.prompt-page { display: flex; flex-direction: column; gap: 12px; height: calc(100dvh - var(--workspace-header-height) - 48px); min-height: 640px; }
.prompt-page__head { flex: none; overflow: hidden; }
.prompt-page__title-row { display: flex; align-items: center; gap: 12px; min-width: 0; padding: 12px 18px; }
.prompt-page__title-row .el-button { margin: 0; }
.prompt-page__back { display: inline-flex; flex: none; align-items: center; gap: 4px; padding-right: 12px; border-right: 1px solid var(--zt-border); color: var(--zt-ink-500); font-size: 13px; text-decoration: none; }
.prompt-page__back:hover { color: var(--zt-blue-600); }
.prompt-page__title { flex: 1; min-width: 0; padding: 2px 0; border: 0; border-bottom: 1px dashed transparent; background: transparent; color: var(--zt-ink-900); font: 600 19px/1.4 var(--zt-font); outline: none; }
.prompt-page__title:hover:not([readonly]), .prompt-page__title:focus { border-bottom-color: var(--el-color-primary-light-5); }
.prompt-page__title::placeholder { color: var(--zt-ink-400); font-weight: 500; }
.prompt-page__spacer { flex: 1; }
.prompt-page__body { display: grid; flex: 1; grid-template-columns: minmax(0, 1fr) minmax(360px, 420px); gap: 12px; min-height: 0; }
.prompt-page__main { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
/* 左栏只有这一条滚动条：提示词在上、跟着内容长高，至少占六成高度；设置区接在下面，不收起也不自己滚。 */
.prompt-page__scroll { display: flex; flex: 1; flex-direction: column; min-height: 0; overflow-y: auto; }
.prompt-page__scroll > .prompt-editor { flex: 1 0 auto; min-height: 60%; }
.prompt-page__scroll > .config { flex: none; }
@media (max-width: 1180px) {
  .prompt-page { height: auto; }
  .prompt-page__body { grid-template-columns: minmax(0, 1fr); }
  .prompt-page__main { min-height: 640px; }
  .prompt-page__test { height: 560px; }
}
</style>
