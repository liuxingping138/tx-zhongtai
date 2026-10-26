<script setup lang="ts">
import { computed } from 'vue'
import { Search } from '@element-plus/icons-vue'

/**
 * 输入关键词模糊查找，不给候选值：政策名称这类几百万行的长文本字段用它，去重取候选会扫整张表。
 * 和 FilterSelect 一样以 string[] 做 v-model（空数组表示不筛选），后端照旧按 ilike_any 模糊匹配，
 * 导出、地址栏恢复都不用改。回车直接查询。
 */
const props = withDefaults(defineProps<{ modelValue: string[]; placeholder?: string; label?: string }>(), {
  placeholder: '输入关键词',
  label: undefined,
})
const emit = defineEmits<{ 'update:modelValue': [value: string[]]; search: [] }>()
const text = computed({
  get: () => props.modelValue[0] ?? '',
  set: (value: string | undefined) => emit('update:modelValue', value?.trim() ? [value] : []),
})
</script>

<template>
  <el-input
    v-model="text"
    :prefix-icon="Search"
    clearable
    :placeholder="placeholder"
    :aria-label="label"
    @keyup.enter="emit('search')"
  />
</template>
