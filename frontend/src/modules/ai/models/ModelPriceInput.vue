<script setup lang="ts">
import { computed } from 'vue'

import { livePriceBadge } from './modelView'

const props = defineProps<{
  modelValue: string
  label: string
  required?: boolean
  placeholder?: string
  disabled?: boolean
  inputId?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const badge = computed(() => livePriceBadge(props.modelValue))

function onInput(event: Event) {
  emit('update:modelValue', (event.target as HTMLInputElement).value)
}
</script>

<template>
  <div class="mp-field">
    <label
      class="mp-label"
      :for="inputId"
    >
      {{ label }}
      <span
        v-if="required"
        class="mp-req"
      >*</span>
    </label>
    <div class="mp-wrap">
      <input
        :id="inputId"
        type="text"
        inputmode="decimal"
        maxlength="20"
        class="mp-input models-mono"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        @input="onInput"
      >
      <span
        class="mp-badge models-mono"
        :class="`is-${badge.tone}`"
      >{{ badge.text }}</span>
    </div>
  </div>
</template>

<style scoped>
.mp-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.mp-label { color: var(--zt-ink-900); font-size: 12.5px; font-weight: 600; line-height: 1.35; }
.mp-req { margin-left: 2px; color: var(--zt-danger-text); }
.mp-wrap { position: relative; display: flex; align-items: center; }
.mp-input {
  width: 100%; height: 36px; padding: 0 112px 0 11px;
  border: 1px solid var(--zt-border-strong); border-radius: 8px;
  background: var(--zt-panel); color: var(--zt-ink-900); font-size: 13px; outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.mp-input::placeholder { color: var(--zt-ink-400); font-family: var(--zt-font); font-size: 12px; }
.mp-input:focus:not(:disabled) {
  border-color: var(--zt-blue-600);
  box-shadow: 0 0 0 3px var(--zt-focus-ring);
}
.mp-input:disabled {
  background: var(--zt-surface-subtle); color: var(--zt-ink-400); cursor: not-allowed;
}
.mp-badge {
  position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
  padding: 2px 7px; border-radius: 5px; font-size: 11px; line-height: 1.35;
  pointer-events: none; white-space: nowrap;
}
.mp-badge.is-muted { border: 1px solid var(--zt-border); background: var(--zt-surface-subtle); color: var(--zt-ink-500); }
.mp-badge.is-warn { border: 1px solid var(--zt-warning-border); background: var(--zt-warning-soft); color: var(--zt-warning-text); font-weight: 600; }
.mp-badge.is-primary {
  border: 1px solid var(--el-color-primary-light-7); background: var(--el-color-primary-light-9);
  color: var(--zt-blue-600); font-weight: 600;
}
</style>
