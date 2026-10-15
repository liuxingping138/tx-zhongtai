<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'

import { createPrompt, deletePrompt, listPrompts, updatePrompt, type AiModel, type PromptTemplate } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { useAuthStore } from '@/stores/auth'
import AnswerTranscript from '../shared/AnswerTranscript.vue'
import ModelPicker from '../shared/ModelPicker.vue'
import StreamStatsBar from '../shared/StreamStatsBar.vue'
import { appendBlock, outputFormatBlock, splitFields } from '../shared/aiText'
import { useAnswerStream } from '../shared/useAnswerStream'
import MentionTextarea from './MentionTextarea.vue'
import PromptFiles from './PromptFiles.vue'
import '../shared/ai.css'

const auth = useAuthStore()
const canEdit = computed(() => auth.canFull('ai.prompts'))
const canExport = computed(() => auth.canExport('ai.prompts'))
const templates = ref<PromptTemplate[]>([])
const models = ref<AiModel[]>([])
const selected = ref<PromptTemplate | null>(null)
const keyword = ref('')
const loading = ref(false)
const loadError = ref('')
const saving = ref(false)
const thinking = ref(false)
const form = reactive({ title: '', content: '', output_fields: '', model_id: '' })
const unsaved = useUnsavedForm(ref(true), () => ({ ...form }), saving)
// 编辑区一直打开，useUnsavedForm 只在打开时记基线；不先记一次，空表单也算「未保存」。
unsaved.markSaved()
const answer = useAnswerStream()

const visibleTemplates = computed(() => {
  const needle = keyword.value.trim()
  return needle ? templates.value.filter(item => item.title.includes(needle)) : templates.value
})
const trialModelId = computed(() => form.model_id || models.value.find(item => item.available)?.id || '')
const trialModel = computed(() => models.value.find(item => item.id === trialModelId.value))

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listPrompts()
    templates.value = data.items
    models.value = data.models
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
  form.title = template?.title ?? ''
  form.content = template?.content ?? ''
  form.output_fields = template?.output_fields ?? ''
  form.model_id = template?.model_id ?? ''
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
  const fields = splitFields(form.output_fields)
  if (!fields.length) {
    ElMessage.warning('先填写新增输出字段，多个字段用竖线 | 隔开')
    return
  }
  form.content = appendBlock(form.content, outputFormatBlock(fields))
}

async function save(): Promise<void> {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('请填写提示词标题和内容')
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
  <section class="workbench">
    <h1 class="ai-sr-only">
      提问配置
    </h1>
    <div class="workbench__left">
      <div class="ai-panel workbench__templates">
        <div class="ai-panel__head">
          <h2>提示词模板</h2>
          <el-button
            v-if="canEdit"
            size="small"
            :icon="Plus"
            @click="choose(null)"
          >
            新建
          </el-button>
        </div>
        <div class="workbench__search">
          <el-input
            v-model="keyword"
            :prefix-icon="Search"
            clearable
            placeholder="按标题查找"
            aria-label="按标题查找模板"
          />
        </div>
        <el-alert
          v-if="loadError"
          :title="loadError"
          type="error"
          :closable="false"
          show-icon
        />
        <ul
          v-loading="loading"
          class="ai-template-list"
          aria-label="提示词模板"
        >
          <li v-if="!loading && !visibleTemplates.length">
            <p class="ai-panel__hint workbench__empty">
              {{ templates.length ? '没有匹配的模板' : '还没有模板，点「新建」开始' }}
            </p>
          </li>
          <li
            v-for="item in visibleTemplates"
            :key="item.id"
          >
            <button
              type="button"
              :aria-current="item.id === selected?.id"
              @click="choose(item)"
            >
              <strong>{{ item.title }}</strong>
              <span>{{ item.excel_name ? `${item.excel_rows} 行` : '未上传 Excel' }} · {{ item.updated_at }}</span>
            </button>
          </li>
        </ul>
      </div>

      <form
        class="ai-panel workbench__editor"
        @submit.prevent="save"
      >
        <div class="ai-panel__head">
          <h2>{{ selected ? '编辑模板' : '新模板' }}</h2>
          <el-tag
            v-if="unsaved.dirty.value"
            type="warning"
            size="small"
          >
            未保存
          </el-tag>
        </div>
        <div class="workbench__fields">
          <span class="workbench__label">标题</span>
          <el-input
            v-model="form.title"
            maxlength="255"
            aria-label="提示词标题"
            placeholder="提示词标题"
            :disabled="!canEdit"
          />
          <span class="workbench__label">内容</span>
          <MentionTextarea
            v-model="form.content"
            label="提示词内容"
            :headers="selected?.excel_headers ?? []"
            :has-code="Boolean(selected?.code_name)"
          />
          <span class="workbench__label">新增输出字段</span>
          <div class="workbench__inline">
            <el-input
              v-model="form.output_fields"
              maxlength="2000"
              aria-label="新增输出字段"
              placeholder="多个字段用竖线隔开，例如：行业|场景|依据"
              :disabled="!canEdit"
            />
            <el-button
              :disabled="!canEdit"
              @click="appendFields"
            >
              追加格式要求
            </el-button>
          </div>
          <span class="workbench__label">模型</span>
          <ModelPicker
            v-model="form.model_id"
            v-model:thinking="thinking"
            :models="models"
            allow-empty
          />
          <span class="workbench__label">附件</span>
          <PromptFiles
            :template="selected"
            :can-edit="canEdit"
            :can-export="canExport"
            @changed="filesChanged"
          />
        </div>
        <footer class="workbench__actions">
          <el-button
            v-if="canEdit && selected"
            type="danger"
            plain
            @click="remove"
          >
            删除模板
          </el-button>
          <span class="workbench__spacer" />
          <el-button
            v-if="canEdit"
            native-type="submit"
            :loading="saving"
          >
            保存模板
          </el-button>
          <el-button
            v-if="canEdit"
            type="primary"
            :disabled="answer.running.value || !trialModel?.available"
            @click="trial"
          >
            试发提问
          </el-button>
        </footer>
      </form>
    </div>

    <div class="ai-panel workbench__output">
      <div class="ai-panel__head">
        <h2>试发结果</h2>
        <el-button
          v-if="answer.running.value"
          size="small"
          @click="answer.stop"
        >
          停止
        </el-button>
        <el-button
          v-else
          size="small"
          :disabled="!answer.messages.value.length"
          @click="answer.clear"
        >
          清空
        </el-button>
      </div>
      <AnswerTranscript
        :messages="answer.messages.value"
        :running="answer.running.value"
        empty="试发会把 @【列名】替换成 Excel 第一行的值、@【上传码表】替换成码表全文再提问。&#10;效果满意后保存模板，到「批量提问」逐行运行。"
      />
      <StreamStatsBar
        :stats="answer.stats"
        :cost="answer.cost.value"
      />
    </div>
  </section>
</template>

<style scoped>
.workbench { display: grid; grid-template-columns: minmax(420px, 1fr) minmax(340px, 1fr); gap: 16px; height: calc(100dvh - var(--workspace-header-height) - 48px); min-height: 560px; }
.workbench__left { display: flex; flex-direction: column; gap: 16px; min-height: 0; overflow: auto; }
.workbench__templates { display: flex; flex-direction: column; flex: 0 0 auto; max-height: 300px; }
.workbench__search { padding: 10px 12px 0; }
.workbench__empty { padding: 16px 8px; }
.workbench__editor { display: flex; flex-direction: column; }
.workbench__fields { display: grid; grid-template-columns: 92px minmax(0, 1fr); align-items: start; gap: 12px 12px; padding: 16px; }
.workbench__label { padding-top: 7px; color: var(--zt-ink-700); font-size: 13px; }
.workbench__inline { display: flex; gap: 8px; }
.workbench__actions { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--zt-border); }
.workbench__actions .el-button { margin: 0; }
.workbench__spacer { flex: 1; }
.workbench__output { display: flex; flex-direction: column; min-height: 0; }
@media (max-width: 1200px) {
  .workbench { grid-template-columns: minmax(0, 1fr); height: auto; }
  .workbench__output { min-height: 480px; }
}
</style>
