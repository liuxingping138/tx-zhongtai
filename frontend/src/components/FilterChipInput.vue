<script setup lang="ts">
import { ArrowDown, Close } from '@element-plus/icons-vue'
import { computed, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    label: string
    placeholder?: string
    prefix?: string
    inputmode?: 'text' | 'numeric'
  }>(),
  {
    placeholder: '输入内容后回车',
    prefix: '',
    inputmode: 'text',
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const open = ref(false)
const draft = ref(props.modelValue)

watch(() => props.modelValue, (val) => {
  draft.value = val
})

watch(open, (visible) => {
  if (visible) draft.value = props.modelValue
})

const hasValue = computed(() => props.modelValue.trim().length > 0)
const summaryText = computed(() => `${props.prefix}${props.modelValue.trim()}`)

function applyDraft() {
  emit('update:modelValue', draft.value.trim())
  open.value = false
}

function clearAll() {
  draft.value = ''
  emit('update:modelValue', '')
}

defineExpose({ open, draft, hasValue, summaryText, applyDraft, clearAll })
</script>

<template>
  <el-popover
    v-model:visible="open"
    trigger="click"
    placement="bottom-start"
    :width="240"
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
            :title="summaryText"
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

    <div class="chip-input">
      <el-input
        v-model="draft"
        size="small"
        clearable
        :inputmode="inputmode"
        :placeholder="placeholder"
        @keydown.enter.prevent="applyDraft"
      />
      <div class="chip-input__footer">
        <button
          v-if="hasValue"
          type="button"
          class="chip-input__reset"
          @click="clearAll"
        >
          清空
        </button>
        <el-button
          size="small"
          type="primary"
          @click="applyDraft"
        >
          确定
        </el-button>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.filter-chip { display: inline-flex; align-items: center; gap: 4px; height: 32px; max-width: 240px; padding: 0 12px; border: 1px solid var(--zt-border-strong); border-radius: 8px; background: var(--zt-panel); color: var(--zt-ink-700); font-size: 13px; line-height: 1; cursor: pointer; transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease; }
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
.chip-input { display: flex; flex-direction: column; gap: 8px; }
.chip-input__footer { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
.chip-input__reset { margin-right: auto; padding: 4px 8px; border: none; border-radius: 4px; background: transparent; color: var(--zt-blue-600); font-size: 12px; cursor: pointer; }
.chip-input__reset:hover { background: var(--zt-row-hover); }
</style>
