<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

import { createPrompt, deletePrompt, listPrompts, updatePrompt, type AiModel, type PromptTemplate, type SystemCodeTable, type TemplateCategory } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { useAuthStore } from '@/stores/auth'
import ModelPicker from '../shared/ModelPicker.vue'
import { appendBlock, outputFormatBlock, splitFields } from '../shared/aiText'
import TemplatePicker from '../shared/TemplatePicker.vue'
import { ALL_CATEGORIES, defaultCategory } from '../shared/categories'
import { useAnswerStream } from '../shared/useAnswerStream'
import PromptEditor from './PromptEditor.vue'
import PromptSettings from './PromptSettings.vue'
import ReleaseBar from './ReleaseBar.vue'
import TrialPanel from './TrialPanel.vue'
import { fitSummary } from './taskFit'
import { useTaskFit } from './useTaskFit'
import '../shared/ai.css'

const auth = useAuthStore()
const canEditPage = computed(() => auth.canFull('ai.prompts'))
const canExport = computed(() => auth.canExport('ai.prompts'))
const canRelease = computed(() => auth.canFull('ai.releases'))
const templates = ref<PromptTemplate[]>([])
const models = ref<AiModel[]>([])
const categories = ref<TemplateCategory[]>([])
const codeTables = ref<SystemCodeTable[]>([])
const editableCategories = computed(() => categories.value.filter(item => item.editable))
const selected = ref<PromptTemplate | null>(null)
const categoryFilter = ref(ALL_CATEGORIES)
// 能不能改看两层：页面本身的编辑权，加这个模板所属类型的编辑权；新模板只要有一个能编辑的类型就行。
const canCreate = computed(() => canEditPage.value && editableCategories.value.length > 0)
const canEdit = computed(() => canEditPage.value && (selected.value ? selected.value.editable : canCreate.value))
const loading = ref(false)
const loadError = ref('')
const saving = ref(false)
const thinking = ref(false)
const form = reactive({ title: '', category: '', content: '', output_fields: '', model_id: '', code_table: '' })
const unsaved = useUnsavedForm(ref(true), () => ({ ...form }), saving)
// 编辑区一直打开，useUnsavedForm 只在打开时记基线；不先记一次，空表单也算「未保存」。
unsaved.markSaved()
const answer = useAnswerStream()
// 政策类模板：和三个打标任务的适配检查、从数据库取测试数据。切到政策类时才去取约定。
const taskFit = useTaskFit(form)
watch(() => form.category, category => { if (category === 'policy') void taskFit.load() }, { immediate: true })
const releaseFit = computed(() => fitSummary(taskFit.results.value))

/** 编辑区的类型下拉：能编辑的类型；只读模板也要显示它自己的类型。 */
const categoryOptions = computed(() => {
  const own = categories.value.find(item => item.code === selected.value?.category)
  return own && !own.editable ? [own, ...editableCategories.value] : editableCategories.value
})
const trialModelId = computed(() => form.model_id || models.value.find(item => item.available)?.id || '')
const trialModel = computed(() => models.value.find(item => item.id === trialModelId.value))

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listPrompts()
    templates.value = data.items
    models.value = data.models
    categories.value = data.categories
    codeTables.value = data.code_tables
    if (!selected.value) {
      form.category = defaultCategory(editableCategories.value, categoryFilter.value)
      unsaved.markSaved()
    }
    loadError.value = ''
  } catch (error) {
    loadError.value = errorMessage(error, '模板加载失败，请刷新重试')
  } finally {
    loading.value = false
  }
}
onMounted(load)
onBeforeUnmount(answer.stop)

function fill(template: PromptTemplate | null): void {
  selected.value = template
  const { title, category, content, output_fields, model_id, code_table } = template
    ?? { title: '', category: defaultCategory(editableCategories.value, categoryFilter.value), content: '', output_fields: '', model_id: '', code_table: '' }
  Object.assign(form, { title, category, content, output_fields, model_id, code_table })
  unsaved.markSaved()
}

async function choose(template: PromptTemplate | null): Promise<void> {
  if (template?.id === selected.value?.id && template) return
  if (await unsaved.canLeave()) fill(template)
}

function replace(template: PromptTemplate): void {
  const index = templates.value.findIndex(item => item.id === template.id)
  if (index >= 0) templates.value.splice(index, 1, template)
  else templates.value.unshift(template)
  selected.value = template
}

/** 上传、删除文件不动表单草稿，只更新附件信息和版本号。 */
function filesChanged(template: PromptTemplate): void {
  replace(template)
}

function appendFields(): void {
  form.content = appendBlock(form.content, outputFormatBlock(splitFields(form.output_fields)))
}

async function save(): Promise<void> {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('请填写提示词标题和内容')
    return
  }
  if (!form.category) {
    ElMessage.warning('请选择模板类型')
    return
  }
  saving.value = true
  try {
    const payload = { ...form, version: selected.value?.version }
    const saved = selected.value ? await updatePrompt(selected.value.id, payload) : await createPrompt(payload)
    replace(saved)
    fill(saved)
    ElMessage.success('模板已保存')
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败，请重试'))
  } finally {
    saving.value = false
  }
}

async function remove(): Promise<void> {
  const target = selected.value
  if (!target) return
  const ok = await ElMessageBox.confirm(`删除「${target.title}」及它的 Excel、码表。已发起的批量任务和结果不受影响。`, '删除模板？', {
    type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
  }).then(() => true, () => false)
  if (!ok) return
  try {
    await deletePrompt(target.id)
    templates.value = templates.value.filter(item => item.id !== target.id)
    fill(null)
    ElMessage.success('模板已删除')
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败，请重试'))
  }
}

async function trial(): Promise<void> {
  if (!form.content.trim()) {
    ElMessage.warning('提示词内容不能为空')
    return
  }
  const useThinking = thinking.value && Boolean(trialModel.value?.supports_thinking)
  const shown = selected.value ? `［${selected.value.title}］\n${form.content}` : form.content
  await answer.send('/ai/stream/ask', {
    content: form.content,
    model_id: trialModelId.value,
    thinking: useThinking,
    prompt_id: selected.value?.id ?? null,
  }, shown, useThinking)
}
</script>

<template>
  <section class="studio">
    <h1 class="ai-sr-only">
      提问配置
    </h1>
    <aside class="ai-panel studio__rail">
      <div class="ai-panel__head">
        <h2>模板</h2>
        <el-button
          v-if="canCreate"
          size="small"
          type="primary"
          plain
          :icon="Plus"
          @click="choose(null)"
        >
          新建
        </el-button>
      </div>
      <TemplatePicker
        v-model:category="categoryFilter"
        :templates="templates"
        :categories="categories"
        :selected-id="selected?.id"
        :loading="loading"
        :error="loadError"
        empty-text="还没有模板，点「新建」开始写第一个"
        @select="choose"
      >
        <template #meta="{ item }">
          {{ item.excel_name ? `${item.excel_rows} 行测试数据` : '还没有测试数据' }}
        </template>
      </TemplatePicker>
    </aside>

    <form
      class="ai-panel studio__main"
      @submit.prevent="save"
    >
      <header class="studio__head">
        <div class="studio__title-row">
          <input
            v-model="form.title"
            class="studio__title"
            maxlength="255"
            aria-label="模板标题"
            :placeholder="selected ? '模板标题' : '给新模板起个名字'"
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
          <span class="studio__spacer" />
          <el-button
            v-if="canEdit && selected"
            text
            type="danger"
            aria-label="删除模板"
            @click="remove"
          >
            删除
          </el-button>
          <el-button
            v-if="canEdit"
            type="primary"
            native-type="submit"
            :loading="saving"
            title="Ctrl/⌘ + S"
          >
            保存
          </el-button>
        </div>
        <div class="studio__meta-row">
          <el-select
            v-model="form.category"
            class="studio__category"
            size="small"
            aria-label="模板类型"
            placeholder="类型"
            :disabled="!canEdit"
          >
            <el-option
              v-for="item in categoryOptions"
              :key="item.code"
              :label="`${item.name}类`"
              :value="item.code"
              :disabled="!item.editable"
            />
          </el-select>
          <ModelPicker
            v-model="form.model_id"
            :models="models"
            :show-thinking="false"
            size="small"
            allow-empty
            label="模板使用的模型"
          />
          <ReleaseBar
            v-if="selected"
            :template="selected"
            :can-release="canRelease"
            :dirty="unsaved.dirty.value"
            :fit="releaseFit"
            @changed="replace"
          />
        </div>
      </header>

      <!-- 标题栏固定，编辑器和下面的设置一起滚动：设置变高（如政策类模板的定时任务适配）时不挤压、不盖住编辑器。 -->
      <div class="studio__body">
        <PromptEditor
          v-model="form.content"
          :headers="selected?.excel_headers ?? []"
          :has-code="Boolean(form.code_table || selected?.code_name)"
          :disabled="!canEdit"
          @run="trial"
          @save="save"
        />

        <PromptSettings
          v-model:output-fields="form.output_fields"
          v-model:code-table="form.code_table"
          :template="selected"
          :code-tables="codeTables"
          :can-edit="canEdit"
          :can-export="canExport"
          :sample-tasks="taskFit.sampleTasks.value"
          :show-fit="taskFit.visible.value"
          :fit="taskFit.results.value"
          @append-format="appendFields"
          @files-changed="filesChanged"
        />
      </div>
    </form>

    <TrialPanel
      v-model:thinking="thinking"
      class="studio__trial"
      :answer="answer"
      :model="trialModel"
      :can-run="canEdit"
      :has-excel="Boolean(selected?.excel_name)"
      @run="trial"
    />
  </section>
</template>

<style scoped>
.studio { display: grid; grid-template-columns: 248px minmax(0, 1fr) minmax(340px, 400px); gap: 12px; height: calc(100dvh - var(--workspace-header-height) - 48px); min-height: 600px; }
.studio__rail, .studio__main, .studio__trial { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.studio__head { padding: 14px 18px 12px; border-bottom: 1px solid var(--zt-border); }
.studio__title-row, .studio__meta-row { display: flex; align-items: center; gap: 10px; min-width: 0; }
.studio__title-row .el-button { margin: 0; }
.studio__meta-row { flex-wrap: wrap; margin-top: 10px; }
.studio__title { flex: 1; min-width: 0; padding: 2px 0; border: 0; border-bottom: 1px dashed transparent; background: transparent; color: var(--zt-ink-900); font: 600 19px/1.4 var(--zt-font); outline: none; }
.studio__title:hover:not([readonly]), .studio__title:focus { border-bottom-color: var(--el-color-primary-light-5); }
.studio__title::placeholder { color: #a5b0bf; font-weight: 500; }
.studio__spacer { flex: 1; }
.studio__body { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow-y: auto; }
/* 编辑器不能被压得比输入区还矮，否则输入框会盖到下面的设置上。 */
.studio__body > .prompt-editor { flex: 1 0 auto; }
.studio__category { width: 104px; }
@media (max-width: 1360px) {
  .studio { grid-template-columns: 228px minmax(0, 1fr); grid-template-rows: minmax(0, 1fr) minmax(420px, 46vh); height: auto; }
  .studio__rail { grid-row: 1 / span 2; max-height: calc(100dvh - var(--workspace-header-height) - 48px); position: sticky; top: 0; }
  .studio__main { min-height: 640px; }
}
@media (max-width: 900px) {
  .studio { grid-template-columns: minmax(0, 1fr); grid-template-rows: none; }
  .studio__rail { grid-row: auto; position: static; max-height: 320px; }
}
</style>
