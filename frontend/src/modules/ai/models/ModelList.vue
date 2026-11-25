<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

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
  checkModelForm,
  CREATE_DEFAULTS,
  DEFAULT_SELECTED_COLUMNS,
  EDIT_GROUPS,
  EDITOR_GROUPS,
  formatMillionSummary,
  priceCellTitle,
  SUMMARY_KEYS,
  TABLE_COLUMNS,
  toBody,
  TOKEN_PRICE_KEYS,
  toRow,
  withLivePriceHints,
  type ModelRow,
} from './fields'

const RESOURCE = 'ai.models'
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))
const items = ref<ModelRow[]>([])
const loading = ref(false)
const loadError = ref('')
const { columns, defaults: allColumns } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)
const defaults = DEFAULT_SELECTED_COLUMNS
const selected = ref([...DEFAULT_SELECTED_COLUMNS])

try {
  const migratedKey = `zt:models:cols-init:${auth.user?.id || 'anonymous'}`
  if (!localStorage.getItem(migratedKey)) {
    localStorage.removeItem(`zt:columns:v2:${auth.user?.id || 'anonymous'}:/ai/models`)
    localStorage.setItem(migratedKey, '1')
  }
} catch { /* Storage unavailable */ }

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
  check: checkModelForm,
  create: form => createModelConfig(toBody(form)),
  update: (row, form) => updateModelConfig(row.id, { ...toBody(form), id: row.id, version: row.version }),
  refresh: load,
})
const groups = computed(() => withLivePriceHints(editor.editing.value ? EDIT_GROUPS : EDITOR_GROUPS, editor.form))

// 列表上直接启停，和用户管理同一种开关：先确认，成功后提示并刷新。
const toggling = ref('')
async function toggle(row: ModelRow) {
  if (toggling.value) return
  const enable = row.enabled !== '启用'
  const verb = enable ? '启用' : '停用'
  const ok = await ElMessageBox.confirm(
    enable
      ? `启用后「${row.name}」会出现在模板和批量任务的模型下拉里。`
      : `停用后「${row.name}」不再出现在模型下拉里，已排队、运行中的任务照常跑完。`,
    `${verb}这个模型？`,
    { confirmButtonText: verb, cancelButtonText: '取消', type: 'warning' },
  ).then(() => true, () => false)
  if (!ok) return
  toggling.value = row.id
  try {
    // 其余字段按原样提交，只改启停：和编辑抽屉保存走同一个接口、同一个版本号
    const form = Object.fromEntries(Object.entries(row).map(([key, value]) => [key, String(value ?? '')]))
    await updateModelConfig(row.id, { ...toBody(form), enabled: enable, id: row.id, version: row.version })
    ElMessage.success(`已${verb}`)
  } catch (error) {
    ElMessage.error(errorMessage(error, `${verb}失败，请刷新后重试`))
  } finally {
    toggling.value = ''
    await load()
  }
}

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
          :legacy-defaults="allColumns"
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
      >
        <template #cell-enabled="{ row }">
          <span class="status-line">
            <el-switch
              v-if="canWrite"
              :model-value="row.enabled === '启用'"
              :loading="toggling === row.id"
              :disabled="!!toggling && toggling !== row.id"
              :aria-label="`${row.name} 启用`"
              @change="toggle(row)"
            />
            <el-tag
              v-else
              :type="row.enabled === '启用' ? 'success' : 'warning'"
              size="small"
            >
              {{ row.enabled }}
            </el-tag>
            <span
              v-if="canWrite"
              class="status-text"
            >{{ row.enabled }}</span>
          </span>
        </template>

        <template
          v-for="priceKey in TOKEN_PRICE_KEYS"
          :key="priceKey"
          #[`cell-${priceKey}`]="{ row }"
        >
          <span
            v-if="row[priceKey]"
            class="price-num"
            :title="priceCellTitle(row[priceKey])"
          >{{ row[priceKey] }}</span>
          <span
            v-else
            class="price-empty"
          >—</span>
        </template>

        <template #detail-extra="{ row }">
          <p
            v-if="formatMillionSummary(row)"
            class="detail-million-note"
          >
            {{ formatMillionSummary(row) }}
          </p>
        </template>
      </BusinessTable>
    </ListPage>
    <RecordEditorDrawer
      :editor="editor"
      :groups="groups"
    />
  </div>
</template>

<style scoped>
.status-line { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.status-text { color: var(--zt-ink-500); font-size: 12px; }
.price-num { font-variant-numeric: tabular-nums; color: var(--zt-ink-900); }
.price-empty { color: var(--zt-ink-400); }
.detail-million-note {
  margin: 14px 0 0;
  padding: 10px 14px;
  border: 1px solid var(--zt-divider);
  border-radius: 8px;
  background: var(--zt-surface-subtle);
  color: var(--zt-ink-500);
  font-size: 12.5px;
  line-height: 1.6;
  font-variant-numeric: tabular-nums;
}
</style>
