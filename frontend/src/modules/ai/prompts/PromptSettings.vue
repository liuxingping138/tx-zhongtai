<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowDown, CircleCheckFilled, Collection, Files, WarningFilled } from '@element-plus/icons-vue'

import type { AiModel, PromptTemplate, SystemCodeTable, TemplateCategory } from '@/api/ai'
import type { SampleOptions } from '@/api/aiTagging'
import ModelPicker from '../shared/ModelPicker.vue'
import { CODE_TABLE_FIELD } from '../shared/aiText'
import CodePreviewDialog from './CodePreviewDialog.vue'
import PromptFiles from './PromptFiles.vue'
import TaskFit from './TaskFit.vue'
import type { TaskFitResult } from './taskFit'
import type { TemplateFiles } from './useTemplateFiles'

/** 40px 单行吸顶 Studio 配置丝带 + 按需滑出二级抽屉：释放首屏高度给提示词编辑画布，滚动正文时配置丝带常驻不丢。 */
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
type TrayKind = 'code' | 'excel' | 'fit' | null

const openTray = ref<TrayKind>(null)
const wantUpload = ref(false)
const previewing = ref(false)
const excelFilesRef = ref<{ openSampling: () => Promise<void> } | null>(null)

watch(() => props.template?.id, () => {
  wantUpload.value = false
  openTray.value = null
})

const codeMode = computed<CodeMode>(() => {
  if (codeTable.value) return 'system'
  return props.template?.code_name || wantUpload.value ? 'upload' : 'none'
})

const CODE_TIPS: Record<CodeMode, string> = {
  none: '提示词里要用标准字典时，可选系统实时码表或上传静态文件（.txt、.csv、.xlsx）。',
  system: `每次运行实时从「码表管理」拉取最新内容；在提示词里写 @【${CODE_TABLE_FIELD}】 即可注入全文。`,
  upload: `Excel 只读首个工作表（Tab 分隔），模板上线时冻结当前版本；提示词里同样写 @【${CODE_TABLE_FIELD}】。`,
}

const activeCodeChip = computed(() => {
  if (codeMode.value === 'system') {
    const label = props.codeTables.find(item => item.key === codeTable.value)?.name ?? codeTable.value
    return `码表：${label}`
  }
  if (codeMode.value === 'upload') return `码表：${props.template?.code_name || '待上传'}`
  return '码表：未启用'
})

const activeSampleChip = computed(() => {
  if (!props.template?.excel_name) return '样本：未绑定'
  const baseName = props.template.excel_name.replace(/\.(xlsx|xls|csv|txt)$/i, '')
  return `样本：${baseName} (${props.template.excel_rows})`
})

const previewable = computed(() =>
  (codeMode.value === 'system' ? Boolean(codeTable.value) : codeMode.value === 'upload' && Boolean(props.template?.code_name)))

const fitBadge = computed(() => {
  const relevant = props.fit.filter(item => !item.skip)
  if (!relevant.length) return { tone: '', text: '任务适配' }
  const errors = relevant.filter(item => item.check.errors.length > 0).length
  if (errors) return { tone: 'is-error', text: `适配：${errors} 项需改` }
  const warns = relevant.filter(item => item.check.warnings.length > 0).length
  if (warns) return { tone: 'is-warn', text: `适配：可用·${warns}提醒` }
  return { tone: 'is-ok', text: `已适配 ${relevant.length} 任务` }
})

function toggleTray(kind: Exclude<TrayKind, null>): void {
  openTray.value = openTray.value === kind ? null : kind
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
    await props.files.remove('code', `不用码表要移除已上传的「${uploaded}」。已发起的任务和线上版本不受影响。`)
  }
}

defineExpose({
  openSampleDb: () => excelFilesRef.value?.openSampling(),
})
</script>

<template>
  <section
    class="studio-config"
    aria-label="模板设置"
  >
    <div class="studio-ribbon">
      <el-select
        v-model="category"
        class="studio-ribbon__cat"
        size="small"
        aria-label="模板类型"
        placeholder="类型"
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

      <div class="studio-ribbon__model">
        <ModelPicker
          v-model="modelId"
          :models="models"
          :show-thinking="false"
          compact
          size="small"
          :disabled="!canEdit"
          allow-empty
          label="模板使用的模型"
        />
      </div>

      <button
        type="button"
        class="studio-chip"
        :class="{ 'is-open': openTray === 'code', 'is-active': openTray !== 'code' && codeMode !== 'none' }"
        :aria-expanded="openTray === 'code'"
        :title="CODE_TIPS[codeMode]"
        @click="toggleTray('code')"
      >
        <el-icon class="studio-chip__icon">
          <Collection />
        </el-icon>
        <span>{{ activeCodeChip }}</span>
        <el-icon class="studio-chip__caret">
          <ArrowDown />
        </el-icon>
      </button>

      <button
        type="button"
        class="studio-chip"
        :class="{ 'is-open': openTray === 'excel', 'is-active': openTray !== 'excel' && Boolean(template?.excel_name) }"
        :aria-expanded="openTray === 'excel'"
        :title="template?.excel_name ? `${template.excel_name}（${template.excel_rows} 行）` : '上传测试样本或从政策库取数'"
        @click="toggleTray('excel')"
      >
        <el-icon class="studio-chip__icon">
          <Files />
        </el-icon>
        <span>{{ activeSampleChip }}</span>
        <el-icon class="studio-chip__caret">
          <ArrowDown />
        </el-icon>
      </button>

      <button
        v-if="showFit"
        type="button"
        class="studio-chip studio-chip--right"
        :class="[openTray === 'fit' ? 'is-open' : fitBadge.tone]"
        :aria-expanded="openTray === 'fit'"
        title="展开查看 5 个政策定时任务的输入变量与输出字段适配检查"
        @click="toggleTray('fit')"
      >
        <el-icon class="studio-chip__icon">
          <WarningFilled v-if="fitBadge.tone === 'is-warn' || fitBadge.tone === 'is-error'" />
          <CircleCheckFilled v-else />
        </el-icon>
        <span>{{ fitBadge.text }}</span>
        <el-icon class="studio-chip__caret">
          <ArrowDown />
        </el-icon>
      </button>
    </div>

    <div
      v-if="openTray === 'code'"
      class="studio-tray"
      role="region"
      aria-label="码表设置详情"
    >
      <div class="studio-tray__line">
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
          class="studio-tray__select"
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
          class="studio-tray__file"
          :template="template"
          :files="files"
          :can-edit="canEdit"
          :can-export="canExport"
        />

        <el-button
          v-if="previewable"
          size="small"
          plain
          @click="previewing = true"
        >
          预览码表
        </el-button>
      </div>
      <p class="studio-tray__hint">
        {{ CODE_TIPS[codeMode] }}
      </p>
    </div>

    <!-- v-show 保持挂载：新建冷启动引导里的「从政策库取数」随时可直接拉起 SampleDialog -->
    <div
      v-show="openTray === 'excel'"
      class="studio-tray"
      role="region"
      aria-label="测试样本设置详情"
    >
      <PromptFiles
        ref="excelFilesRef"
        kind="excel"
        :template="template"
        :files="files"
        :can-edit="canEdit"
        :can-export="canExport"
        :sample-options="sampleOptions"
        @changed="item => emit('files-changed', item)"
      />
      <p
        v-if="template?.excel_headers.length"
        class="studio-tray__hint"
      >
        已识别表头列：{{ template.excel_headers.map(col => `@【${col}】`).join('、') }}
      </p>
    </div>

    <div
      v-if="openTray === 'fit' && showFit"
      class="studio-tray"
      role="region"
      aria-label="政策定时任务适配检查"
    >
      <TaskFit :results="fit" />
    </div>

    <CodePreviewDialog
      v-model="previewing"
      :system-key="codeMode === 'system' ? codeTable : ''"
      :prompt-id="template?.id ?? ''"
    />
  </section>
</template>

<style scoped>
.studio-config { flex: none; border-bottom: 1px solid var(--zt-border); background: var(--zt-surface-subtle); }

.studio-ribbon {
  display: flex; align-items: center; gap: 5px; min-height: 44px; padding: 7px 10px;
  flex-wrap: wrap;
}
.studio-ribbon__cat { width: 86px; flex: none; }
.studio-ribbon__model { flex: 0 1 182px; min-width: 146px; }
.studio-ribbon__model :deep(.model-picker) { flex-wrap: nowrap; gap: 6px; width: 100%; }
.studio-ribbon__model :deep(.model-picker__select--small) { width: 100%; }
.studio-ribbon__model :deep(.model-picker__off) { display: none; }
.studio-ribbon :deep(.el-select__wrapper) {
  min-height: 30px; border-radius: 8px;
  background: var(--zt-btn-sec-bg);
  box-shadow: 0 0 0 1px var(--zt-border-strong) inset, var(--zt-btn-sec-shadow);
  font-size: 12.5px; font-weight: 550;
}
.studio-ribbon :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--zt-blue-600) inset, var(--zt-btn-sec-hover-shadow);
}

.studio-chip {
  display: inline-flex; align-items: center; gap: 5px; height: 30px; padding: 0 10px;
  border: 1px solid var(--zt-border-strong); border-radius: 8px;
  background: var(--zt-btn-sec-bg); box-shadow: var(--zt-btn-sec-shadow); color: var(--zt-ink-900);
  font: 550 12px/1 var(--zt-font); min-width: 0; max-width: min(250px, 48%); cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease, transform 0.12s ease;
}
.studio-chip__icon { flex: none; font-size: 13px; color: var(--zt-blue-600); }
.studio-chip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.studio-chip__caret { flex: none; font-size: 11px; color: var(--zt-ink-400); transition: transform 0.15s ease; }
.studio-chip.is-open .studio-chip__caret { transform: rotate(180deg); color: var(--zt-blue-600); }
.studio-chip:hover {
  border-color: var(--zt-blue-600); background: var(--zt-btn-sec-hover-bg);
  color: var(--zt-blue-600); box-shadow: var(--zt-btn-sec-hover-shadow); transform: translateY(-0.5px);
}
.studio-chip.is-open {
  border-color: var(--el-color-primary-light-5); background: var(--el-color-primary-light-9); color: var(--zt-blue-600);
}
.studio-chip.is-active { border-color: var(--el-color-primary-light-5); }
.studio-chip.is-ok { border-color: var(--zt-success-border); background: var(--zt-success-soft); color: var(--zt-success-text); }
.studio-chip.is-ok .studio-chip__icon { color: var(--zt-success); }
.studio-chip.is-warn { border-color: var(--zt-warning-border); background: var(--zt-warning-soft); color: var(--zt-warning-text); }
.studio-chip.is-warn .studio-chip__icon { color: var(--zt-warning); }
.studio-chip.is-error { border-color: var(--zt-danger-border); background: var(--zt-danger-soft); color: var(--zt-danger-text); }
.studio-chip.is-error .studio-chip__icon { color: var(--zt-danger-text); }
.studio-chip--right { margin-left: auto; }

.studio-tray {
  padding: 10px 14px; border-top: 1px solid var(--zt-divider); background: var(--zt-panel);
}
.studio-tray__line { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.studio-tray__line .el-button { margin: 0; }
.studio-tray__select { width: 196px; }
.studio-tray__file { flex: 1 1 200px; min-width: 0; }
.studio-tray__hint { margin: 6px 0 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.5; }
</style>
