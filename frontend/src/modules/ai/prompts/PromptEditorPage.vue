<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { createPrompt, promptEditorData, updatePrompt, type AiModel, type BatchRun, type PromptFileKind, type PromptTemplate, type SystemCodeTable, type TemplateCategory } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import DetailSkeleton from '@/components/DetailSkeleton.vue'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { useAuthStore } from '@/stores/auth'
import { splitFields } from '../shared/aiText'
import { defaultCategory } from '../shared/categories'
import { createTurns } from '../shared/inTurn'
import { useAnswerStream } from '../shared/useAnswerStream'
import OutputFieldsDock from './OutputFieldsDock.vue'
import PromptEditor from './PromptEditor.vue'
import PromptEditorHeader from './PromptEditorHeader.vue'
import PromptSettings from './PromptSettings.vue'
import ReleaseDrawer from './ReleaseDrawer.vue'
import { removeTemplate, trialRequest } from './promptActions'
import { starterPromptForCategory } from './promptStarter'
import TestPanel from './TestPanel.vue'
import { fitSummary } from './taskFit'
import { withSample } from './templateStatus'
import { useTaskFit } from './useTaskFit'
import { useTemplateFiles } from './useTemplateFiles'
import '../shared/ai.css'

/**
 * 提示词工程工作台：单行 48px 顶栏 + 左栏 40px 吸顶配置丝带 + 高占比提示词画布 + 右栏单条试发/样本试跑。
 * 新模板不用先点保存就能传测试样本或从库取数：起好名字后上传会顺便存成模板（inTurn 串行防并发冲突）。
 */
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const canEditPage = computed(() => auth.canFull('ai.prompts'))
const canExport = computed(() => auth.canExport('ai.prompts'))
const models = ref<AiModel[]>([])
const categories = ref<TemplateCategory[]>([])
const codeTables = ref<SystemCodeTable[]>([])
const selected = ref<PromptTemplate | null>(null)
const loading = ref(false)
const loaded = ref(false)
const loadError = ref('')
const saving = ref(false)
const thinking = ref(false)
const testTab = ref<'trial' | 'sample'>('trial')
const sampleWide = ref(false)
const editorWide = ref(false)
const trialRow = ref(0)
const editor = ref<{ focus: () => void } | null>(null)
const headerRef = ref<{ focusTitle: () => void } | null>(null)
const settingsRef = ref<{ openSampleDb: () => Promise<void> | undefined } | null>(null)
const releasing = ref(false)
const form = reactive({ title: '', category: '', content: '', output_fields: '', model_id: '', code_table: '' })
const unsaved = useUnsavedForm(ref(true), () => ({ ...form }), saving)
unsaved.markSaved()
const answer = useAnswerStream()
const taskFit = useTaskFit(form)
watch(() => form.category, category => { if (category === 'policy') void taskFit.load() }, { immediate: true })
const releaseFit = computed(() => fitSummary(taskFit.results.value))
const FILE_KINDS: PromptFileKind[] = ['excel', 'code']
// 保存、上传、删附件都会换版本号，排队一个接一个发（见 createTurns）。
const inTurn = createTurns()
const files = useTemplateFiles({ template: selected, canCreate: canCreateDraft, create: () => persist(true), changed: replace, inTurn })

const routeId = computed(() => (typeof route.params.id === 'string' && route.params.id !== 'new' ? route.params.id : ''))
const opening = computed(() => Boolean(routeId.value) && !selected.value && !loadError.value)
const editableCategories = computed(() => categories.value.filter(item => item.editable))
const canEdit = computed(() => canEditPage.value && (
  selected.value
    ? selected.value.editable
    : (loading.value && !categories.value.length) || editableCategories.value.length > 0
))
const canRelease = computed(() => auth.canFull('ai.releases') && Boolean(selected.value?.editable))
const categoryOptions = computed(() => {
  const own = categories.value.find(item => item.code === selected.value?.category)
  return own && !own.editable ? [own, ...editableCategories.value] : editableCategories.value
})
const trialModel = computed(() => models.value.find(item => item.id === form.model_id))
const codeName = computed(() => (form.code_table
  ? codeTables.value.find(item => item.key === form.code_table)?.name ?? form.code_table
  : selected.value?.code_name ?? ''))

let loadSeq = 0

function needsCreateForbidden(): boolean {
  return !routeId.value && !loadError.value && (!canEditPage.value || (loaded.value && !loading.value && !canEdit.value))
}

async function load(): Promise<void> {
  if (!routeId.value && !canEditPage.value) {
    void router.replace({ name: 'forbidden' })
    return
  }
  const seq = ++loadSeq
  loading.value = true
  try {
    const data = await promptEditorData(routeId.value)
    if (seq !== loadSeq) return
    models.value = data.models
    categories.value = data.categories
    codeTables.value = data.code_tables
    loadError.value = ''
    loaded.value = true
    if (!routeId.value && !editableCategories.value.length) {
      void router.replace({ name: 'forbidden' })
      return
    }
    fill(data.item)
    openReviewFromLink()
  } catch (error) { if (seq === loadSeq) loadError.value = errorMessage(error, '模板加载失败，请刷新重试') }
  finally { if (seq === loadSeq) loading.value = false }
}
onMounted(load)

function openReviewFromLink(): void {
  if (route.query.review !== '1') return
  void router.replace({ query: { ...route.query, review: undefined } })
  if (selected.value && (selected.value.release || canRelease.value)) releasing.value = true
}
watch(routeId, id => {
  if (id === (selected.value?.id ?? '')) return
  loaded.value = false
  answer.stop(); void load()
})
watch([routeId, loading, canEdit], () => {
  if (needsCreateForbidden()) void router.replace({ name: 'forbidden' })
})
onBeforeUnmount(answer.stop)

function fill(template: PromptTemplate | null): void {
  selected.value = template
  const wanted = typeof route.query.category === 'string' ? route.query.category : ''
  const model = models.value.find(item => item.available && !item.web_search) ?? models.value.find(item => item.available)
  const { title, category, content, output_fields, model_id, code_table } = template
    ?? { title: '', category: defaultCategory(editableCategories.value, wanted), content: '', output_fields: '', model_id: model?.id ?? '', code_table: '' }
  Object.assign(form, { title, category, content, output_fields, model_id, code_table })
  unsaved.markSaved()
}

function replace(template: PromptTemplate): void { selected.value = template }
function sampleChanged(run: BatchRun): void { if (selected.value) selected.value = withSample(selected.value, run) }

function canCreateDraft(): boolean {
  if (!form.title.trim()) {
    ElMessage.warning(selected.value ? '请填写模板名称' : '先给模板起个名字，上传时会顺便保存模板')
    headerRef.value?.focusTitle()
    return false
  }
  if (!form.category) { ElMessage.warning('请选择模板类型'); return false }
  return true
}

function persist(quiet = false): Promise<PromptTemplate | null> {
  if (!canEdit.value || !canCreateDraft()) return Promise.resolve(null)
  return inTurn(() => save(quiet))
}

async function save(quiet: boolean): Promise<PromptTemplate | null> {
  saving.value = true
  try {
    const creating = !selected.value
    const sent = { ...form }
    const payload = { ...sent, version: selected.value?.version }
    const saved = selected.value ? await updatePrompt(selected.value.id, payload) : await createPrompt(payload)
    if (JSON.stringify({ ...form }) === JSON.stringify(sent)) {
      fill(saved)
    } else {
      selected.value = saved
      unsaved.markSaved(sent)
    }
    if (!quiet) ElMessage.success('模板已保存')
    if (creating) await router.replace({ name: 'ai-prompt-edit', params: { id: saved.id } })
    return saved
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败，请重试'))
    return null
  } finally {
    saving.value = false
  }
}

async function remove(): Promise<void> {
  if (!selected.value || !await removeTemplate(selected.value)) return
  unsaved.markSaved()
  await router.push({ name: 'ai-prompts' })
}

async function trial(): Promise<void> {
  if (!canEdit.value) return
  const problem = form.content.trim() ? '' : '提示词内容不能为空'
  if (problem || !trialModel.value) return void ElMessage.warning(problem || '请先在左上方配置栏选择一个模型')
  testTab.value = 'trial'
  const context = { template: selected.value, model: trialModel.value, row: trialRow.value, thinking: thinking.value }
  const request = trialRequest(form, context)
  await answer.send('/ai/stream/ask', request.body, request.shown, request.thinking)
}

function pickExcel(): void {
  if (!canEdit.value) return
  files.pick('excel')
}

function applyStarter(): void {
  if (!canEdit.value) return
  const spec = starterPromptForCategory(form.category)
  if (!form.title.trim()) form.title = spec.defaultTitle
  form.content = spec.content
  form.output_fields = spec.outputFields
  ElMessage({ type: 'success', message: '已填入标准结构化提示词骨架，可直接按 Ctrl+Enter 试发', offset: 72, duration: 2400 })
  editor.value?.focus()
}
</script>

<template>
  <section
    class="prompt-page"
    :class="{ 'is-opening': opening && !selected }"
  >
    <h1 class="ai-sr-only">
      {{ selected ? selected.title : '新建提示词模板' }}
    </h1>

    <PromptEditorHeader
      ref="headerRef"
      v-model:title="form.title"
      :template="selected"
      :dirty="unsaved.dirty.value"
      :saving="saving"
      :can-edit="canEdit"
      :can-release="canRelease"
      :editor-wide="editorWide"
      :hide-wide-toggle="testTab === 'sample' && sampleWide"
      @save="persist()"
      @remove="remove"
      @open-release="releasing = true"
      @toggle-wide="editorWide = !editorWide"
    />

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
    >
      <el-button @click="load()">
        重试
      </el-button>
    </el-alert>

    <DetailSkeleton
      v-if="opening && !selected"
      :sections="2"
      :fields-per-section="4"
    />

    <div
      v-else
      class="prompt-page__body"
      :class="{
        'is-refreshing': loading,
        'is-sample-wide': testTab === 'sample' && sampleWide,
        'is-editor-wide': editorWide && !(testTab === 'sample' && sampleWide),
      }"
    >
      <form
        class="ai-panel prompt-page__main"
        aria-label="编写模板"
        @submit.prevent="persist()"
      >
        <PromptSettings
          ref="settingsRef"
          v-model:category="form.category"
          v-model:model-id="form.model_id"
          v-model:code-table="form.code_table"
          :template="selected"
          :categories="categoryOptions"
          :models="models"
          :code-tables="codeTables"
          :files="files"
          :can-edit="canEdit"
          :can-export="canExport"
          :sample-options="taskFit.sampleOptions.value"
          :show-fit="taskFit.visible.value"
          :fit="taskFit.results.value"
          @files-changed="replace"
        />

        <div class="prompt-page__scroll">
          <PromptEditor
            ref="editor"
            v-model="form.content"
            :headers="selected?.excel_headers ?? []"
            :code-name="codeName"
            :disabled="!canEdit"
            @run="trial"
            @save="persist()"
            @upload="pickExcel"
          />
        </div>

        <OutputFieldsDock
          v-model:output-fields="form.output_fields"
          v-model:content="form.content"
          :can-edit="canEdit"
        />
      </form>

      <TestPanel
        v-model:tab="testTab"
        v-model:wide="sampleWide"
        v-model:thinking="thinking"
        v-model:row="trialRow"
        class="prompt-page__test"
        :answer="answer"
        :template="selected"
        :category="form.category"
        :has-sample-tasks="Boolean(taskFit.sampleOptions.value.tasks.length)"
        :model="trialModel"
        :content="form.content"
        :fields="splitFields(form.output_fields)"
        :code-name="codeName"
        :can-run="canEdit"
        :can-export="canExport"
        :dirty="unsaved.dirty.value"
        @run="trial"
        @upload="pickExcel"
        @open-sample-db="settingsRef?.openSampleDb()"
        @apply-starter="applyStarter"
        @edit="sampleWide = false; editorWide = false; editor?.focus()"
        @sample-changed="sampleChanged"
      />
    </div>

    <input
      v-for="kind in FILE_KINDS"
      :key="kind"
      :ref="files.bind(kind)"
      type="file"
      :accept="files.accept[kind]"
      hidden
      @change="files.received(kind, $event)"
    >

    <ReleaseDrawer
      v-if="selected"
      v-model="releasing"
      :template="selected"
      :can-release="canRelease"
      :dirty="unsaved.dirty.value"
      :fit="form.category === 'policy' ? releaseFit : null"
      :used-by="taskFit.usedBy(selected.id)"
      @changed="replace"
    />
  </section>
</template>

<style scoped src="./prompt-editor-page.css"></style>
