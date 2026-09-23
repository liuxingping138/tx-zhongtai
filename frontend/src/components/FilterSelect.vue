<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 多选：同一字段选多个值是「或」。空数组表示不筛选。 */
    modelValue: string[]
    options: string[]
    labels?: Record<string, string>
    placeholder?: string
    size?: 'short' | 'medium'
    /**
     * 候选值过多时由调用方提供。传了它就改走服务端搜索：
     * 未输入关键词时展示 options 打底，输入后按关键词向后端取。
     */
    remoteSearch?: (keyword: string) => Promise<string[]>
  }>(),
  { placeholder: '输入或选择', size: 'medium', labels: undefined, remoteSearch: undefined },
)

function optionLabel(value: string): string {
  return props.labels?.[value] || value
}

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const MAX_SHOWN = 80
const SEARCH_DEBOUNCE_MS = 250

const keyword = ref('')
const remoteItems = ref<string[]>([])
const searching = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null
let sequence = 0

const isRemote = computed(() => typeof props.remoteSearch === 'function')

const shown = computed(() => {
  const query = keyword.value.trim()
  // 服务端搜索模式下，输入了关键词就用后端返回的结果，没输入则用打底列表。
  const source = isRemote.value && query ? remoteItems.value : props.options
  if (isRemote.value && query) {
    return source.slice(0, MAX_SHOWN)
  }
  const matched = query
    ? source.filter((item) => {
        const needle = query.toLowerCase()
        return item.toLowerCase().includes(needle) || optionLabel(item).toLowerCase().includes(needle)
      })
    : source
  return matched.slice(0, MAX_SHOWN)
})

/** 已选中但不在当前候选里的值也要能显示出来，否则回填的筛选条件会变空白。 */
const withSelected = computed(() => {
  const list = shown.value
  const missing = props.modelValue.filter(value => !list.includes(value))
  return missing.length ? [...missing, ...list] : list
})

const emptyText = computed(() => {
  if (searching.value) return '搜索中…'
  if (isRemote.value && !keyword.value.trim()) return '候选较多，输入关键词搜索'
  return '无匹配项'
})

function runRemote(query: string) {
  const search = props.remoteSearch
  if (!search) return
  const current = ++sequence
  searching.value = true
  void search(query)
    .then((items) => {
      if (current !== sequence) return
      remoteItems.value = items
    })
    .catch(() => {
      if (current !== sequence) return
      remoteItems.value = []
    })
    .finally(() => {
      if (current === sequence) searching.value = false
    })
}

watch(keyword, (value) => {
  if (!isRemote.value) return
  if (timer) clearTimeout(timer)
  const query = value.trim()
  if (!query) {
    sequence += 1
    searching.value = false
    remoteItems.value = []
    return
  }
  timer = setTimeout(() => runRemote(query), SEARCH_DEBOUNCE_MS)
})

function onFilter(query: string) {
  keyword.value = query
}

function reset() {
  if (timer) clearTimeout(timer)
  sequence += 1
  keyword.value = ''
  remoteItems.value = []
  searching.value = false
}

function onChange(value: string[] | null) {
  // 去掉首尾空格和重复值：手动输入的「 广东 」与候选里的「广东」是同一个条件。
  const next: string[] = []
  for (const item of value ?? []) {
    const text = String(item).trim()
    if (text && !next.includes(text)) next.push(text)
  }
  emit('update:modelValue', next)
}
</script>

<template>
  <el-select
    class="filter-select"
    :class="{ 'filter-select--short': size === 'short' }"
    :model-value="modelValue"
    multiple
    collapse-tags
    collapse-tags-tooltip
    :max-collapse-tags="1"
    filterable
    :allow-create="!labels"
    :reserve-keyword="false"
    default-first-option
    clearable
    :loading="searching"
    :placeholder="placeholder"
    :no-data-text="emptyText"
    :no-match-text="emptyText"
    :filter-method="onFilter"
    @visible-change="(open: boolean) => { if (!open) reset() }"
    @update:model-value="onChange"
  >
    <el-option
      v-for="opt in withSelected"
      :key="opt"
      :label="optionLabel(opt)"
      :value="opt"
    />
  </el-select>
</template>
