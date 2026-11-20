<script setup lang="ts">
import { Check, Star } from '@element-plus/icons-vue'
import { computed } from 'vue'

import FilterChipSelect from '@/components/FilterChipSelect.vue'
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

const props = withDefaults(
  defineProps<{
    query: KnowledgeFilterQuery
    filters: ReturnType<typeof useFilterOptions>
    group?: 'primary' | 'more'
  }>(),
  { group: 'primary' },
)

const emit = defineEmits<{
  update: [field: keyof KnowledgeFilterQuery, value: string[]]
}>()

interface ChipFilterDef {
  field: keyof KnowledgeFilterQuery
  label: string
}

const PRIMARY_CHIPS: readonly ChipFilterDef[] = [
  { field: 'file_type', label: '文件类型' },
  { field: 'operator_type', label: '运营商' },
  { field: 'product_type', label: '产品类型' },
  { field: 'industry_type', label: '行业类型' },
  { field: 'prov_name', label: '省份' },
]

const MORE_CHIPS: readonly ChipFilterDef[] = [
  { field: 'market_category', label: '市场类别' },
  { field: 'depart_affiliation', label: '部门归属' },
  { field: 'app_scenario', label: '应用场景' },
  { field: 'data_time', label: '资料时间' },
  { field: 'tag_status', label: '定义状态' },
]

const activeDefs = computed(() => (props.group === 'more' ? MORE_CHIPS : PRIMARY_CHIPS))
const isFavoriteOnly = computed(() => props.query.favorite_only.length > 0)

function toggleFavoriteOnly() {
  emit('update', 'favorite_only', isFavoriteOnly.value ? [] : ['仅已收藏'])
}
</script>

<template>
  <FilterChipSelect
    v-for="item in activeDefs"
    :key="item.field"
    :model-value="query[item.field]"
    :label="item.label"
    v-bind="filters.bind(item.field)"
    @update:model-value="emit('update', item.field, $event)"
  />
  <button
    v-if="group === 'primary'"
    type="button"
    class="fav-chip"
    :class="{ 'is-active': isFavoriteOnly }"
    :aria-pressed="isFavoriteOnly"
    @click="toggleFavoriteOnly"
  >
    <el-icon><Check v-if="isFavoriteOnly" /><Star v-else /></el-icon>
    <span>仅看收藏</span>
  </button>
</template>

<style scoped>
.fav-chip { display: inline-flex; align-items: center; gap: 4px; height: 32px; padding: 0 12px; border: 1px solid var(--zt-border-strong); border-radius: 8px; background: var(--zt-panel); color: var(--zt-ink-700); font-size: 13px; line-height: 1; cursor: pointer; transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease; }
.fav-chip:hover { background: var(--zt-soft); border-color: var(--zt-ink-400); color: var(--zt-ink-900); }
.fav-chip.is-active { background: var(--zt-warning-soft); border-color: transparent; color: var(--zt-warning-text); font-weight: 500; }
</style>
