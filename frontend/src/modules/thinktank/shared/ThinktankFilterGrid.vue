<script setup lang="ts">
import FilterKeyword from '@/components/FilterKeyword.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import type { useFilterOptions } from '@/composables/useFilterOptions'

export interface ThinktankFilterDef {
  field: string
  label: string
  placeholder: string
  kind: 'keyword' | 'select'
  size?: 'short' | 'medium'
  fallbackOptions?: readonly string[]
}

const props = defineProps<{
  defs: readonly ThinktankFilterDef[]
  query: Record<string, string[]>
  filters: ReturnType<typeof useFilterOptions>
}>()

const emit = defineEmits<{
  update: [field: string, value: string[]]
}>()

function bindField(def: ThinktankFilterDef) {
  const bound = props.filters.bind(def.field)
  if (bound.options.length > 0 || !def.fallbackOptions?.length) return bound
  return { ...bound, options: [...def.fallbackOptions] }
}
</script>

<template>
  <el-form-item
    v-for="item in defs"
    :key="item.field"
    :label="item.label"
  >
    <FilterKeyword
      v-if="item.kind === 'keyword'"
      :model-value="query[item.field] ?? []"
      :label="item.label"
      :placeholder="item.placeholder"
      @update:model-value="emit('update', item.field, $event)"
    />
    <FilterSelect
      v-else
      :model-value="query[item.field] ?? []"
      v-bind="bindField(item)"
      :placeholder="item.placeholder"
      :size="item.size"
      @update:model-value="emit('update', item.field, $event)"
    />
  </el-form-item>
</template>
