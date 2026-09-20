<script setup lang="ts">
import { computed, ref, useSlots } from 'vue'
import { Filter, ArrowUp } from '@element-plus/icons-vue'
const props = defineProps<{ query: Record<string, unknown> }>()
const emit = defineEmits<{ search: []; reset: [] }>()
const slots = useSlots()
const expanded = ref(false)
const composing = ref(false)
const count = computed(() => Object.entries(props.query).filter(([key, value]) =>
  !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length : Boolean(value))).length)
function submit() { if (!composing.value) emit('search') }
</script>
<template>
  <el-form
    class="filter-bar"
    :class="{ 'is-expanded': expanded }"
    label-position="top"
    novalidate
    @compositionstart="composing = true"
    @compositionend="composing = false"
    @submit.prevent="submit"
  >
    <div class="filter-bar__fields">
      <slot />
    </div>
    <div class="filter-bar__buttons">
      <el-button
        class="filter-bar__toggle"
        :class="{ 'has-advanced': slots.advanced }"
        :icon="expanded ? ArrowUp : Filter"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? '收起筛选' : '更多筛选' }}<span
          v-if="count"
          class="filter-count"
        >{{ count }}</span>
      </el-button>
      <el-button
        type="primary"
        native-type="submit"
      >
        查询
      </el-button>
      <el-button
        text
        @click="emit('reset')"
      >
        重置
      </el-button>
    </div>
    <div
      v-if="slots.advanced"
      v-show="expanded"
      class="filter-bar__advanced"
    >
      <slot name="advanced" />
    </div>
  </el-form>
</template>
<style scoped>
.filter-bar { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px; }
.filter-bar__fields { flex: 0 1 900px; display: grid; grid-template-columns: minmax(210px, 1.6fr) repeat(2, minmax(140px, 1fr)); gap: 12px; min-width: 0; }
.filter-bar__fields:has(> :only-child) { grid-template-columns: minmax(200px, 360px); }
.filter-bar__fields:has(> :nth-child(2):last-child) { grid-template-columns: minmax(200px, 320px) minmax(140px, 220px); }
.filter-bar__buttons { display: flex; align-items: center; gap: 8px; }
.filter-bar__buttons :deep(.el-button + .el-button) { margin-left: 0; }
.filter-bar__toggle { display: none; }
.filter-bar__toggle.has-advanced { display: inline-flex; }
.filter-bar__advanced { flex-basis: 100%; display: grid; grid-template-columns: repeat(3, minmax(140px, 1fr)); gap: 12px; padding-top: 4px; }
.filter-bar :deep(.el-form-item) { margin: 0; min-width: 0; }
.filter-bar :deep(.el-form-item__label) { color: var(--zt-ink-700); margin: 0 0 6px; padding: 0; line-height: 20px; font-size: 13px; }
.filter-bar :deep(.el-input), .filter-bar :deep(.el-select), .filter-bar :deep(.el-date-editor) { width: 100%; }
.filter-bar :deep(.el-input__wrapper), .filter-bar :deep(.el-select__wrapper) { min-height: 36px; background: var(--zt-panel); }
.filter-count { margin-left: 6px; font-variant-numeric: tabular-nums; color: var(--zt-blue-600); }
@media (max-width: 1200px) { .filter-bar__fields { grid-template-columns: minmax(170px, 1.4fr) repeat(2, minmax(110px, 1fr)); } .filter-bar__buttons { margin-left: auto; } }
@media (min-width: 901px) {
 .filter-bar__fields { flex-basis: min(900px, calc(100% - 270px)); }
 .filter-bar__fields:has(> :only-child) { flex-basis: 360px; }
 .filter-bar__fields:has(> :nth-child(2):last-child) { flex-basis: 552px; }
}
@media (max-width: 900px) { .filter-bar__fields { flex-basis: 100%; } }
@media (max-width: 767px) {
 .filter-bar { gap: 10px; }
 .filter-bar :deep(.el-input__wrapper), .filter-bar :deep(.el-select__wrapper) { min-height: 44px; }
 .filter-bar__fields, .filter-bar__fields:has(> :nth-child(2):last-child), .filter-bar__fields:has(> :only-child), .filter-bar__advanced { grid-template-columns: minmax(0, 1fr); }
 .filter-bar:not(.is-expanded) .filter-bar__fields :deep(> .el-form-item:nth-child(n+2)) { display: none; }
 .filter-bar__toggle { display: inline-flex; }
 .filter-bar__buttons { margin: 0; width: 100%; }
 .filter-bar__buttons .el-button:first-child { margin-right: auto; }
}
</style>
