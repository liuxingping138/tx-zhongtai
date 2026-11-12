<script setup lang="ts">
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import { DATES, REGIONS, type TenderQuery } from './fields'
const query = defineModel<TenderQuery>({ required: true })
defineProps<{ applied: Record<string, unknown> }>()
const emit = defineEmits<{ search: []; reset: [] }>()
function range(key: typeof DATES[number]['key']): [string, string] | null {
  const from = query.value[`${key}_from`]
  const to = query.value[`${key}_to`]
  return from || to ? [from, to] : null
}
function setRange(key: typeof DATES[number]['key'], value: [string, string] | null) {
  query.value[`${key}_from`] = value?.[0] ?? ''
  query.value[`${key}_to`] = value?.[1] ?? ''
}
</script>
<template>
  <FilterBar
    :query="query"
    :applied="applied"
    @search="emit('search')"
    @reset="emit('reset')"
  >
    <el-form-item label="项目名称">
      <el-input
        v-model="query.project_name"
        placeholder="输入项目名称关键词"
        clearable
      />
    </el-form-item>
    <el-form-item
      v-for="region in REGIONS"
      :key="region.key"
      :label="region.label"
    >
      <el-select
        v-model="query[region.key]"
        multiple
        filterable
        allow-create
        default-first-option
        collapse-tags
        clearable
        placeholder="输入名称，回车添加"
      >
        <el-option
          v-for="value in query[region.key]"
          :key="value"
          :value="value"
          :label="value"
        />
      </el-select>
    </el-form-item>
    <el-form-item label="项目状态">
      <el-select
        v-model="query.project_status"
        aria-label="项目状态"
      >
        <el-option
          value="0"
          label="原始数据（0）"
        />
        <el-option
          value="1"
          label="人工已处理（1）"
        />
      </el-select>
    </el-form-item>
    <el-form-item
      v-for="field in DATES"
      :key="field.key"
      :label="field.label"
      class="filter-form__item--wide"
    >
      <el-date-picker
        :model-value="range(field.key)"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        unlink-panels
        @update:model-value="setRange(field.key, $event)"
      />
    </el-form-item>
    <el-form-item label="项目ID">
      <el-input
        v-model="query.project_content_id"
        placeholder="输入完整项目ID"
        clearable
      />
    </el-form-item>
    <el-form-item label="是否补充场景">
      <FilterSelect
        v-model="query.is_supp_scene"
        :options="['0', '1']"
        :labels="{ '0': '未补充', '1': '已补充' }"
      />
    </el-form-item>
  </FilterBar>
</template>
