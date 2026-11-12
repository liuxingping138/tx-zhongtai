<script setup lang="ts">
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import { DATES, type TenderQuery } from './fields'

const query = defineModel<TenderQuery>({ required: true })
defineProps<{ applied: Record<string, unknown> }>()
const emit = defineEmits<{ search: []; reset: [] }>()

const ADVANCED_DATES = DATES.filter(field => field.key !== 'collect_date')
const SECONDARY_REGIONS = [
  { key: 'purchaser_cityname', label: '地市' },
  { key: 'purchaser_countyname', label: '区县' },
] as const

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
  <div class="tender-filters">
    <FilterBar
      :query="query"
      :applied="applied"
      @search="emit('search')"
      @reset="emit('reset')"
    >
      <el-form-item label="项目名称">
        <el-input
          v-model="query.project_name"
          clearable
          placeholder="输入项目名称关键词"
          @keyup.enter="emit('search')"
        />
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
      <el-form-item label="省份">
        <el-select
          v-model="query.purchaser_provname"
          multiple
          filterable
          allow-create
          default-first-option
          collapse-tags
          clearable
          placeholder="输入省份回车"
        >
          <el-option
            v-for="value in query.purchaser_provname"
            :key="value"
            :value="value"
            :label="value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="采集时间">
        <el-date-picker
          :model-value="range('collect_date')"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="开始"
          end-placeholder="结束"
          unlink-panels
          @update:model-value="setRange('collect_date', $event)"
        />
      </el-form-item>

      <template #advanced>
        <el-form-item
          v-for="region in SECONDARY_REGIONS"
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
            placeholder="输入名称回车"
          >
            <el-option
              v-for="value in query[region.key]"
              :key="value"
              :value="value"
              :label="value"
            />
          </el-select>
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
        <el-form-item
          v-for="field in ADVANCED_DATES"
          :key="field.key"
          :label="field.label"
        >
          <el-date-picker
            :model-value="range(field.key)"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            unlink-panels
            @update:model-value="setRange(field.key, $event)"
          />
        </el-form-item>
      </template>
    </FilterBar>
  </div>
</template>

<style scoped>
.tender-filters :deep(.filter-bar__fields) { gap: 8px 10px; }
.tender-filters :deep(.filter-bar__fields > .el-form-item) { flex: 1 1 140px; max-width: 210px; }
.tender-filters :deep(.filter-bar__fields > .el-form-item:first-child) { flex: 1.3 1 180px; max-width: 260px; }
.tender-filters :deep(.el-form-item__label) { margin-bottom: 3px; font-size: 12px; line-height: 16px; }
.tender-filters :deep(.el-input__wrapper),
.tender-filters :deep(.el-select__wrapper),
.tender-filters :deep(.el-date-editor) { min-height: 32px; height: 32px; }
</style>
