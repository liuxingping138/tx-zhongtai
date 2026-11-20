<script setup lang="ts">
import { ArrowDown, Check, Close, Search } from '@element-plus/icons-vue'
import { computed, onScopeDispose, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string[]
    label: string
    options: string[]
    labels?: Record<string, string>
    remoteSearch?: (keyword: string) => Promise<string[]>
  }>(),
  { labels: undefined, remoteSearch: undefined },
)

const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const MAX_SHOWN = 80
const SEARCH_DEBOUNCE_MS = 250

const open = ref(false)
const keyword = ref('')
const remoteItems = ref<string[]>([])
const searching = ref(false)
const remoteFailed = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null
let sequence = 0

onScopeDispose(() => {
  if (timer) clearTimeout(timer)
})

const optionLabel = (value: string) => props.labels?.[value] || value
const isRemote = computed(() => typeof props.remoteSearch === 'function')
const selectedCount = computed(() => props.modelValue.length)
const firstLabel = computed(() => (selectedCount.value > 0 ? optionLabel(props.modelValue[0] ?? '') : ''))
const summaryText = computed(() => (selectedCount.value > 1 ? `${firstLabel.value} +${selectedCount.value - 1}` : firstLabel.value))
const fullTooltip = computed(() => props.modelValue.map(optionLabel).join('、'))

const matchedOptions = computed(() => {
  const query = keyword.value.trim()
  const source = isRemote.value && query ? remoteItems.value : props.options
  if (isRemote.value && query) return source.slice(0, MAX_SHOWN)
  const needle = query.toLowerCase()
  const matched = needle
    ? source.filter(item => item.toLowerCase().includes(needle) || optionLabel(item).toLowerCase().includes(needle))
    : source
  return matched.slice(0, MAX_SHOWN)
})

const displayOptions = computed(() => {
  const list = matchedOptions.value
  const missing = props.modelValue.filter(val => !list.includes(val))
  return missing.length ? [...missing, ...list] : list
})

const emptyText = computed(() => {
  if (searching.value) return '搜索中…'
  if (remoteFailed.value) return '搜索失败，请稍后重试'
  if (isRemote.value && !keyword.value.trim()) return '候选较多，输入关键词搜索'
  return '无匹配项'
})

function runRemote(query: string) {
  const search = props.remoteSearch
  if (!search) return
  const current = ++sequence
  searching.value = true
  remoteFailed.value = false
  void search(query)
    .then((items) => { if (current === sequence) remoteItems.value = items })
    .catch(() => { if (current === sequence) { remoteFailed.value = true; remoteItems.value = [] } })
    .finally(() => { if (current === sequence) searching.value = false })
}

watch(keyword, (value) => {
  if (!isRemote.value) return
  if (timer) clearTimeout(timer)
  const query = value.trim()
  if (!query) {
    sequence += 1; searching.value = false; remoteFailed.value = false; remoteItems.value = []
    return
  }
  timer = setTimeout(() => runRemote(query), SEARCH_DEBOUNCE_MS)
})

watch(open, (visible) => {
  if (visible) return
  if (timer) clearTimeout(timer)
  sequence += 1; keyword.value = ''; remoteItems.value = []; searching.value = false; remoteFailed.value = false
})

const isSelected = (value: string) => props.modelValue.includes(value)

function toggleValue(value: string) {
  const text = value.trim()
  if (!text) return
  const next = isSelected(text) ? props.modelValue.filter(item => item !== text) : [...props.modelValue, text]
  emit('update:modelValue', next)
}

function onEnterKeyword() {
  const text = keyword.value.trim()
  keyword.value = ''
  if (!text) return
  if (!props.labels) {
    if (!isSelected(text)) emit('update:modelValue', [...props.modelValue, text])
    return
  }
  if (displayOptions.value.length === 1 && displayOptions.value[0]) toggleValue(displayOptions.value[0])
}

function clearAll() {
  emit('update:modelValue', [])
}

defineExpose({ open, keyword, displayOptions, emptyText, summaryText, searching, remoteFailed, toggleValue, onEnterKeyword, clearAll })
</script>

<template>
  <el-popover
    v-model:visible="open"
    trigger="click"
    placement="bottom-start"
    :width="260"
    :show-arrow="false"
    :teleported="true"
  >
    <template #reference>
      <button
        type="button"
        class="filter-chip"
        :class="{ 'is-active': selectedCount > 0, 'is-open': open }"
        :aria-expanded="open"
        :aria-label="label"
      >
        <template v-if="selectedCount === 0">
          <span class="filter-chip__label">{{ label }}</span>
          <el-icon class="filter-chip__arrow">
            <ArrowDown />
          </el-icon>
        </template>
        <template v-else>
          <span class="filter-chip__key">{{ label }}:</span>
          <span
            class="filter-chip__val"
            :title="fullTooltip"
          >{{ summaryText }}</span>
          <span
            role="button"
            tabindex="0"
            class="filter-chip__clear"
            aria-label="清除"
            @click.stop="clearAll"
            @keydown.enter.stop.prevent="clearAll"
          >
            <el-icon><Close /></el-icon>
          </span>
        </template>
      </button>
    </template>

    <div class="chip-panel">
      <el-input
        v-model="keyword"
        size="small"
        :prefix-icon="Search"
        clearable
        placeholder="搜索或输入后回车添加"
        @keydown.enter.prevent="onEnterKeyword"
      />
      <div class="chip-panel__list">
        <button
          v-for="opt in displayOptions"
          :key="opt"
          type="button"
          class="chip-option"
          :class="{ 'is-selected': isSelected(opt) }"
          @click="toggleValue(opt)"
        >
          <el-icon class="chip-option__check">
            <Check v-if="isSelected(opt)" />
          </el-icon>
          <span class="chip-option__text">{{ optionLabel(opt) }}</span>
        </button>
        <p
          v-if="displayOptions.length === 0"
          class="chip-panel__empty"
        >
          {{ emptyText }}
        </p>
      </div>
      <div
        v-if="selectedCount > 0"
        class="chip-panel__footer"
      >
        <span class="chip-panel__count">已选 {{ selectedCount }} 项</span>
        <button
          type="button"
          class="chip-panel__reset"
          @click="clearAll"
        >
          清空
        </button>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.filter-chip { display: inline-flex; align-items: center; gap: 4px; height: 32px; max-width: 240px; padding: 0 12px; border: 1px solid var(--zt-border-strong); border-radius: 8px; background: var(--zt-panel); color: var(--zt-ink-700); font-size: 13px; line-height: 1; cursor: pointer; transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease; }
.filter-chip:hover { background: var(--zt-soft); border-color: var(--zt-ink-400); color: var(--zt-ink-900); }
.filter-chip.is-open { border-color: var(--zt-blue-600); box-shadow: 0 0 0 3px var(--zt-focus-ring); }
.filter-chip.is-active { background: var(--zt-row-hover); border-color: var(--zt-blue-600); color: var(--zt-blue-700); padding-right: 8px; }
.filter-chip__label, .filter-chip__key { white-space: nowrap; }
.filter-chip__key { font-weight: 500; }
.filter-chip__val { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.filter-chip__arrow { font-size: 12px; color: var(--zt-ink-500); }
.filter-chip__clear { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; margin-left: 4px; border-radius: 50%; color: var(--zt-blue-600); font-size: 12px; cursor: pointer; }
.filter-chip__clear:hover { background: var(--zt-border); color: var(--zt-blue-700); }
.chip-panel { display: flex; flex-direction: column; gap: 8px; }
.chip-panel__list { display: flex; flex-direction: column; gap: 4px; max-height: 240px; overflow-y: auto; }
.chip-option { display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px; border: none; border-radius: 6px; background: transparent; color: var(--zt-ink-700); font-size: 13px; text-align: left; cursor: pointer; }
.chip-option:hover { background: var(--zt-soft); color: var(--zt-ink-900); }
.chip-option.is-selected { background: var(--zt-row-hover); color: var(--zt-blue-700); font-weight: 500; }
.chip-option__check { width: 16px; flex-shrink: 0; color: var(--zt-blue-600); }
.chip-option__text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip-panel__empty { margin: 0; padding: 16px 8px; text-align: center; color: var(--zt-ink-500); font-size: 12px; }
.chip-panel__footer { display: flex; align-items: center; justify-content: space-between; padding-top: 8px; border-top: 1px solid var(--zt-divider); }
.chip-panel__count { font-size: 12px; color: var(--zt-ink-500); }
.chip-panel__reset { padding: 4px 8px; border: none; border-radius: 4px; background: transparent; color: var(--zt-blue-600); font-size: 12px; cursor: pointer; }
.chip-panel__reset:hover { background: var(--zt-row-hover); }
</style>
