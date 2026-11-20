<script setup lang="ts">
import { Search } from '@element-plus/icons-vue'
import { onMounted, watch } from 'vue'
import FilterBar from '@/components/FilterBar.vue'
import FilterChipDate from '@/components/FilterChipDate.vue'
import FilterChipInput from '@/components/FilterChipInput.vue'
import FilterChipSelect from '@/components/FilterChipSelect.vue'
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
      variant="chips"
      :more-keys="['project_content_id', 'collect_date_from', 'create_time_from']"
      @search="emit('search')"
      @reset="emit('reset')"
    >
      <template #search>
        <el-radio-group
          v-model="query.project_status"
          class="tender-filters__status"
          aria-label="项目状态"
          @change="(val: string | number | boolean | undefined) => onStatusChange(String(val ?? 'all'))"
        >
          <el-radio-button value="all">
            全部
          </el-radio-button>
          <el-radio-button value="1">
            通过
          </el-radio-button>
          <el-radio-button value="0">
            未通过
          </el-radio-button>
        </el-radio-group>
        <el-input
          v-model="query.project_name"
          class="tender-filters__name"
          :prefix-icon="Search"
          clearable
          placeholder="搜索项目名称关键词（需选日期范围）…"
          aria-label="项目名称"
        />
        <el-date-picker
          :model-value="range('public_date')"
          class="tender-filters__date"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="发布开始"
          end-placeholder="发布结束"
          unlink-panels
          :shortcuts="dateShortcuts"
          aria-label="发布时间"
          @update:model-value="setRange('public_date', $event)"
        />
      </template>

      <FilterChipSelect
        v-model="query.purchaser_provname"
        label="省份"
        v-bind="areaFilters.bind('prov_name')"
      />
      <FilterChipSelect
        v-for="region in SECONDARY_REGIONS"
        :key="region.key"
        v-model="query[region.key]"
        :label="region.label"
        v-bind="areaFilters.bind(region.optionField)"
      />
      <FilterChipSelect
        v-model="query.is_supp_scene"
        label="是否补充场景"
        :options="['0', '1']"
        :labels="{ '0': '未补充', '1': '已补充' }"
      />

      <template #more>
        <FilterChipInput
          v-model="query.project_content_id"
          label="项目ID"
          placeholder="输入完整项目ID"
        />
        <FilterChipDate
          v-for="field in ADVANCED_DATES"
          :key="field.key"
          :model-value="range(field.key)"
          :label="field.label"
          :shortcuts="dateShortcuts"
          @update:model-value="setRange(field.key, $event)"
        />
      </template>
    </FilterBar>
  </div>
</template>

<style scoped>
.tender-filters__status :deep(.el-radio-button__inner) {
  height: 36px;
  line-height: 34px;
  padding: 0 12px;
}
.tender-filters__name {
  flex: 1.5 1 240px;
  max-width: 340px;
}
.tender-filters__date {
  flex: 0 1 260px;
  max-width: 280px;
}
</style>
