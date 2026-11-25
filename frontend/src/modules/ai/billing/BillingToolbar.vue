<script setup lang="ts">
import { RefreshLeft } from '@element-plus/icons-vue'

import { SCENES, type BillingFilters, type RangePreset } from './billing'

defineProps<{
  preset: RangePreset | ''
  range: [string, string]
  daysSpan: number
  filters: BillingFilters
  options: { categories: string[]; purposes: string[]; models: string[] }
  activeFilterCount: number
}>()

const emit = defineEmits<{
  'pick-preset': [value: string | number | boolean | undefined]
  'pick-range': [value: [string, string] | null]
  'update-filter': [key: keyof BillingFilters, value: string[]]
  reset: []
}>()

const PRESETS: { value: RangePreset; label: string }[] = [
  { value: '7', label: '近 7 天' },
  { value: '30', label: '近 30 天' },
  { value: '90', label: '近 90 天' },
  { value: 'month', label: '本月' },
]

function isFutureDate(day: Date): boolean {
  return day.getTime() > Date.now()
}

function onPreset(value: string | number | boolean | undefined): void {
  emit('pick-preset', value)
}

function onRange(value: [string, string] | null): void {
  emit('pick-range', value)
}

function onFilter(key: keyof BillingFilters, value: string[]): void {
  emit('update-filter', key, value)
}
</script>

<template>
  <section
    class="billing__toolbar"
    aria-label="账单范围与维度筛选"
  >
    <div class="billing__toolbar-top">
      <div class="billing__time-group">
        <el-radio-group
          :model-value="preset"
          class="ai-seg"
          aria-label="快捷范围"
          @update:model-value="onPreset"
        >
          <el-radio-button
            v-for="item in PRESETS"
            :key="item.value"
            :value="item.value"
          >
            {{ item.label }}
          </el-radio-button>
        </el-radio-group>
        <el-date-picker
          :model-value="range"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          :clearable="false"
          :disabled-date="isFutureDate"
          aria-label="日期范围"
          class="billing__date-picker"
          @update:model-value="onRange"
        />
        <span class="billing__period-meta">共 {{ daysSpan }} 天 · 北京时间</span>
      </div>
      <div class="billing__toolbar-actions">
        <button
          v-if="activeFilterCount > 0"
          type="button"
          class="billing__reset-btn"
          @click="emit('reset')"
        >
          <el-icon><RefreshLeft /></el-icon>
          <span>已选 {{ activeFilterCount }} 项筛选 · 重置</span>
        </button>
      </div>
    </div>

    <div class="billing__filters">
      <div
        class="billing__cascade"
        role="group"
        aria-label="业务归属三级联动"
      >
        <span class="billing__filter-tag">业务归属</span>
        <el-select
          :model-value="filters.scenes"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          clearable
          size="small"
          placeholder="全部业务分类"
          aria-label="业务分类"
          class="billing__select"
          :class="{ 'is-picked': filters.scenes.length > 0 }"
          @update:model-value="(val: string[]) => onFilter('scenes', val)"
        >
          <el-option
            v-for="item in SCENES"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>
        <span
          class="billing__cascade-arrow"
          aria-hidden="true"
        >›</span>
        <el-select
          :model-value="filters.categories"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          clearable
          size="small"
          placeholder="全部一级业务板块"
          aria-label="一级业务板块"
          class="billing__select"
          :class="{ 'is-picked': filters.categories.length > 0 }"
          @update:model-value="(val: string[]) => onFilter('categories', val)"
        >
          <el-option
            v-for="item in options.categories"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>
        <span
          class="billing__cascade-arrow"
          aria-hidden="true"
        >›</span>
        <el-select
          :model-value="filters.purposes"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          clearable
          size="small"
          placeholder="全部二级业务板块"
          aria-label="二级业务板块"
          class="billing__select"
          :class="{ 'is-picked': filters.purposes.length > 0 }"
          @update:model-value="(val: string[]) => onFilter('purposes', val)"
        >
          <el-option
            v-for="item in options.purposes"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>
      </div>
      <div
        class="billing__v-divider"
        aria-hidden="true"
      />
      <div class="billing__model-slot">
        <span class="billing__filter-tag">模型</span>
        <el-select
          :model-value="filters.models"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          clearable
          size="small"
          placeholder="全部模型"
          aria-label="模型"
          class="billing__select"
          :class="{ 'is-picked': filters.models.length > 0 }"
          @update:model-value="(val: string[]) => onFilter('models', val)"
        >
          <el-option
            v-for="item in options.models"
            :key="item"
            :label="item"
            :value="item"
          />
        </el-select>
      </div>
    </div>
  </section>
</template>
