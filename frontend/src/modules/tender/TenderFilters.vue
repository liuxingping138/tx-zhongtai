<script setup lang="ts">
import { onMounted, watch } from 'vue'
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useAuthStore } from '@/stores/auth'
import { applyDefaultDateRange, DATES, type TenderQuery } from './fields'

const query = defineModel<TenderQuery>({ required: true })
defineProps<{ applied: Record<string, unknown> }>()
const emit = defineEmits<{ search: []; reset: [] }>()

const auth = useAuthStore()
const areaFilters = useFilterOptions('/codebook/area-codes')
onMounted(() => {
  if (auth.canRead('codebook.area_codes')) void areaFilters.load()
})

// 省份清空时联动重置已选地市和区县
watch(
  () => query.value.purchaser_provname,
  (provinces) => {
    if (!provinces || provinces.length === 0) {
      query.value.purchaser_cityname = []
      query.value.purchaser_countyname = []
    }
  },
)

function onStatusChange(status: string) {
  if (status === '') {
    query.value.project_status = 'all'
  }
  applyDefaultDateRange(query.value)
  emit('search')
}

// 项目状态空值归一化；切换到未通过或全部且无日期时，自动预填近 7 天发布时间
watch(
  () => query.value.project_status,
  (val, oldVal) => {
    if (val === '') {
      query.value.project_status = 'all'
      return
    }
    if ((val === '0' || val === 'all') && val !== oldVal) {
      applyDefaultDateRange(query.value)
    }
  },
  { immediate: true },
)

const ADVANCED_DATES = DATES.filter(field => field.key !== 'public_date')
const SECONDARY_REGIONS = [
  { key: 'purchaser_cityname', optionField: 'city_name', label: '地市', placeholder: '选择或搜索地市' },
  { key: 'purchaser_countyname', optionField: 'county_name', label: '区县', placeholder: '选择或搜索区县' },
] as const

const dateShortcuts = [
  {
    text: '近 7 天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 6)
      return [start, end]
    },
  },
  {
    text: '近 30 天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 29)
      return [start, end]
    },
  },
  {
    text: '近 90 天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 89)
      return [start, end]
    },
  },
]

function range(key: typeof DATES[number]['key']): [string, string] | null {
  const from = query.value[`${key}_from`]
  const to = query.value[`${key}_to`]
  return from && to ? [from, to] : null
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
          placeholder="输入关键词（需选日期范围）"
        />
      </el-form-item>
      <el-form-item label="项目状态">
        <el-select
          v-model="query.project_status"
          placeholder="全部"
          aria-label="项目状态"
          @change="onStatusChange"
        >
          <el-option
            value="all"
            label="全部"
          />
          <el-option
            value="1"
            label="通过"
          />
          <el-option
            value="0"
            label="未通过"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="省份">
        <FilterSelect
          v-model="query.purchaser_provname"
          v-bind="areaFilters.bind('prov_name')"
          placeholder="选择或搜索省份"
          size="short"
        />
      </el-form-item>
      <el-form-item
        label="发布时间"
        class="filter-form__item--wide"
      >
        <el-date-picker
          :model-value="range('public_date')"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="开始"
          end-placeholder="结束"
          unlink-panels
          :shortcuts="dateShortcuts"
          @update:model-value="setRange('public_date', $event)"
        />
      </el-form-item>

      <template #advanced>
        <el-form-item
          v-for="region in SECONDARY_REGIONS"
          :key="region.key"
          :label="region.label"
        >
          <FilterSelect
            v-model="query[region.key]"
            v-bind="areaFilters.bind(region.optionField)"
            :placeholder="region.placeholder"
            size="short"
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
        <el-form-item
          v-for="field in ADVANCED_DATES"
          :key="field.key"
          :label="field.label"
          class="filter-form__item--wide"
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
.tender-filters :deep(.filter-bar__fields) {
  gap: var(--zt-space-3) var(--zt-space-4);
}
.tender-filters :deep(.filter-bar__fields > .el-form-item) {
  flex: 1 1 160px;
  max-width: 240px;
}
.tender-filters :deep(.filter-bar__fields > .el-form-item:first-child) {
  flex: 1.5 1 200px;
  max-width: 280px;
}
</style>
