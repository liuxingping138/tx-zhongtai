<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

/**
 * 码表可搜索单选下拉框（省份、一级行业等）。
 *
 * Element Plus 在同时开启 allow-create + default-first-option 时，会把用户刚输入的半截搜索词
 * 当作「新建项」排在已有候选前面并默认高亮（例如输入「广东」回车会选中「广东」而非「广东省」），
 * 且当初始候选为空时动态挂载新建项会被内部 updateHoveringIndex 重置高亮导致回车无响应。
 * 这里直接把匹配的码表项排在前面、未精确命中的自定义输入词追加在末尾，使回车默认优先选中码表项，
 * 同时仍支持方向键下移或点击选中自定义短词，以及在码表为空时直接输入回车创建。
 */
const props = withDefaults(defineProps<{
  modelValue: string
  options?: string[]
  placeholder?: string
  size?: '' | 'small' | 'default' | 'large'
  disabled?: boolean
}>(), {
  options: () => [],
  placeholder: '搜索或选择',
  size: undefined,
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

interface SelectStates {
  states: { hoveringIndex: number }
  filteredOptionsCount: number
}

const selectRef = ref<SelectStates | null>(null)
const keyword = ref('')

const shownOptions = computed(() => {
  const query = keyword.value.trim()
  if (query) {
    const lower = query.toLowerCase()
    const matched = props.options.filter(item => item.toLowerCase().includes(lower))
    return matched.includes(query) ? matched : [...matched, query]
  }
  const current = props.modelValue.trim()
  if (current && !props.options.includes(current)) {
    return [current, ...props.options]
  }
  return props.options
})

watch(shownOptions, async list => {
  if (!keyword.value.trim() || !list.length) return
  await nextTick()
  if (selectRef.value && selectRef.value.states.hoveringIndex < 0 && selectRef.value.filteredOptionsCount > 0) {
    selectRef.value.states.hoveringIndex = 0
  }
}, { flush: 'post' })

function onFilter(query: string): void {
  keyword.value = query
}

function onVisibleChange(visible: boolean): void {
  if (!visible) keyword.value = ''
}

function onChange(value: string | undefined): void {
  emit('update:modelValue', (value ?? '').trim())
}
</script>

<template>
  <el-select
    ref="selectRef"
    :model-value="modelValue"
    :size="size"
    filterable
    clearable
    default-first-option
    :placeholder="placeholder"
    :disabled="disabled"
    :filter-method="onFilter"
    @visible-change="onVisibleChange"
    @update:model-value="onChange"
  >
    <el-option
      v-for="name in shownOptions"
      :key="name"
      :label="name"
      :value="name"
    />
  </el-select>
</template>
