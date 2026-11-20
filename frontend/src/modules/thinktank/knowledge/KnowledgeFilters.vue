<script setup lang="ts">
import FilterKeyword from '@/components/FilterKeyword.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import type { useFilterOptions } from '@/composables/useFilterOptions'

export interface KnowledgeFilterQuery {
  file_name: string[]
  file_type: string[]
  operator_type: string[]
  product_type: string[]
  product_sub_type: string[]
  industry_type: string[]
  prov_name: string[]
  app_scenario: string[]
  depart_affiliation: string[]
  market_category: string[]
  data_time: string[]
  tag_status: string[]
  favorite_only: string[]
}

defineProps<{
  query: KnowledgeFilterQuery
  filters: ReturnType<typeof useFilterOptions>
}>()

const emit = defineEmits<{
  update: [field: keyof KnowledgeFilterQuery, value: string[]]
}>()

interface FilterDef {
  field: keyof KnowledgeFilterQuery
  label: string
  placeholder: string
  kind: 'keyword' | 'select'
  size?: 'short' | 'medium'
}

const FILTER_DEFS: readonly FilterDef[] = [
  { field: 'file_name', label: '资料名称', placeholder: '输入关键词', kind: 'keyword' },
  { field: 'file_type', label: '文件类型', placeholder: '全部', kind: 'select', size: 'medium' },
  { field: 'operator_type', label: '运营商类型', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'product_type', label: '产品类型', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'industry_type', label: '行业类型', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'prov_name', label: '省份', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'market_category', label: '市场类别', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'depart_affiliation', label: '部门归属', placeholder: '全部', kind: 'select', size: 'medium' },
  { field: 'app_scenario', label: '应用场景', placeholder: '全部', kind: 'select', size: 'medium' },
  { field: 'product_sub_type', label: '产品子类型', placeholder: '输入关键词', kind: 'keyword' },
  { field: 'data_time', label: '资料时间', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'tag_status', label: '定义状态', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'favorite_only', label: '我的收藏', placeholder: '全部', kind: 'select', size: 'short' },
]
</script>

<template>
  <el-form-item
    v-for="item in FILTER_DEFS"
    :key="item.field"
    :label="item.label"
  >
    <FilterKeyword
      v-if="item.kind === 'keyword'"
      :model-value="query[item.field]"
      :label="item.label"
      :placeholder="item.placeholder"
      @update:model-value="emit('update', item.field, $event)"
    />
    <FilterSelect
      v-else
      :model-value="query[item.field]"
      v-bind="filters.bind(item.field)"
      :placeholder="item.placeholder"
      :size="item.size"
      @update:model-value="emit('update', item.field, $event)"
    />
  </el-form-item>
</template>
