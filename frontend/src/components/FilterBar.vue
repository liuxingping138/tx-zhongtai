<script setup lang="ts">
import { Comment, Fragment, Text, computed, ref, useSlots, type Slot, type VNode } from 'vue'
import { ArrowUp, Filter } from '@element-plus/icons-vue'

const props = defineProps<{ query: Record<string, unknown>; applied?: Record<string, unknown> }>()
const emit = defineEmits<{ search: []; reset: [] }>()
const slots = useSlots()
const composing = ref(false)

function filledEntries(source: Record<string, unknown> = {}) {
  return Object.entries(source).filter(([key, value]) =>
    !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : value !== '' && value !== null && value !== undefined))
}

function filledSignature(source: Record<string, unknown> = {}) {
  const next = Object.fromEntries(filledEntries(source).sort(([left], [right]) => left.localeCompare(right)))
  return JSON.stringify(next)
}

function countSlotFields(slot?: Slot) {
  const walk = (nodes: VNode[] = []): number => nodes.reduce((sum, node) => {
    if (node.type === Comment || node.type === Text) return sum
    if (node.type === Fragment) return sum + walk((node.children as VNode[]) ?? [])
    return sum + 1
  }, 0)
  return walk(slot?.() ?? [])
}

const count = computed(() => filledEntries(props.applied ?? {}).length)
const dirty = computed(() => filledSignature(props.query) !== filledSignature(props.applied ?? {}))
const canReset = computed(() => count.value > 0 || dirty.value)
const hasExtraFields = computed(() => countSlotFields(slots.default) + countSlotFields(slots.advanced) > 1)
const expanded = ref(count.value > 0)
const hint = computed(() => {
  if (dirty.value) return '条件已改，点击查询后生效'
  if (count.value) return `已筛选 ${count.value} 项`
  return ''
})

function submit() {
  if (!composing.value) emit('search')
}
</script>
<template>
  <el-form
    class="filter-bar"
    :class="{ 'is-expanded': expanded, 'is-pending': dirty }"
    label-position="top"
    novalidate
    @compositionstart="composing = true"
    @compositionend="composing = false"
    @submit.prevent="submit"
  >
    <div class="filter-bar__fields">
      <slot />
      <slot name="advanced" />
    </div>
    <div class="filter-bar__actions">
      <p
        v-if="hint"
        class="filter-bar__hint"
        :class="{ 'is-pending': dirty }"
        role="status"
        aria-live="polite"
      >
        {{ hint }}
      </p>
      <div class="filter-bar__buttons">
        <el-button
          v-if="hasExtraFields"
          class="filter-bar__toggle"
          :icon="expanded ? ArrowUp : Filter"
          :aria-expanded="expanded"
          @click="expanded = !expanded"
        >
          {{ expanded ? '收起筛选' : '更多筛选' }}
        </el-button>
        <el-button
          type="primary"
          native-type="submit"
        >
          查询
        </el-button>
        <el-button
          :disabled="!canReset"
          @click="emit('reset')"
        >
          重置
        </el-button>
      </div>
    </div>
  </el-form>
</template>
<style scoped>
.filter-bar { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px 16px; }
.filter-bar__fields { display: flex; flex-wrap: wrap; flex: 1 1 640px; align-items: flex-end; gap: 12px; min-width: 0; }
.filter-bar__fields :deep(> .el-form-item) { flex: 1 1 160px; max-width: 240px; margin: 0; min-width: 0; }
.filter-bar__fields :deep(> .el-form-item:first-child) { flex: 1.5 1 220px; max-width: 360px; }
.filter-bar__fields :deep(> .el-form-item:only-child) { flex: 0 1 360px; max-width: 360px; }
.filter-bar__fields :deep(> .filter-form__item--wide) { flex: 2 1 360px; max-width: 560px; }
.filter-bar__actions { display: flex; flex-direction: column; align-items: flex-end; justify-content: flex-end; gap: 6px; margin-left: auto; }
.filter-bar__hint { margin: 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.4; white-space: nowrap; }
.filter-bar__hint.is-pending { color: var(--zt-blue-600); }
.filter-bar__buttons { display: flex; align-items: center; gap: 8px; }
.filter-bar__buttons :deep(.el-button + .el-button) { margin-left: 0; }
.filter-bar__toggle { display: none; }
.filter-bar :deep(.el-form-item__label) { color: var(--zt-ink-700); margin: 0 0 6px; padding: 0; line-height: 20px; font-size: 13px; }
.filter-bar :deep(.el-input), .filter-bar :deep(.el-select), .filter-bar :deep(.el-date-editor) { width: 100%; }
.filter-bar :deep(.el-date-editor.el-date-editor--datetimerange) { min-width: 280px; }
.filter-bar :deep(.el-input__wrapper), .filter-bar :deep(.el-select__wrapper), .filter-bar :deep(.el-date-editor) {
  min-height: 36px;
  background: #fff;
  box-shadow: 0 0 0 1px #d7dfeb inset;
}
.filter-bar :deep(.el-input__wrapper.is-focus), .filter-bar :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px var(--zt-blue-600) inset, 0 0 0 3px rgba(44, 104, 187, 0.12);
}
@media (max-width: 900px) {
  .filter-bar__fields { flex-basis: 100%; }
  .filter-bar__actions { width: 100%; align-items: stretch; margin-left: 0; }
  .filter-bar__hint { white-space: normal; }
  .filter-bar__buttons { width: 100%; }
  .filter-bar__toggle { margin-right: auto; }
}
@media (max-width: 767px) {
  .filter-bar { gap: 10px; }
  .filter-bar__fields, .filter-bar__fields :deep(> .el-form-item), .filter-bar__fields :deep(> .el-form-item:first-child), .filter-bar__fields :deep(> .el-form-item:only-child), .filter-bar__fields :deep(> .filter-form__item--wide) { flex: 1 1 100%; max-width: none; }
  .filter-bar:not(.is-expanded) .filter-bar__fields :deep(> .el-form-item:nth-child(n+2)) { display: none; }
  .filter-bar__toggle { display: inline-flex; }
  .filter-bar :deep(.el-input__wrapper), .filter-bar :deep(.el-select__wrapper), .filter-bar :deep(.el-date-editor) { min-height: 44px; }
}
</style>
