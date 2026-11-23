<script setup lang="ts">
import { ArrowDown, ArrowUp, Close } from '@element-plus/icons-vue'
import { onMounted, ref } from 'vue'

// 文档内查找条：Enter 下一处、Shift+Enter 上一处、Esc 关掉（先于退出全屏）。
const props = defineProps<{
  query: string
  label: string
  total: number
}>()

const emit = defineEmits<{
  'update:query': [value: string]
  submit: [backward: boolean]
  step: [direction: 1 | -1]
  close: []
}>()

const input = ref<HTMLInputElement>()

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    event.preventDefault()
    emit('submit', event.shiftKey)
  } else if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    emit('close')
  }
}

function focus() {
  input.value?.focus()
  input.value?.select()
}

defineExpose({ focus })
onMounted(focus)
</script>

<template>
  <div
    class="pdf-search"
    role="search"
  >
    <input
      ref="input"
      class="pdf-search__input"
      type="search"
      placeholder="在文档中查找"
      aria-label="在文档中查找"
      :value="props.query"
      @input="emit('update:query', ($event.target as HTMLInputElement).value)"
      @keydown="onKeydown"
    >
    <span
      class="pdf-search__count"
      role="status"
    >{{ props.query.trim() ? props.label : '' }}</span>
    <button
      type="button"
      class="pdf-search__btn"
      title="上一处（Shift+Enter）"
      :disabled="props.total === 0"
      @click="emit('step', -1)"
    >
      <el-icon><ArrowUp /></el-icon>
    </button>
    <button
      type="button"
      class="pdf-search__btn"
      title="下一处（Enter）"
      :disabled="props.total === 0"
      @click="emit('step', 1)"
    >
      <el-icon><ArrowDown /></el-icon>
    </button>
    <button
      type="button"
      class="pdf-search__btn"
      title="关闭查找（Esc）"
      @click="emit('close')"
    >
      <el-icon><Close /></el-icon>
    </button>
  </div>
</template>

<style scoped>
.pdf-search { display: flex; align-items: center; gap: 4px; padding: 6px 12px; border-bottom: 1px solid var(--zt-border); background: var(--zt-panel); }
.pdf-search__input { flex: 1; min-width: 120px; max-width: 320px; height: 26px; padding: 0 8px; border: 1px solid var(--zt-border); border-radius: 4px; background: var(--zt-panel); color: var(--zt-ink-900); font-size: 12px; }
.pdf-search__input:focus { outline: none; border-color: var(--zt-blue-600); box-shadow: var(--zt-focus-ring); }
.pdf-search__count { min-width: 84px; color: var(--zt-ink-500); font-size: 12px; white-space: nowrap; }
.pdf-search__btn { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border: none; border-radius: 6px; background: transparent; color: var(--zt-ink-700); cursor: pointer; }
.pdf-search__btn:hover:not(:disabled) { background: var(--zt-row-hover); color: var(--zt-blue-600); }
.pdf-search__btn:disabled { color: var(--zt-ink-400); cursor: not-allowed; }
</style>
