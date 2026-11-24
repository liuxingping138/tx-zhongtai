<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { AiModel, PromptTemplate, SystemCodeTable, TemplateCategory } from '@/api/ai'
import type { SampleOptions } from '@/api/aiTagging'
import ModelPicker from '../shared/ModelPicker.vue'
import { CODE_TABLE_FIELD } from '../shared/aiText'
import CodePreviewDialog from './CodePreviewDialog.vue'
import PromptFiles from './PromptFiles.vue'
import TaskFit from './TaskFit.vue'
import type { TaskFitResult } from './taskFit'
import type { TemplateFiles } from './useTemplateFiles'

/** 提示词上方紧凑配置区：类型、模型、码表（含预览）、测试样本（上传/从库取）及政策任务适配，全部同页一眼可见。 */
const props = defineProps<{
  template: PromptTemplate | null
  categories: TemplateCategory[]
  models: AiModel[]
  codeTables: SystemCodeTable[]
  files: TemplateFiles
  canEdit: boolean
  canExport: boolean
  sampleOptions: SampleOptions
  showFit: boolean
  fit: TaskFitResult[]
}>()
const emit = defineEmits<{ 'files-changed': [template: PromptTemplate] }>()
const category = defineModel<string>('category', { required: true })
const modelId = defineModel<string>('modelId', { required: true })
const codeTable = defineModel<string>('codeTable', { required: true })

type CodeMode = 'none' | 'system' | 'upload'
const wantUpload = ref(false)
watch(() => props.template?.id, () => { wantUpload.value = false })
const codeMode = computed<CodeMode>(() => {
  if (codeTable.value) return 'system'
  return props.template?.code_name || wantUpload.value ? 'upload' : 'none'
})
const CODE_TIPS: Record<CodeMode, string> = {
  none: '提示词里要用码表时，选系统码表或上传文件（.txt、.csv、.xlsx）',
  system: `每次运行都从「码表管理」取最新的；提示词里写 @【${CODE_TABLE_FIELD}】插入码表全文`,
  upload: `Excel 只读第一个工作表，每行各格用 Tab 连成一行；上线时冻结这一份。提示词里同样写 @【${CODE_TABLE_FIELD}】`,
}

const previewing = ref(false)
const previewable = computed(() => (codeMode.value === 'system' ? Boolean(codeTable.value) : codeMode.value === 'upload' && Boolean(props.template?.code_name)))

function onCodeMode(value: string | number | boolean | undefined): void {
  void setCodeMode(value as CodeMode)
}

async function setCodeMode(next: CodeMode): Promise<void> {
  if (next === codeMode.value) return
  if (next === 'system') {
    wantUpload.value = false
    codeTable.value = props.codeTables[0]?.key ?? ''
    return
  }
  codeTable.value = ''
  wantUpload.value = next === 'upload'
  const uploaded = props.template?.code_name
  if (next === 'none' && uploaded) {
    await props.files.remove('code', `不用码表要删掉已上传的「${uploaded}」。已发起的任务和线上版本不受影响。`)
  }
}
</script>

<template>
  <section
    class="config"
    aria-label="模板设置"
  >
    <div class="config__row config__row--inline">
      <label class="config__item">
        <span>类型</span>
        <el-select
          v-model="category"
          class="config__category"
          size="small"
          aria-label="模板类型"
          placeholder="选择类型"
          :disabled="!canEdit"
        >
          <el-option
            v-for="item in categories"
            :key="item.code"
            :label="`${item.name}类`"
            :value="item.code"
            :disabled="!item.editable"
          />
        </el-select>
      </label>
      <div class="config__item config__item--grow">
        <span>模型</span>
        <ModelPicker
          v-model="modelId"
          :models="models"
          :show-thinking="false"
          :disabled="!canEdit"
          allow-empty
          label="模板使用的模型"
        />
      </div>
    </div>

    <div class="config__row">
      <span
        class="config__label"
        :title="CODE_TIPS[codeMode]"
      >码表</span>
      <div
        class="config__code"
        :title="CODE_TIPS[codeMode]"
      >
        <div class="config__code-line">
          <el-radio-group
            :model-value="codeMode"
            size="small"
            class="ai-seg"
            aria-label="码表来源"
            :disabled="!canEdit"
            @change="onCodeMode"
          >
            <el-radio-button value="none">
              不用码表
            </el-radio-button>
            <el-radio-button value="system">
              系统码表
            </el-radio-button>
            <el-radio-button value="upload">
              上传文件
            </el-radio-button>
          </el-radio-group>
          <el-select
            v-if="codeMode === 'system'"
            v-model="codeTable"
            class="config__code-select"
            size="small"
            aria-label="系统码表"
            :disabled="!canEdit"
          >
            <el-option
              v-for="item in codeTables"
              :key="item.key"
              :label="item.name"
              :value="item.key"
            />
          </el-select>
          <PromptFiles
            v-else-if="codeMode === 'upload'"
            kind="code"
            class="config__code-file"
            :template="template"
            :files="files"
            :can-edit="canEdit"
            :can-export="canExport"
          />
          <el-button
            v-if="previewable"
            link
            type="primary"
            size="small"
            @click="previewing = true"
          >
            预览码表
          </el-button>
        </div>
        <CodePreviewDialog
          v-model="previewing"
          :system-key="codeMode === 'system' ? codeTable : ''"
          :prompt-id="template?.id ?? ''"
        />
      </div>
    </div>

    <div class="config__row">
      <span
        class="config__label"
        title="列名就是提示词里能插的变量；只给试发和样本试跑用"
      >测试样本</span>
      <PromptFiles
        kind="excel"
        :template="template"
        :files="files"
        :can-edit="canEdit"
        :can-export="canExport"
        :sample-options="sampleOptions"
        @changed="item => emit('files-changed', item)"
      />
    </div>

    <div
      v-if="showFit"
      class="config__row"
    >
      <span class="config__label">定时任务</span>
      <TaskFit :results="fit" />
    </div>
  </section>
</template>

<style scoped>
.config { display: grid; gap: 5px; padding: 8px 16px; border-bottom: 1px solid var(--zt-border); background: var(--zt-surface-subtle); }
.config__row { display: grid; grid-template-columns: 56px minmax(0, 1fr); align-items: center; gap: 8px; min-height: 26px; }
.config__row--inline { display: flex; flex-wrap: wrap; gap: 6px 14px; }
.config__item { display: flex; align-items: center; gap: 8px; min-width: 0; }
.config__item > span, .config__label { flex: none; width: 56px; color: var(--zt-ink-500); font-size: 12px; font-weight: 600; }
.config__item--grow { flex: 1 1 220px; }
.config__item--grow > :last-child { flex: 1; min-width: 0; }
.config__category { width: 96px; }
.config__item--grow :deep(.model-picker__select) { width: 100%; }
.config__code { min-width: 0; }
.config__code-line { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 8px; min-width: 0; }
.config__code-select { width: 184px; }
.config__code-file { flex: 1; min-width: 160px; }
</style>
