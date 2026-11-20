<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowDown, ArrowUp, RefreshRight, Search } from '@element-plus/icons-vue'
import { foldFilterFields } from './filterFold'

const props = withDefaults(
  defineProps<{
    query: Record<string, unknown>
    applied?: Record<string, unknown>
    collapsible?: boolean
    labelPosition?: 'top' | 'left'
  }>(),
  { applied: undefined, collapsible: true, labelPosition: 'left' },
)
const emit = defineEmits<{ search: []; reset: [] }>()
const composing = ref(false)

function filledEntries(source: Record<string, unknown> = {}) {
  return Object.entries(source).filter(([key, value]) =>
    !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : value !== '' && value !== null && value !== undefined))
}

function filledSignature(source: Record<string, unknown> = {}) {
  const next = Object.fromEntries(filledEntries(source).sort(([left], [right]) => left.localeCompare(right)))
  return JSON.stringify(next)
}

const count = computed(() => filledEntries(props.applied ?? {}).length)
const dirty = computed(() => filledSignature(props.query) !== filledSignature(props.applied ?? {}))
const canReset = computed(() => count.value > 0 || dirty.value)
const hint = computed(() => {
  if (dirty.value) return '条件已改，点击查询后生效'
  if (count.value) return `已筛选 ${count.value} 项`
  return ''
})

// 默认只露第一行，一行放几个由屏幕宽度决定；第一行之后的框收起，点「展开」再看。
// 收起的框用 visibility 藏，仍占位置才量得出它在第几行，也不会被 Tab 选中。
// 筛选区四周留 4px，第一行输入框的聚焦外圈不被截掉。
const FOCUS_ROOM = 4
const fields = ref<HTMLElement>()
const expanded = ref(false)
const foldedCount = ref(0)
const foldedFilled = ref(0)
const firstRowBottom = ref(0)
const folded = computed(() => !expanded.value && foldedCount.value > 0)
const toggleLabel = computed(() => {
  if (expanded.value) return '收起筛选条件'
  return foldedFilled.value ? `展开筛选条件，收起的条件里已填 ${foldedFilled.value} 项` : '展开筛选条件'
})

/** 框里有没有值：多选看已选标签，单选看占位文字是否换成了选中项，输入框和日期看文字。 */
function hasValue(item: HTMLElement) {
  if (item.querySelector('.el-tag, .el-select__placeholder:not(.is-transparent)')) return true
  return [...item.querySelectorAll('input')].some(input => input.value.trim() !== '')
}

function measure() {
  const box = fields.value
  if (!box) return
  const items = [...box.children].filter((node): node is HTMLElement => node instanceof HTMLElement)
  if (!props.collapsible) {
    items.forEach(item => item.removeAttribute('data-folded'))
    foldedCount.value = 0
    foldedFilled.value = 0
    return
  }
  const fold = foldFilterFields(items.map(item => ({ top: item.offsetTop, height: item.offsetHeight, filled: hasValue(item) })))
  const hidden = new Set(fold.folded)
  items.forEach((item, index) => item.toggleAttribute('data-folded', !expanded.value && hidden.has(index)))
  foldedCount.value = fold.folded.length
  foldedFilled.value = fold.foldedFilled
  firstRowBottom.value = fold.firstRowBottom
}

let resizeObserver: ResizeObserver | undefined
let mutationObserver: MutationObserver | undefined
onMounted(() => {
  measure()
  if (!fields.value) return
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => measure())
    resizeObserver.observe(fields.value)
  }
  // 有的页面按权限或类型增减筛选框，框的个数变了要重新量。
  mutationObserver = new MutationObserver(() => measure())
  mutationObserver.observe(fields.value, { childList: true })
})
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  mutationObserver?.disconnect()
})
watch([() => JSON.stringify(props.query), expanded], measure, { flush: 'post' })

function submit() {
  if (!composing.value) emit('search')
}
</script>
<template>
  <el-form
    class="filter-bar"
    :class="{ 'is-pending': dirty, 'filter-bar--left': labelPosition === 'left' }"
    :label-position="labelPosition"
    novalidate
    @compositionstart="composing = true"
    @compositionend="composing = false"
    @submit.prevent="submit"
  >
    <div
      ref="fields"
      class="filter-bar__fields"
      :class="{ 'is-folded': folded }"
      :style="folded ? { maxHeight: `${firstRowBottom + FOCUS_ROOM}px` } : undefined"
    >
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
          type="primary"
          native-type="submit"
          :icon="Search"
        >
          查询
        </el-button>
        <el-button
          :disabled="!canReset"
          :icon="RefreshRight"
          @click="emit('reset')"
        >
          重置
        </el-button>
        <el-button
          v-if="foldedCount > 0"
          class="filter-bar__toggle"
          link
          type="primary"
          :aria-expanded="expanded"
          :aria-label="toggleLabel"
          @click="expanded = !expanded"
        >
          {{ expanded ? '收起' : '展开' }}
          <span
            v-if="!expanded && foldedFilled"
            class="filter-bar__badge"
            aria-hidden="true"
          >{{ foldedFilled }}</span>
          <el-icon class="el-icon--right">
            <ArrowUp v-if="expanded" />
            <ArrowDown v-else />
          </el-icon>
        </el-button>
      </div>
    </div>
  </el-form>
</template>
<style scoped>
.filter-bar { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px 16px; }
.filter-bar__fields { position: relative; display: flex; flex-wrap: wrap; flex: 1 1 640px; align-items: flex-end; gap: 12px; min-width: 0; }
.filter-bar__fields.is-folded { overflow: hidden; padding: 0 4px 4px; margin: 0 -4px -4px; }
.filter-bar__fields :deep(> [data-folded]) { visibility: hidden; }
.filter-bar__fields :deep(> .el-form-item) { flex: 1 1 160px; max-width: 240px; margin: 0; min-width: 0; }
.filter-bar__fields :deep(> .el-form-item:first-child) { flex: 1.5 1 220px; max-width: 360px; }
.filter-bar__fields :deep(> .el-form-item:only-child) { flex: 0 1 360px; max-width: 360px; }
.filter-bar__fields :deep(> .filter-form__item--wide) { flex: 2 1 360px; max-width: 560px; }
.filter-bar__actions { display: flex; flex-direction: column; align-items: flex-end; justify-content: flex-end; gap: 6px; margin-left: auto; }
.filter-bar__hint { margin: 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.4; white-space: nowrap; }
.filter-bar__hint.is-pending { color: var(--zt-blue-600); }
.filter-bar__buttons { display: flex; align-items: center; gap: 8px; }
.filter-bar__buttons :deep(.el-button + .el-button) { margin-left: 0; }
.filter-bar__toggle { padding: 0 2px; }
.filter-bar__badge { min-width: 18px; margin-left: 4px; padding: 0 5px; border-radius: 9px; background: var(--zt-blue-600); color: var(--el-color-white); font-size: 12px; line-height: 18px; text-align: center; }
.filter-bar :deep(.el-form-item__label) { color: var(--zt-ink-700); margin: 0 0 6px; padding: 0; line-height: 20px; font-size: 13px; }
.filter-bar--left { align-items: center; }
.filter-bar--left .filter-bar__fields { align-items: center; gap: 12px 16px; }
.filter-bar--left .filter-bar__fields :deep(> .el-form-item) { display: flex; align-items: center; flex: 1 1 200px; max-width: 270px; }
.filter-bar--left .filter-bar__fields :deep(> .el-form-item:first-child) { flex: 1.4 1 240px; max-width: 340px; }
.filter-bar--left .filter-bar__fields :deep(> .el-form-item:only-child) { flex: 0 1 380px; max-width: 380px; }
.filter-bar--left .filter-bar__fields :deep(> .filter-form__item--wide) { flex: 2 1 360px; max-width: 560px; }
.filter-bar--left :deep(.el-form-item__label) { margin: 0 8px 0 0; line-height: 36px; white-space: nowrap; flex-shrink: 0; }
.filter-bar--left :deep(.el-form-item__content) { flex: 1; min-width: 0; }
.filter-bar :deep(.el-input), .filter-bar :deep(.el-select), .filter-bar :deep(.el-date-editor) { width: 100%; }
.filter-bar :deep(.el-date-editor.el-date-editor--datetimerange) { min-width: 280px; }
.filter-bar :deep(.el-input__wrapper), .filter-bar :deep(.el-select__wrapper), .filter-bar :deep(.el-date-editor) {
  min-height: 36px;
  background: var(--zt-panel);
  box-shadow: 0 0 0 1px var(--zt-border-strong) inset;
}
.filter-bar :deep(.el-input__wrapper.is-focus), .filter-bar :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px var(--zt-blue-600) inset, 0 0 0 3px var(--zt-focus-ring);
}
@media (max-width: 900px) {
  .filter-bar__fields { flex-basis: 100%; }
  .filter-bar__actions { width: 100%; align-items: stretch; margin-left: 0; }
  .filter-bar__hint { white-space: normal; }
  .filter-bar__buttons { width: 100%; }
}
@media (max-width: 767px) {
  .filter-bar { gap: 10px; }
  .filter-bar__fields, .filter-bar__fields :deep(> .el-form-item), .filter-bar__fields :deep(> .el-form-item:first-child), .filter-bar__fields :deep(> .el-form-item:only-child), .filter-bar__fields :deep(> .filter-form__item--wide) { flex: 1 1 100%; max-width: none; }
  .filter-bar :deep(.el-input__wrapper), .filter-bar :deep(.el-select__wrapper), .filter-bar :deep(.el-date-editor) { min-height: 44px; }
}
</style>
