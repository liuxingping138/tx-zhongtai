<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { AiModel, PromptTemplate, SystemCodeTable, TemplateCategory } from '@/api/ai'
import type { ContractTask } from '@/api/aiTagging'
import ModelPicker from '../shared/ModelPicker.vue'
import { missingFieldsWarning } from '../shared/outputFields'
import { CODE_TABLE_FIELD, formatState, promptFields, refreshFormatBlock, splitFields } from '../shared/aiText'
import CodePreviewDialog from './CodePreviewDialog.vue'
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
const emit = defineEmits<{ 'files-changed': [template: PromptTemplate] }>()
const category = defineModel<string>('category', { required: true })
const modelId = defineModel<string>('modelId', { required: true })
const outputFields = defineModel<string>('outputFields', { required: true })
const codeTable = defineModel<string>('codeTable', { required: true })
/** 编辑器里的提示词：看里面的格式要求和输出字段对不对得上，需要时由这里写进去 */
const content = defineModel<string>('content', { required: true })
// 没设输出字段：结果里不会有 AI 回答的列，写清楚该填哪几个
const noFields = computed(() => missingFieldsWarning(content.value, splitFields(outputFields.value)))

// 输出字段在库里按「a|b」存，标签输入框按数组编辑；敲竖线、逗号、顿号也会断开成一个字段。
const FIELD_DELIMITER = /[|｜,，、]/
const fields = computed({
  get: () => splitFields(outputFields.value),
  set: (value: string[] | undefined) => { outputFields.value = (value ?? []).join('|') },
})
// 「追加格式要求」是一次性的：之后改了输出字段，提示词里的「返回字段」不会跟着变，模型按旧字段回就解析不出来。
const format = computed(() => formatState(content.value, fields.value))
const writtenFields = computed(() => promptFields(content.value)?.join('、') ?? '')
/** 提示词里还没有格式要求就追加整段；有了只改「返回字段」和「例如」两行。 */
function writeFormat(): void {
  content.value = refreshFormatBlock(content.value, fields.value)
}

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
  none: '提示词里要用码表时，选系统码表或上传文件（.txt、.csv、.xlsx）',
  system: `每次运行都从「码表管理」取最新的；提示词里写 @【${CODE_TABLE_FIELD}】插入码表全文`,
  upload: `Excel 只读第一个工作表，每行各格用 Tab 连成一行；上线时冻结这一份，码表更新了要重新上传。提示词里同样写 @【${CODE_TABLE_FIELD}】`,
}

function onCodeMode(value: string | number | boolean | undefined): void {
  void setCodeMode(value as CodeMode)
}

// 选了系统码表、或者已经传了文件，就能看一眼码表内容和大小。
const previewing = ref(false)
const collapsed = ref(false)
watch(
  () => props.template?.id,
  (id, prev) => { if (id !== prev) collapsed.value = Boolean(id && modelId.value && content.value.trim()) },
  { immediate: true, flush: 'post' },
)
const previewable = computed(() => (codeMode.value === 'system' ? Boolean(codeTable.value) : codeMode.value === 'upload' && Boolean(props.template?.code_name)))
const activeModelName = computed(() => props.models.find(item => item.id === modelId.value)?.name ?? '未选模型')
const activeCodeSummary = computed(() => {
  if (codeMode.value === 'none') return '不用码表'
  if (codeMode.value === 'system') return props.codeTables.find(item => item.key === codeTable.value)?.name ?? '系统码表'
  return props.template?.code_name || '上传码表'
})

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
    :class="{ 'is-collapsed': collapsed }"
    aria-label="模板设置"
  >
    <div class="config__bar">
      <span class="config__title">模板配置</span>
      <div class="config__summary">
        <span class="config__pill">{{ activeModelName }}</span>
        <span class="config__pill">{{ activeCodeSummary }}</span>
        <span class="config__pill">{{ fields.length ? `${fields.length} 个输出字段` : '自由文本输出' }}</span>
        <span
          v-if="template?.excel_name"
          class="config__pill is-sample"
        >{{ template.excel_name }}</span>
      </div>
      <button
        type="button"
        class="config__toggle"
        :aria-expanded="!collapsed"
        @click="collapsed = !collapsed"
      >
        {{ collapsed ? '展开配置 ▾' : '收起配置 ▴' }}
      </button>
    </div>

    <div
      v-show="!collapsed"
      class="config__body"
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
            <span
              v-if="noFields"
              class="config__stale"
              role="status"
            >{{ noFields }}</span>
            <span
              v-else-if="format === 'stale'"
              class="config__stale"
              role="status"
            >提示词里写的返回字段还是「{{ writtenFields }}」，和这里对不上，模型会按旧字段回</span>
            <span v-else>{{ fields.length ? `共 ${fields.length} 个，` : '' }}模型按这些字段返回 JSON{{ format === 'match' ? '，提示词里的格式要求已对上' : '' }}</span>
            <el-button
              v-if="format !== 'match'"
              link
              :type="format === 'stale' ? 'warning' : 'primary'"
              :disabled="!canEdit || !fields.length"
              @click="writeFormat"
            >
              {{ format === 'stale' ? '更新提示词里的格式要求' : '把格式要求追加到提示词' }}
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
    </div>
  </section>
</template>

<style scoped>
.config { border-bottom: 1px solid var(--zt-border); background: var(--zt-surface-subtle); }
.config__bar { display: flex; align-items: center; gap: 8px; padding: 8px 16px; min-height: 40px; }
.config__title { flex: none; color: var(--zt-ink-700); font-size: 12.5px; font-weight: 600; }
.config__summary { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; flex-wrap: wrap; }
.config__pill { display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border: 1px solid var(--zt-border); border-radius: 999px; background: var(--zt-panel); color: var(--zt-ink-700); font-size: 11.5px; white-space: nowrap; }
.config__pill.is-sample { border-color: var(--el-color-primary-light-7); background: var(--el-color-primary-light-9); color: var(--zt-blue-700); }
.config__toggle { flex: none; margin-left: auto; padding: 3px 8px; border: 0; border-radius: 6px; background: transparent; color: var(--zt-blue-600); font: 500 12px/1.4 var(--zt-font); cursor: pointer; }
.config__toggle:hover { background: var(--el-color-primary-light-9); }
.config__body { display: grid; gap: 10px; padding: 4px 16px 12px; border-top: 1px solid var(--zt-divider); }
.config__row { display: grid; grid-template-columns: 64px minmax(0, 1fr); align-items: start; gap: 10px; }
.config__row--inline { display: flex; flex-wrap: wrap; gap: 10px 18px; }
.config__item { display: flex; align-items: center; gap: 10px; min-width: 0; }
.config__item > span, .config__label { flex: none; width: 64px; color: var(--zt-ink-500); font-size: 12.5px; line-height: 30px; }
.config__item--grow { flex: 1 1 220px; }
.config__item--grow > :last-child { flex: 1; min-width: 0; }
.config__category { width: 116px; }
.config__item--grow :deep(.model-picker__select) { width: 100%; }
.config__code { display: grid; gap: 4px; min-width: 0; }
.config__code-line { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; min-height: 30px; min-width: 0; }
.config__code-select { width: 240px; }
.config__code-file { flex: 1; min-width: 200px; }
.config__fields { display: grid; gap: 4px; min-width: 0; }
.config__fields-foot { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 4px 12px; color: var(--zt-ink-500); font-size: 12px; }
.config__tip { margin: 2px 0 0; color: var(--zt-ink-500); font-size: 12px; }
.config__stale { color: var(--zt-warning-text); }
</style>
