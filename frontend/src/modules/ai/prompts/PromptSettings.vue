<script setup lang="ts">
import { computed } from 'vue'

import type { PromptTemplate, SystemCodeTable } from '@/api/ai'
import type { ContractTask } from '@/api/aiTagging'
import { splitFields } from '../shared/aiText'
import PromptFiles from './PromptFiles.vue'
import TaskFit from './TaskFit.vue'
import type { TaskFitResult } from './taskFit'

/** 编辑器下方：输出字段（标签输入）、码表来源、测试数据（Excel 和上传的码表）。 */
defineProps<{
  template: PromptTemplate | null
  codeTables: SystemCodeTable[]
  canEdit: boolean
  canExport: boolean
  /** 政策类模板：三个打标任务的约定（取测试数据用）和按草稿的适配检查；不是政策类时不显示 */
  sampleTasks: ContractTask[]
  showFit: boolean
  fit: TaskFitResult[]
}>()
const emit = defineEmits<{ 'append-format': []; 'files-changed': [template: PromptTemplate] }>()
const outputFields = defineModel<string>('outputFields', { required: true })
const codeTable = defineModel<string>('codeTable', { required: true })

// 输出字段在库里按「a|b」存，标签输入框按数组编辑；敲竖线、逗号、顿号也会断开成一个字段。
const FIELD_DELIMITER = /[|｜,，、]/
const fields = computed({
  get: () => splitFields(outputFields.value),
  set: (value: string[] | undefined) => { outputFields.value = (value ?? []).join('|') },
})
// 「上传的码表文件」在库里存空串；下拉框把空串当成没选，页面上换一个值表示它。
const UPLOADED_CODE = 'uploaded'
const codeSource = computed({
  get: () => codeTable.value || UPLOADED_CODE,
  set: (value: string) => { codeTable.value = value === UPLOADED_CODE ? '' : value },
})
</script>

<template>
  <section
    class="settings__config"
    aria-label="输出和数据"
  >
    <div class="settings__tile settings__tile--wide">
      <div class="settings__tile-head">
        <h3>输出字段</h3>
        <el-button
          link
          type="primary"
          :disabled="!canEdit || !fields.length"
          @click="emit('append-format')"
        >
          把格式要求追加到提示词
        </el-button>
      </div>
      <el-input-tag
        v-model="fields"
        aria-label="输出字段"
        placeholder="输入字段名回车，如：行业"
        :delimiter="FIELD_DELIMITER"
        :disabled="!canEdit"
        clearable
        draggable
      />
      <p class="settings__tip">
        模型按这些字段返回 JSON，批量结果每个字段一列
      </p>
    </div>
    <div class="settings__tile">
      <div class="settings__tile-head">
        <h3>码表</h3>
      </div>
      <el-select
        v-model="codeSource"
        aria-label="码表来源"
        :disabled="!canEdit"
      >
        <el-option
          label="上传的码表文件"
          :value="UPLOADED_CODE"
        />
        <el-option
          v-for="item in codeTables"
          :key="item.key"
          :label="`系统${item.name}`"
          :value="item.key"
        />
      </el-select>
      <p class="settings__tip">
        {{ codeTable ? '每次提问取码表最新内容，用 @【上传码表】引用' : '在下方上传 .txt 码表，没有就不用码表' }}
      </p>
    </div>
    <div class="settings__tile">
      <div class="settings__tile-head">
        <h3>测试数据</h3>
      </div>
      <PromptFiles
        :template="template"
        :can-edit="canEdit"
        :can-export="canExport"
        :system-code="Boolean(codeTable)"
        :sample-tasks="sampleTasks"
        @changed="item => emit('files-changed', item)"
      />
    </div>
    <div
      v-if="showFit"
      class="settings__tile settings__tile--fit"
    >
      <div class="settings__tile-head">
        <h3>定时任务适配</h3>
        <span class="settings__tip">按当前草稿检查；任务设置里选模板时也会核对</span>
      </div>
      <TaskFit :results="fit" />
    </div>
  </section>
</template>

<style scoped>
.settings__config { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr); border-top: 1px solid var(--zt-border); }
.settings__tile { display: flex; flex-direction: column; gap: 6px; min-width: 0; padding: 12px 18px 14px; }
.settings__tile--wide { grid-column: 1 / -1; border-bottom: 1px solid var(--zt-border); }
.settings__tile--wide + .settings__tile + .settings__tile { border-left: 1px solid var(--zt-border); }
.settings__tile--fit { grid-column: 1 / -1; border-top: 1px solid var(--zt-border); }
.settings__tile-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 24px; }
.settings__tile h3 { margin: 0; color: var(--zt-ink-700); font-size: 13px; font-weight: 600; }
.settings__tip { margin: 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.5; }
/* 标签输入框里真正的 input 不要再套一层全局聚焦框，外框已经变色。 */
.settings__tile :deep(.el-input-tag__input:focus-visible) { outline: none; box-shadow: none; }
@media (max-width: 900px) {
  .settings__config { grid-template-columns: minmax(0, 1fr); }
  .settings__tile--wide + .settings__tile + .settings__tile { border-left: 0; border-top: 1px solid var(--zt-border); }
}
</style>
