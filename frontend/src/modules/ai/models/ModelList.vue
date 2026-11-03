<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'

import { createModelConfig, listModelConfigs, updateModelConfig } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import AuditLogButton from '@/components/AuditLogButton.vue'
import BusinessTable from '@/components/BusinessTable.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import ListPage from '@/components/ListPage.vue'
import RecordEditorDrawer from '@/components/RecordEditorDrawer.vue'
import { useDetailColumns } from '@/composables/useDetailColumns'
import { useRecordEditor } from '@/composables/useRecordEditor'
import { useAuthStore } from '@/stores/auth'
import {
  CREATE_DEFAULTS,
  EDIT_GROUPS,
  EDITOR_GROUPS,
  SUMMARY_KEYS,
  TABLE_COLUMNS,
  toBody,
  toRow,
  type ModelRow,
} from './fields'

const RESOURCE = 'ai.models'
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))
const items = ref<ModelRow[]>([])
const loading = ref(false)
const loadError = ref('')
const { columns, defaults, selected } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)

async function load() {
  loading.value = true
  try {
    items.value = (await listModelConfigs()).map(toRow)
    loadError.value = ''
  } catch (error) {
    loadError.value = errorMessage(error, '加载模型配置失败')
  } finally {
    loading.value = false
  }
}

const editor = useRecordEditor<ModelRow>({
  noun: '模型',
  groups: EDITOR_GROUPS,
  defaults: CREATE_DEFAULTS,
  create: form => createModelConfig(toBody(form)),
  update: (row, form) => updateModelConfig(row.id, { ...toBody(form), id: row.id, version: row.version }),
  refresh: load,
})
const groups = computed(() => (editor.editing.value ? EDIT_GROUPS : EDITOR_GROUPS))

onMounted(() => { void load() })
</script>

<template>
  <div>
    <ListPage
      title="模型配置"
      hint="提示词模板和批量任务可选的模型与单价。保存后立即生效，已在跑的批量任务仍按开跑时的配置。"
      :total="items.length"
      :page="1"
      :page-size="items.length || 20"
      hide-pager
      :loading="loading"
      :error="loadError"
      @retry="load"
    >
      <template #actions>
        <el-button
          v-if="canWrite"
          type="primary"
          :icon="Plus"
          @click="editor.openCreate"
        >
          新增
        </el-button>
        <AuditLogButton :module="RESOURCE" />
      </template>
      <template #tools>
        <ColumnPicker
          v-model="selected"
          :columns="columns"
          :defaults="defaults"
        />
      </template>
      <BusinessTable
        :items="items"
        :columns="columns"
        :groups="EDITOR_GROUPS"
        :selected="selected"
        :summary-keys="SUMMARY_KEYS"
        title-key="name"
        detail-title="模型详情"
        :can-write="canWrite"
        :loading="loading"
        :filtered="false"
        @edit="editor.openEdit"
      />
    </ListPage>
    <RecordEditorDrawer
      :editor="editor"
      :groups="groups"
    />
  </div>
</template>
