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
const columnKeys = computed(() => props.columns.map(col => col.prop))
const known = computed(() => new Set(columnKeys.value))

function readStoredList(key: string): string[] | null {
  const raw: unknown = JSON.parse(localStorage.getItem(key) || 'null')
  return Array.isArray(raw) ? raw.filter((item): item is string => typeof item === 'string') : null
}

function isLegacyCompact(current: string | null, restored: string[] | null): boolean {
  if (current || !props.legacyDefaults || !restored) return false
  return restored.length === props.legacyDefaults.length && props.legacyDefaults.every(key => restored.includes(key))
}

function collectPending(saved: unknown, keys: readonly string[]): Set<string> {
  if (!Array.isArray(saved)) return new Set()
  const present = new Set(keys)
  return new Set(saved.filter((key): key is string => typeof key === 'string' && !present.has(key)))
}

// 记住首次加载时本地保存的已知列与选中列，防止异步追加 AI 列到达前被首屏静态列覆盖。
let knownHistory = new Set<string>(columnKeys.value)
let pendingSaved = new Set<string>()

function remember(value: string[]): void {
  const savedKeys = [...new Set([...value, ...pendingSaved])]
  const knownKeys = [...new Set([...knownHistory, ...columnKeys.value])]
  localStorage.setItem(storageKey, JSON.stringify(savedKeys))
  localStorage.setItem(knownKey, JSON.stringify(knownKeys))
}

function initSelection(): void {
  const current = localStorage.getItem(storageKey)
  const saved: unknown = JSON.parse(current || localStorage.getItem(`zt:columns:v1:${storageSuffix}`) || 'null')
  const storedKnown = readStoredList(knownKey)
  const keys = columnKeys.value
  const restored = restoreColumns(saved, storedKnown, keys)
  const wasCompactDefault = isLegacyCompact(current, restored)
  knownHistory = new Set([...(storedKnown ?? []), ...keys])
  if (!wasCompactDefault) pendingSaved = collectPending(saved, keys)
  if (restored && !wasCompactDefault) selected.value = restored
  remember(selected.value)
}

try {
  initSelection()
} catch { /* Storage restrictions must not prevent using the table. */ }

watch(columnKeys, keys => {
  const toShow = keys.filter(key => pendingSaved.delete(key) || !knownHistory.has(key))
  const hasNewKnown = keys.some(key => !knownHistory.has(key))
  keys.forEach(key => knownHistory.add(key))
  if (toShow.length) {
    const next = new Set([...selected.value, ...toShow])
    selected.value = keys.filter(key => next.has(key))
  }
  if (toShow.length || hasNewKnown) {
    try { remember(selected.value) } catch { /* In-memory selection still works. */ }
  }
})

watch(selected, value => {
  try { remember(value) } catch { /* In-memory selection still works. */ }
}, { deep: true })
const count = computed(() => selected.value.filter(key => known.value.has(key)).length)

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
