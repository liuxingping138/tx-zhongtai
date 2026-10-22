<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Setting } from '@element-plus/icons-vue'
import type { DataColumn } from './dataColumns'
import { restoreColumns } from './columnSelection'
const props = defineProps<{ columns: readonly DataColumn[]; defaults: string[]; legacyDefaults?: string[] }>()
const selected = defineModel<string[]>({ required: true })
const route = useRoute()
const auth = useAuthStore()
const storageSuffix = `${auth.user?.id || 'anonymous'}:${route.path}`
const storageKey = `zt:columns:v2:${storageSuffix}`
// 保存时页面上有哪些列，用来认出之后新加的列（见 restoreColumns）。
const knownKey = `zt:columns:known:${storageSuffix}`
const columnKeys = props.columns.map(col => col.prop)
const known = new Set(columnKeys)
function remember(value: string[]): void {
  localStorage.setItem(storageKey, JSON.stringify(value))
  localStorage.setItem(knownKey, JSON.stringify(columnKeys))
}
try {
  const current = localStorage.getItem(storageKey)
  const saved: unknown = JSON.parse(current || localStorage.getItem(`zt:columns:v1:${storageSuffix}`) || 'null')
  const restored = restoreColumns(saved, JSON.parse(localStorage.getItem(knownKey) || 'null'), columnKeys)
  const wasCompactDefault = !current && props.legacyDefaults && restored?.length === props.legacyDefaults.length && props.legacyDefaults.every(key => restored.includes(key))
  if (restored && !wasCompactDefault) selected.value = restored
  remember(selected.value)
} catch { /* Storage restrictions must not prevent using the table. */ }
watch(selected, value => {
  try { remember(value) } catch { /* In-memory selection still works. */ }
}, { deep: true })
const count = computed(() => selected.value.filter(key => known.has(key)).length)

</script>
<template>
  <el-popover
    trigger="click"
    role="dialog"
    aria-label="设置显示列"
    width="280"
    placement="bottom-end"
    :popper-options="{ modifiers: [{ name: 'preventOverflow', options: { altAxis: true, tether: false, padding: 12 } }] }"
  >
    <template #reference>
      <el-button
        :icon="Setting"
        :aria-label="`列设置，已显示 ${count} 列，共 ${columns.length} 列`"
        title="选择需要展示的字段，或显示全部列"
      >
        列设置 <span class="column-picker__count">{{ count }}/{{ columns.length }}</span>
      </el-button>
    </template>
    <div class="column-picker">
      <h2>设置显示列</h2><p>已显示 {{ count }} / {{ columns.length }} 列，至少保留一列。<br>设置会保存在当前浏览器。</p>
      <el-checkbox-group
        v-model="selected"
        :min="1"
        class="column-picker__list"
        aria-label="表格显示列"
      >
        <el-checkbox
          v-for="col in columns"
          :key="col.prop"
          :value="col.prop"
          :title="col.fullLabel || col.label"
        >
          {{ col.label }}
        </el-checkbox>
      </el-checkbox-group>
      <div class="column-picker__actions">
        <el-button
          text
          type="primary"
          @click="selected = columns.map(col => col.prop)"
        >
          显示全部列
        </el-button>
        <el-button
          text
          type="primary"
          @click="selected = [...props.defaults]"
        >
          恢复默认列
        </el-button>
      </div>
    </div>
  </el-popover>
</template>
<style scoped>
.column-picker__count { margin-left: 6px; font-size: 12px; font-variant-numeric: tabular-nums; }
.column-picker { display: flex; flex-direction: column; max-height: calc(100dvh - 48px); }
.column-picker__actions { display: flex; justify-content: space-between; border-top: 1px solid var(--zt-border); padding-top: 8px; }
.column-picker__actions :deep(.el-button + .el-button) { margin-left: 0; }
.column-picker h2 { margin: 0; font-size: 15px; color: var(--zt-ink-900); }
.column-picker p { font-size: 12px; color: var(--zt-ink-500); }
.column-picker__list { display: flex; flex-direction: column; min-height: 0; max-height: 320px; overflow: auto; margin-bottom: 12px; }
.column-picker__list :deep(.el-checkbox) { height: auto; min-height: 36px; margin-right: 0; }
.column-picker__list :deep(.el-checkbox__label) { white-space: normal; line-height: 1.5; }
</style>
