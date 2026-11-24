<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'

import { createPrompt, promptEditorData, updatePrompt, type AiModel, type BatchRun, type PromptFileKind, type PromptTemplate, type SystemCodeTable, type TemplateCategory } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import DetailSkeleton from '@/components/DetailSkeleton.vue'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { useAuthStore } from '@/stores/auth'
import { splitFields } from '../shared/aiText'
import { defaultCategory } from '../shared/categories'
import { useAnswerStream } from '../shared/useAnswerStream'
import FlowBar from './FlowBar.vue'
import OutputFieldsDock from './OutputFieldsDock.vue'
import PromptEditor from './PromptEditor.vue'
import PromptSettings from './PromptSettings.vue'
import ReleaseDrawer from './ReleaseDrawer.vue'
import { removeTemplate, trialRequest } from './promptActions'
import TestPanel from './TestPanel.vue'
import { fitSummary } from './taskFit'
import { flowSteps, stepActions, withSample, type StepKey } from './templateStatus'
import { useTaskFit } from './useTaskFit'
import { useTemplateFiles } from './useTemplateFiles'
import { createTurns } from '../shared/inTurn'
import '../shared/ai.css'

/**
 * 编辑一个模板：顶部三步（写提示词 → 样本试跑 → 上线）告诉人到哪一步；左边写提示词和设置，右边试发一条、样本试跑，上线由管理员审核。
 * 新模板不用先点保存就能传测试样本、码表：起了名字，上传时顺便存成模板，先传样本再照着列名写提示词。
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
const sampleWide = ref(false)
const editorWide = ref(false)
const trialRow = ref(0)
const editor = ref<{ focus: () => void } | null>(null)
const releasing = ref(false)
const form = reactive({ title: '', category: '', content: '', output_fields: '', model_id: '', code_table: '' })
const unsaved = useUnsavedForm(ref(true), () => ({ ...form }), saving)
unsaved.markSaved()
const answer = useAnswerStream()
const taskFit = useTaskFit(form)
watch(() => form.category, category => { if (category === 'policy') void taskFit.load() }, { immediate: true })
const releaseFit = computed(() => fitSummary(taskFit.results.value))
const titleInput = ref<HTMLInputElement | null>(null)
const FILE_KINDS: PromptFileKind[] = ['excel', 'code']
// 保存、上传、删附件都会换版本号，排队一个接一个发（见 createTurns）。
const inTurn = createTurns()
const files = useTemplateFiles({ template: selected, canCreate: canCreateDraft, create: () => persist(true), changed: replace, inTurn })

// 新建的地址是 /ai/prompts/new，保存后换成模板 ID：同一条路由，页面不重建，试发记录也还在。
const routeId = computed(() => (typeof route.params.id === 'string' && route.params.id !== 'new' ? route.params.id : ''))
const opening = computed(() => Boolean(routeId.value) && !selected.value && !loadError.value)
const editableCategories = computed(() => categories.value.filter(item => item.editable))
// 能不能改看两层：页面本身的编辑权，加这个模板所属类型的编辑权；新模板只要有一个能编辑的类型就行。
const canEdit = computed(() => canEditPage.value && (selected.value ? selected.value.editable : editableCategories.value.length > 0))
/** 类型下拉：能编辑的类型；只读模板也要显示它自己的类型。 */
const categoryOptions = computed(() => {
  const own = categories.value.find(item => item.code === selected.value?.category)
  return own && !own.editable ? [own, ...editableCategories.value] : editableCategories.value
})
// 试发、试跑都用模板上选的模型，和上线后跑的是同一个；没选就提示去选，不拿别的模型顶替。
const trialModel = computed(() => models.value.find(item => item.id === form.model_id))
const dirty = computed(() => unsaved.dirty.value || !selected.value)
/** 提示词里 @【上传码表】换成的是哪份码表：系统码表名或上传的文件名，空表示没选 */
const codeName = computed(() => (form.code_table
  ? codeTables.value.find(item => item.key === form.code_table)?.name ?? form.code_table
  : selected.value?.code_name ?? ''))

const steps = computed(() => flowSteps(selected.value, dirty.value, canRelease.value))
/** 流程条上的按钮：去试跑、上线第 N 版、看改动、上线管理……按身份和状态给，规则在 templateStatus。 */
const actions = computed(() => stepActions(selected.value, steps.value, {
  canEdit: canEdit.value, canRelease: canRelease.value, sampleOpen: testTab.value === 'sample',
}))

let loadSeq = 0

async function load(): Promise<void> {
  const seq = ++loadSeq
  loading.value = true
  try {
    const data = await promptEditorData(routeId.value)
    if (seq !== loadSeq) return
    models.value = data.models
    categories.value = data.categories
    codeTables.value = data.code_tables
    loadError.value = ''
    fill(data.item)
    openReviewFromLink()
  } catch (error) { if (seq === loadSeq) loadError.value = errorMessage(error, '模板加载失败，请刷新重试') }
  finally { if (seq === loadSeq) loading.value = false }
}
onMounted(load)

/** 列表上点「看改动」带 ?review=1 进来：直接打开上线抽屉看草稿和线上的对比，地址里去掉这个参数。 */
function openReviewFromLink(): void {
  if (route.query.review !== '1') return
  void router.replace({ query: { ...route.query, review: undefined } })
  if (selected.value?.release) releasing.value = true
}
watch(routeId, id => {
  if (id === (selected.value?.id ?? '')) return
  answer.stop(); void load()
})
onBeforeUnmount(answer.stop)

function fill(template: PromptTemplate | null): void {
  selected.value = template
  const wanted = typeof route.query.category === 'string' ? route.query.category : ''
  // 新模板先选好一个不联网的模型：联网更贵更慢，要用再自己换。
  const model = models.value.find(item => item.available && !item.web_search) ?? models.value.find(item => item.available)
  const { title, category, content, output_fields, model_id, code_table } = template
    ?? { title: '', category: defaultCategory(editableCategories.value, wanted), content: '', output_fields: '', model_id: model?.id ?? '', code_table: '' }
  Object.assign(form, { title, category, content, output_fields, model_id, code_table })
  unsaved.markSaved()
}

/** 上传、删除附件，上线、下线，试跑开始和结束：只换模板信息，不动没保存的草稿。 */
function replace(template: PromptTemplate): void { selected.value = template }
function sampleChanged(run: BatchRun): void { if (selected.value) selected.value = withSample(selected.value, run) }

/** 能不能存成模板：要有名字和类型；提示词可以先空着（先传样本再照着列名写）。不行就说明原因，名字空着就把光标放过去。 */
function canCreateDraft(): boolean {
  if (!form.title.trim()) {
    ElMessage.warning(selected.value ? '请填写模板名称' : '先给模板起个名字，上传时会顺便保存模板')
    titleInput.value?.focus()
    return false
  }
  if (!form.category) { ElMessage.warning('请选择模板类型'); return false }
  return true
}

/** 存下草稿并返回模板；quiet 时不弹「已保存」（上传时顺便保存，由上传那边一起提示）。和上传、删附件排队执行（inTurn）。 */
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
      // Ctrl/⌘+S 之后接着打字：请求期间敲的字不能被服务端返回的版本盖掉。只换模板信息（版本号等），
      // 基线是发出去的那份，表单仍算未保存。
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
  // 只读的人在编辑器里按 Ctrl/⌘+Enter 也会走到这里，后端只会回 403。
  if (!canEdit.value) return
  const problem = form.content.trim() ? '' : '提示词内容不能为空'
  if (problem || !trialModel.value) return void ElMessage.warning(problem || '先在左边「模型」里选一个模型')
  testTab.value = 'trial'
  const context = { template: selected.value, model: trialModel.value, row: trialRow.value, thinking: thinking.value }
  const request = trialRequest(form, context)
  await answer.send('/ai/stream/ask', request.body, request.shown, request.thinking)
}

function onStep(key: StepKey): void {
  if (key === 'test') testTab.value = 'sample'; else if (key === 'release') releasing.value = true
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
          ref="titleInput"
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
        <el-button
          v-if="!(testTab === 'sample' && sampleWide)"
          size="small"
          @click="editorWide = !editorWide"
        >
          {{ editorWide ? '恢复分栏' : '专注编辑' }}
        </el-button>
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
          :disabled="Boolean(selected) && !unsaved.dirty.value"
          title="Ctrl/⌘ + S"
          @click="persist()"
        >
          保存
        </el-button>
      </div>
      <FlowBar
        :steps="steps"
        :actions="actions"
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
        'is-sample': testTab === 'sample',
        'is-sample-wide': testTab === 'sample' && sampleWide,
        'is-editor-wide': editorWide && !(testTab === 'sample' && sampleWide),
      }"
    >
      <form
        class="ai-panel prompt-page__main"
        aria-label="编写模板"
        @submit.prevent="persist()"
      >
        <div class="prompt-page__scroll">
          <PromptSettings
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
          <PromptEditor
            ref="editor"
            v-model="form.content"
            :headers="selected?.excel_headers ?? []"
            :code-name="codeName"
            :disabled="!canEdit"
            @run="trial"
            @save="persist()"
            @upload="files.pick('excel')"
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
        :model="trialModel"
        :content="form.content"
        :fields="splitFields(form.output_fields)"
        :code-name="codeName"
        :can-run="canEdit"
        :can-export="canExport"
        :dirty="unsaved.dirty.value"
        @run="trial"
        @upload="files.pick('excel')"
        @edit="sampleWide = false; editorWide = false; editor?.focus()"
        @sample-changed="sampleChanged"
      />
    </div>
    <!-- 两个附件的文件框：编辑器、试跑区、设置区的「上传」都点这里，新模板上传时顺便保存。 -->
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
