<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { deletePromptFile, uploadPromptFile, type PromptFileKind, type PromptTemplate } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { downloadPromptFile } from '../shared/downloads'

/** systemCode：模板选了系统码表，上传的码表文件不生效，只留 Excel 一行 */
const props = defineProps<{ template: PromptTemplate | null; canEdit: boolean; canExport: boolean; systemCode: boolean }>()
const emit = defineEmits<{ changed: [template: PromptTemplate] }>()
const busy = ref<PromptFileKind | null>(null)
const pickers = ref<Record<PromptFileKind, HTMLInputElement | null>>({ excel: null, code: null })

const SLOTS: { kind: PromptFileKind; label: string; accept: string; empty: string }[] = [
  { kind: 'excel', label: 'Excel', accept: '.xlsx', empty: '未上传（.xlsx，第一行为表头）' },
  { kind: 'code', label: '码表', accept: '.txt', empty: '未上传（.txt，用 @【上传码表】引用）' },
]

const slots = computed(() => (props.systemCode ? SLOTS.filter(slot => slot.kind === 'excel') : SLOTS))

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
    ElMessage.success(kind === 'excel' ? 'Excel 已上传' : '码表已上传')
  } catch (error) {
    ElMessage.error(errorMessage(error, '上传失败，请重试'))
  } finally {
    busy.value = null
  }
}

async function remove(kind: PromptFileKind): Promise<void> {
  if (!props.template) return
  const ok = await ElMessageBox.confirm(`删除后批量提问将无法使用这份${kind === 'excel' ? ' Excel' : '码表'}，已发起的任务不受影响。`, '删除已上传的文件？', {
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
      <span class="prompt-files__label">{{ slot.label }}</span>
      <span
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
        size="small"
        :disabled="!template"
        :loading="busy === slot.kind"
        @click="pickers[slot.kind]?.click()"
      >
        {{ fileName(slot.kind) ? '重新上传' : '上传' }}
      </el-button>
      <el-button
        v-if="canExport && fileName(slot.kind)"
        size="small"
        @click="download(slot.kind)"
      >
        下载
      </el-button>
      <el-button
        v-if="canEdit && fileName(slot.kind)"
        size="small"
        type="danger"
        plain
        :disabled="busy !== null"
        @click="remove(slot.kind)"
      >
        删除
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.prompt-files { display: grid; gap: 8px; }
.prompt-files__row { display: flex; align-items: center; gap: 8px; min-height: 32px; }
.prompt-files__row .el-button { margin: 0; }
.prompt-files__label { flex: 0 0 64px; color: var(--zt-ink-700); font-size: 13px; }
.prompt-files__name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.prompt-files__name.is-empty { color: var(--zt-ink-500); }
</style>
