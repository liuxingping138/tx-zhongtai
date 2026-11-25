<script setup lang="ts">
import { computed, ref } from 'vue'

import type { PromptFileKind, PromptTemplate } from '@/api/ai'
import type { SampleOptions } from '@/api/aiTagging'
import SampleDialog from './SampleDialog.vue'
import type { TemplateFiles } from './useTemplateFiles'

/** 模板的一个附件：测试样本（.xlsx）或上传的码表（.txt）。上传、移除、下载都交给编辑页的 files；新模板上传时顺便保存。
 * sampleOptions：政策类模板能从数据库取测试样本（和正式打标的输入一致），tasks 为空就不显示这个入口。 */
const props = defineProps<{
  template: PromptTemplate | null
  kind: PromptFileKind
  files: TemplateFiles
  canEdit: boolean
  canExport: boolean
  sampleOptions?: SampleOptions
}>()
const emit = defineEmits<{ changed: [template: PromptTemplate] }>()
const sampling = ref(false)

const EMPTY: Record<PromptFileKind, string> = {
  excel: '未绑定测试样本（.xlsx 首行为表头列名，仅用于试发与样本试跑）',
  code: '尚未上传码表文件（支持 .txt、.csv 或 .xlsx）',
}
const REMOVE_LABEL: Record<PromptFileKind, string> = {
  excel: '移除样本',
  code: '移除码表',
}
const name = computed(() => (props.kind === 'excel' ? props.template?.excel_name : props.template?.code_name) ?? '')

async function openSampling(): Promise<void> {
  if (await props.files.ensure()) sampling.value = true
}

defineExpose({ openSampling })
</script>

<template>
  <div class="prompt-files">
    <div class="prompt-files__row">
      <span
        class="prompt-files__name"
        :class="{ 'is-empty': !name }"
      >
        {{ name || EMPTY[kind] }}
        <template v-if="kind === 'excel' && name">（共 {{ template?.excel_rows }} 行）</template>
      </span>
      <el-button
        v-if="canEdit"
        size="small"
        plain
        :loading="files.busy.value === kind"
        @click="files.pick(kind)"
      >
        {{ name ? '重新上传' : kind === 'code' ? '上传码表' : '上传 Excel' }}
      </el-button>
      <el-button
        v-if="kind === 'excel' && canEdit && sampleOptions?.tasks.length"
        size="small"
        type="primary"
        plain
        :disabled="files.busy.value !== null"
        @click="openSampling"
      >
        从政策库取数
      </el-button>
      <el-button
        v-if="canExport && name"
        link
        type="primary"
        @click="files.download(kind)"
      >
        下载
      </el-button>
      <el-button
        v-if="canEdit && name"
        link
        type="danger"
        :disabled="files.busy.value !== null"
        @click="files.remove(kind)"
      >
        {{ REMOVE_LABEL[kind] }}
      </el-button>
    </div>
    <SampleDialog
      v-if="template"
      v-model="sampling"
      :template="template"
      :fields="sampleOptions?.draftFields"
      :tasks="sampleOptions?.tasks ?? []"
      :provinces="sampleOptions?.provinces"
      :industries="sampleOptions?.industries"
      :save-rows="files.saveRows"
      @done="item => emit('changed', item)"
    />
  </div>
</template>

<style scoped>
.prompt-files { display: grid; gap: 4px; min-width: 0; width: 100%; }
.prompt-files__row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 10px; min-height: 28px; }
.prompt-files__row .el-button { margin: 0; font-size: 12.5px; }
.prompt-files__name {
  flex: 1 1 160px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--zt-ink-900); font-size: 12.5px; font-weight: 500;
}
.prompt-files__name.is-empty { color: var(--zt-ink-500); font-weight: 400; }
</style>
