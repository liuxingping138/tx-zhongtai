<script setup lang="ts">
import { ArrowDown, Close } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'

export interface DateChipShortcut {
  text: string
  value: () => [Date, Date] | Date[]
}

const props = withDefaults(
  defineProps<{
    modelValue: [string, string] | null
    label: string
    type?: 'daterange' | 'datetimerange'
    valueFormat?: string
    shortcuts?: DateChipShortcut[]
  }>(),
  {
    type: 'daterange',
    valueFormat: 'YYYY-MM-DD',
    shortcuts: undefined,
  },
)

const emit = defineEmits<{ 'update:modelValue': [[string, string] | null] }>()
const open = ref(false)

const hasValue = computed(() => Boolean(props.modelValue?.[0] && props.modelValue?.[1]))

function shortPart(raw: string): string {
  const datePart = raw.split('T')[0] ?? raw
  const year = String(new Date().getFullYear())
  return datePart.startsWith(`${year}-`) ? datePart.slice(5) : datePart
}

const summaryText = computed(() => {
  if (!props.modelValue?.[0] || !props.modelValue?.[1]) return ''
  return `${shortPart(props.modelValue[0])} ~ ${shortPart(props.modelValue[1])}`
})

const fullTooltip = computed(() => {
  if (!props.modelValue?.[0] || !props.modelValue?.[1]) return ''
  return `${props.modelValue[0]} 至 ${props.modelValue[1]}`
})

function formatDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  const base = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  if (props.type === 'datetimerange') {
    return `${base}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  }
  return base
}

function applyShortcut(shortcut: DateChipShortcut) {
  const [from, to] = shortcut.value()
  if (from && to) emit('update:modelValue', [formatDate(from), formatDate(to)])
  open.value = false
}

function onPickerChange(val: [string, string] | null) {
  emit('update:modelValue', val && val[0] && val[1] ? val : null)
}

function clearAll() {
  emit('update:modelValue', null)
}

defineExpose({ open, hasValue, summaryText, clearAll, applyShortcut, onPickerChange })
</script>

<template>
  <el-popover
    v-model:visible="open"
    trigger="click"
    placement="bottom-start"
    :width="320"
    :show-arrow="false"
    :teleported="true"
  >
    <template #reference>
      <button
        type="button"
        class="filter-chip"
        :class="{ 'is-active': hasValue, 'is-open': open }"
        :aria-expanded="open"
        :aria-label="label"
      >
        <template v-if="!hasValue">
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

    <div class="chip-date">
      <div
        v-if="shortcuts?.length"
        class="chip-date__shortcuts"
      >
        <button
          v-for="item in shortcuts"
          :key="item.text"
          type="button"
          class="chip-date__shortcut"
          @click="applyShortcut(item)"
        >
          {{ item.text }}
        </button>
      </div>
      <el-date-picker
        :model-value="modelValue"
        :type="type"
        :value-format="valueFormat"
        range-separator="至"
        start-placeholder="开始"
        end-placeholder="结束"
        unlink-panels
        :teleported="false"
        @update:model-value="onPickerChange"
      />
      <div
        v-if="hasValue"
        class="chip-date__footer"
      >
        <button
          type="button"
          class="chip-date__reset"
          @click="clearAll"
        >
          清空
        </button>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.filter-chip { display: inline-flex; align-items: center; gap: 4px; height: 32px; max-width: 260px; padding: 0 12px; border: 1px solid var(--zt-border-strong); border-radius: 8px; background: var(--zt-panel); color: var(--zt-ink-700); font-size: 13px; line-height: 1; cursor: pointer; transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease; }
.filter-chip:hover { background: var(--zt-soft); border-color: var(--zt-ink-400); color: var(--zt-ink-900); }
.filter-chip.is-open { border-color: var(--zt-blue-600); box-shadow: 0 0 0 3px var(--zt-focus-ring); }
.filter-chip.is-active { background: var(--zt-row-hover); border-color: transparent; color: var(--zt-blue-700); padding-right: 8px; }
.filter-chip.is-active:hover { background: var(--el-color-primary-light-8); border-color: transparent; color: var(--zt-blue-700); }
.filter-chip.is-active.is-open { border-color: var(--zt-blue-600); }
.filter-chip__label, .filter-chip__key { white-space: nowrap; }
.filter-chip__key { font-weight: 500; }
.filter-chip__val { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.filter-chip__arrow { font-size: 12px; color: var(--zt-ink-500); }
.filter-chip__clear { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; margin-left: 4px; border-radius: 50%; color: var(--zt-blue-600); font-size: 12px; cursor: pointer; }
.filter-chip__clear:hover { background: var(--zt-border); color: var(--zt-blue-700); }
.chip-date { display: flex; flex-direction: column; gap: 8px; }
.chip-date__shortcuts { display: flex; flex-wrap: wrap; gap: 6px; }
.chip-date__shortcut { padding: 4px 10px; border: 1px solid var(--zt-border); border-radius: 6px; background: var(--zt-surface-subtle); color: var(--zt-ink-700); font-size: 12px; cursor: pointer; }
.chip-date__shortcut:hover { background: var(--zt-row-hover); border-color: var(--zt-blue-600); color: var(--zt-blue-700); }
.chip-date :deep(.el-date-editor) { width: 100%; }
.chip-date__footer { display: flex; justify-content: flex-end; padding-top: 6px; border-top: 1px solid var(--zt-divider); }
.chip-date__reset { padding: 4px 8px; border: none; border-radius: 4px; background: transparent; color: var(--zt-blue-600); font-size: 12px; cursor: pointer; }
.chip-date__reset:hover { background: var(--zt-row-hover); }
</style>
