<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { deletePromptFile, uploadPromptFile, type PromptFileKind, type PromptTemplate } from '@/api/ai'
import type { ContractTask } from '@/api/aiTagging'
import { errorMessage } from '@/api/errors'
import { downloadPromptFile } from '../shared/downloads'
import SampleDialog from './SampleDialog.vue'

/** 模板的一个附件：测试样本（.xlsx）或上传的码表（.txt）。
 * sampleTasks：政策类模板能从数据库取测试样本（和正式打标的输入一致），空数组就不显示这个入口。 */
const props = defineProps<{
  template: PromptTemplate | null
  kind: PromptFileKind
  canEdit: boolean
  canExport: boolean
  sampleTasks?: ContractTask[]
}>()
const sampling = ref(false)
const emit = defineEmits<{ changed: [template: PromptTemplate] }>()
const busy = ref<PromptFileKind | null>(null)
const pickers = ref<Record<PromptFileKind, HTMLInputElement | null>>({ excel: null, code: null })

const SLOTS: Record<PromptFileKind, { kind: PromptFileKind; accept: string; empty: string }> = {
  excel: { kind: 'excel', accept: '.xlsx', empty: '未上传，.xlsx 第一行是表头' },
  code: { kind: 'code', accept: '.txt', empty: '未上传码表 .txt' },
}

const slots = computed(() => [SLOTS[props.kind]])

function fileName(kind: PromptFileKind): string {
  if (!props.template) return ''
  return kind === 'excel' ? props.template.excel_name : props.template.code_name
}

async function upload(kind: PromptFileKind, event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ''
  if (!file || !props.template) return
  busy.value = kind
  try {
    emit('changed', await uploadPromptFile(props.template.id, kind, file))
    ElMessage.success(kind === 'excel' ? '测试样本已上传' : '码表已上传')
  } catch (error) {
    ElMessage.error(errorMessage(error, '上传失败，请重试'))
  } finally {
    busy.value = null
  }
}

async function remove(kind: PromptFileKind): Promise<void> {
  if (!props.template) return
  const ok = await ElMessageBox.confirm(kind === 'excel' ? '删除后试发和样本试跑就没有数据可用，批量任务不受影响。' : '删除后模板不再提供这个码表，已发起的任务和线上版本不受影响。', '删除已上传的文件？', {
    type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
  }).then(() => true, () => false)
  if (!ok) return
  busy.value = kind
  try {
    emit('changed', await deletePromptFile(props.template.id, kind))
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败，请重试'))
  } finally {
    busy.value = null
  }
}

async function download(kind: PromptFileKind): Promise<void> {
  if (!props.template) return
  try {
    await downloadPromptFile(props.template.id, kind, fileName(kind))
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败，请重试'))
  }
}
</script>

<template>
  <div class="prompt-files">
    <div
      v-for="slot in slots"
      :key="slot.kind"
      class="prompt-files__row"
    >
      <span
        v-if="fileName(slot.kind) || slot.kind === 'excel' || !template"
        class="prompt-files__name"
        :class="{ 'is-empty': !fileName(slot.kind) }"
      >
        {{ fileName(slot.kind) || (template ? slot.empty : '保存模板后可上传') }}
        <template v-if="slot.kind === 'excel' && template?.excel_name">（{{ template.excel_rows }} 行数据）</template>
      </span>
      <input
        :ref="el => (pickers[slot.kind] = el as HTMLInputElement | null)"
        type="file"
        :accept="slot.accept"
        hidden
        @change="upload(slot.kind, $event)"
      >
      <el-button
        v-if="canEdit"
        link
        type="primary"
        :disabled="!template"
        :loading="busy === slot.kind"
        @click="pickers[slot.kind]?.click()"
      >
        {{ fileName(slot.kind) ? '重新上传' : slot.kind === 'code' ? '上传码表 .txt' : '上传' }}
      </el-button>
      <el-button
        v-if="slot.kind === 'excel' && canEdit && sampleTasks?.length"
        link
        type="primary"
        :disabled="!template"
        @click="sampling = true"
      >
        从数据库取
      </el-button>
      <el-button
        v-if="canExport && fileName(slot.kind)"
        link
        type="primary"
        @click="download(slot.kind)"
      >
        下载
      </el-button>
      <el-button
        v-if="canEdit && fileName(slot.kind)"
        link
        type="danger"
        :disabled="busy !== null"
        @click="remove(slot.kind)"
      >
        删除
      </el-button>
    </div>
    <SampleDialog
      v-if="template"
      v-model="sampling"
      :template="template"
      :tasks="sampleTasks ?? []"
      @done="item => emit('changed', item)"
    />
  </div>
</template>

<style scoped>
.prompt-files { display: grid; gap: 8px; }
/* 栏窄时按钮整组换到下一行，不撑出横向滚动条。 */
.prompt-files__row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 14px; min-height: 32px; }
.prompt-files__row .el-button { margin: 0; }
.prompt-files__name { flex: 1 1 120px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.prompt-files__name.is-empty { color: var(--zt-ink-500); }
</style>
