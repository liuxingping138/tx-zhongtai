<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { AiModel, PromptTemplate, SystemCodeTable, TemplateCategory } from '@/api/ai'
import type { ContractTask } from '@/api/aiTagging'
import ModelPicker from '../shared/ModelPicker.vue'
import { CODE_TABLE_FIELD, splitFields } from '../shared/aiText'
import PromptFiles from './PromptFiles.vue'
import TaskFit from './TaskFit.vue'
import type { TaskFitResult } from './taskFit'
import type { TemplateFiles } from './useTemplateFiles'

/** 编辑器下方的模板设置：常驻显示，不收起——输出字段、模型、码表决定结果长什么样，写提示词时要一直看得到。 */
const props = defineProps<{
  template: PromptTemplate | null
  categories: TemplateCategory[]
  models: AiModel[]
  codeTables: SystemCodeTable[]
  files: TemplateFiles
  canEdit: boolean
  canExport: boolean
  /** 政策类模板：三个打标任务的约定（取测试样本用）和按草稿的适配检查；不是政策类时不显示 */
  sampleTasks: ContractTask[]
  showFit: boolean
  fit: TaskFitResult[]
}>()
const emit = defineEmits<{ 'append-format': []; 'files-changed': [template: PromptTemplate] }>()
const category = defineModel<string>('category', { required: true })
const modelId = defineModel<string>('modelId', { required: true })
const outputFields = defineModel<string>('outputFields', { required: true })
const codeTable = defineModel<string>('codeTable', { required: true })

// 输出字段在库里按「a|b」存，标签输入框按数组编辑；敲竖线、逗号、顿号也会断开成一个字段。
const FIELD_DELIMITER = /[|｜,，、]/
const fields = computed({
  get: () => splitFields(outputFields.value),
  set: (value: string[] | undefined) => { outputFields.value = (value ?? []).join('|') },
})

/**
 * 码表三选一。库里只有两样：code_table 存系统码表的键，空串时用上传的 .txt（有的话）。
 * 「上传文件」选了还没传时库里仍是空，先记在页面上；「不用码表」要把已上传的文件删掉才真的不用。
 */
type CodeMode = 'none' | 'system' | 'upload'
const wantUpload = ref(false)
watch(() => props.template?.id, () => { wantUpload.value = false })
const codeMode = computed<CodeMode>(() => {
  if (codeTable.value) return 'system'
  return props.template?.code_name || wantUpload.value ? 'upload' : 'none'
})
const CODE_TIPS: Record<CodeMode, string> = {
  none: '提示词里要用码表时，选系统码表或上传 .txt',
  system: `每次运行都从「码表管理」取最新的；提示词里写 @【${CODE_TABLE_FIELD}】插入码表全文`,
  upload: `上线时冻结这一份，码表更新了要重新上传；提示词里同样写 @【${CODE_TABLE_FIELD}】插入码表全文`,
}

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
      <span class="config__label">码表</span>
      <div class="config__code">
        <div class="config__code-line">
          <el-radio-group
            :model-value="codeMode"
            size="small"
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
        </div>
        <p class="config__tip">
          {{ CODE_TIPS[codeMode] }}
        </p>
      </div>
    </div>

    <div class="config__row">
      <span class="config__label">输出字段</span>
      <div class="config__fields">
        <el-input-tag
          v-model="fields"
          aria-label="输出字段"
          placeholder="输入字段名回车，如：行业"
          size="small"
          :delimiter="FIELD_DELIMITER"
          :disabled="!canEdit"
          clearable
          draggable
        />
        <div class="config__fields-foot">
          <span>{{ fields.length ? `共 ${fields.length} 个，` : '' }}模型按这些字段返回 JSON</span>
          <el-button
            link
            type="primary"
            :disabled="!canEdit || !fields.length"
            @click="emit('append-format')"
          >
            把格式要求追加到提示词
          </el-button>
        </div>
      </div>
    </div>

    <div class="config__row">
      <span class="config__label">测试样本</span>
      <div>
        <PromptFiles
          kind="excel"
          :template="template"
          :files="files"
          :can-edit="canEdit"
          :can-export="canExport"
          :sample-tasks="sampleTasks"
          @changed="item => emit('files-changed', item)"
        />
        <p class="config__tip">
          列名就是提示词里能插的变量；只给试发和样本试跑用，正式的批量任务另外上传数据
        </p>
      </div>
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
.config { display: grid; gap: 12px; padding: 14px 18px 16px; border-top: 1px solid var(--zt-border); background: var(--zt-surface-subtle); }
.config__row { display: grid; grid-template-columns: 64px minmax(0, 1fr); align-items: start; gap: 12px; }
.config__row--inline { display: flex; flex-wrap: wrap; gap: 10px 20px; }
.config__item { display: flex; align-items: center; gap: 12px; min-width: 0; }
.config__item > span, .config__label { flex: none; width: 64px; color: var(--zt-ink-500); font-size: 13px; line-height: 32px; }
.config__item--grow { flex: 1 1 220px; }
.config__item--grow > :last-child { flex: 1; min-width: 0; }
.config__category { width: 120px; }
.config__item--grow :deep(.model-picker__select) { width: 100%; }
.config__code { display: grid; gap: 4px; min-width: 0; }
.config__code-line { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; min-height: 32px; min-width: 0; }
.config__code-select { width: 260px; }
.config__code-file { flex: 1; min-width: 200px; }
/* 十几个输出字段时标签框最多三行，再多在框里滚动，不把测试样本挤出视野。 */
.config__fields { display: grid; gap: 4px; min-width: 0; }
.config__fields-foot { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 4px 12px; color: var(--zt-ink-500); font-size: 12px; }
.config__tip { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 12px; }
</style>
