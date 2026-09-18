<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    options: string[]
    labels?: Record<string, string>
    placeholder?: string
    size?: 'short' | 'medium'
  }>(),
  { placeholder: '输入或选择', size: 'medium' },
)

function optionLabel(value: string): string {
  return props.labels?.[value] || value
}

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const MAX_SHOWN = 80
const keyword = ref('')

const shown = computed(() => {
  const query = keyword.value.trim()
  const source = props.options
  const matched = query
    ? source.filter((item) => {
        const needle = query.toLowerCase()
        return item.toLowerCase().includes(needle) || optionLabel(item).toLowerCase().includes(needle)
      })
    : source
  return matched.slice(0, MAX_SHOWN)
})

function onFilter(query: string) {
  keyword.value = query
}

function onChange(value: string | null) {
  emit('update:modelValue', value ?? '')
}
</script>

<template>
  <el-select
    class="filter-select"
    :class="{ 'filter-select--short': size === 'short' }"
    :model-value="modelValue"
    filterable
    allow-create
    default-first-option
    clearable
    :placeholder="placeholder"
    :filter-method="onFilter"
    @visible-change="(open: boolean) => { if (!open) keyword = '' }"
    @update:model-value="onChange"
  >
    <el-option
      v-for="opt in shown"
      :key="opt"
      :label="optionLabel(opt)"
      :value="opt"
    />
  </el-select>
</template>
