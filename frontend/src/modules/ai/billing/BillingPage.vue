<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getAiBilling, type BillingRow } from '@/api/aiBilling'
import { errorMessage } from '@/api/errors'
import BaseChart from '@/components/charts/BaseChart.vue'
import { useChartPalette } from '@/components/charts/echarts'
import CardSkeleton from '@/components/CardSkeleton.vue'
import ChartSkeleton from '@/components/ChartSkeleton.vue'
import { useTheme } from '@/composables/useTheme'
import {
  buildLedgerCards, colorMap, countActiveFilters, dailySeries, daysBetween,
  filterOptions, filterRows, groupBy, money, OTHER, presetRange, pruneInPlace, summarize,
  type BillingFilters, type GroupKey, type RangePreset,
} from './billing'
import { costOption } from './billingChart'
import BillingTable from './BillingTable.vue'
import BillingToolbar from './BillingToolbar.vue'
import '../shared/ai.css'

/** 所有模型调用的花费：批量任务、定时打标、样本试跑、试发，以及已下线的多轮对话留下的记录。改日期重新取数，
 * 业务分类 → 一级业务板块 → 二级业务板块三级联动、模型独立，都在页面上直接筛，账本指标、图表和明细跟着变。 */
const route = useRoute()
const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })

const preset = ref<RangePreset | ''>('30')
const range = ref<[string, string]>(presetRange('30', today))
const rows = ref<BillingRow[]>([])
const loading = ref(false)
const error = ref('')
// 从任务调度「查看账单」跳过来时带着用途（二级业务板块），进来就筛好。
const initialPurposes = [route.query.purpose].flat().filter((item): item is string => typeof item === 'string' && !!item)
const filters = reactive<BillingFilters>({
  scenes: [],
  categories: [],
  purposes: initialPurposes,
  models: [],
})
const colorBy = ref<'model' | 'purpose'>(initialPurposes.length ? 'purpose' : 'model')
const tab = ref<GroupKey>(initialPurposes.length ? 'purpose' : 'model')
const hoveredSeries = ref<string | null>(null)
const hoveredDay = ref<string | null>(null)
const palette = useChartPalette()
const { isDark } = useTheme()

const options = computed(() => filterOptions(rows.value, filters))
const shown = computed(() => filterRows(rows.value, filters))
const total = computed(() => summarize(shown.value))
const daysSpan = computed(() => daysBetween(range.value[0], range.value[1]).length)
const ledgerCards = computed(() => buildLedgerCards(shown.value, daysSpan.value))
const activeFilterCount = computed(() => countActiveFilters(filters))
const initialLoading = computed(() => loading.value && rows.value.length === 0)
const colors = computed(() => colorMap(rows.value, colorBy.value, isDark.value))
const chart = computed(() => dailySeries(shown.value, range.value[0], range.value[1], colorBy.value, colors.value, isDark.value))
const option = computed(() => costOption(chart.value.days, chart.value.series, palette.value))
const hoveredDayIndex = computed(() => {
  if (!hoveredDay.value) return null
  const idx = chart.value.days.indexOf(hoveredDay.value)
  return idx >= 0 ? idx : null
})
const tabCounts = computed<Record<GroupKey, number>>(() => ({
  model: new Set(shown.value.map(row => row.model)).size,
  purpose: new Set(shown.value.map(row => row.purpose)).size,
  day: new Set(shown.value.map(row => row.day)).size,
}))
const chartLabel = computed(() =>
  `每日费用：${range.value[0]} 至 ${range.value[1]} 合计 ${money(total.value.cost)}。${groupBy(shown.value, colorBy.value)
    .slice(0, 5).map(group => `${group.name} ${money(group.cost)}`).join('；')}`,
)
const groups = computed(() => groupBy(shown.value, tab.value))

let sequence = 0
async function load(): Promise<void> {
  const current = ++sequence
  loading.value = true
  try {
    const data = await getAiBilling(range.value[0], range.value[1])
    if (current !== sequence) return
    rows.value = data.items
    error.value = ''
  } catch (cause) {
    if (current === sequence) error.value = errorMessage(cause, '账单加载失败，请重试')
  } finally {
    if (current === sequence) loading.value = false
  }
}

/** 上一级改了，下一级选不到的值去掉。只在人改上一级时修剪：刚换日期、数据还没回来时不能把带进来的用途清掉。 */
function pruneBelow(): void {
  pruneInPlace(rows.value, filters)
}

function pickPreset(value: string | number | boolean | undefined): void {
  preset.value = value as RangePreset
  range.value = presetRange(preset.value, today)
}

function pickRange(value: [string, string] | null): void {
  if (!value) return
  preset.value = ''
  range.value = value
}

function updateFilter(key: keyof BillingFilters, value: string[]): void {
  filters[key] = value
}

function resetAllFilters(): void {
  filters.scenes = []
  filters.categories = []
  filters.purposes = []
  filters.models = []
}

function onTabChange(next: GroupKey): void {
  tab.value = next
  hoveredSeries.value = null
  hoveredDay.value = null
  if (next === 'model' || next === 'purpose') colorBy.value = next
}

function toggleFocus(dimension: 'model' | 'purpose', name: string): void {
  if (!name || name === OTHER) return
  if (dimension === 'model') {
    filters.models = filters.models.length === 1 && filters.models[0] === name ? [] : [name]
  } else {
    filters.purposes = filters.purposes.length === 1 && filters.purposes[0] === name ? [] : [name]
  }
}

function onRowClick(name: string): void {
  if (tab.value === 'model' || tab.value === 'purpose') toggleFocus(tab.value, name)
}

function onChartSelect(params: { seriesName?: string }): void {
  if (!params.seriesName || params.seriesName === OTHER) return
  tab.value = colorBy.value
  toggleFocus(colorBy.value, params.seriesName)
}

watch(() => [filters.scenes, filters.categories], pruneBelow)
watch(range, () => void load())
onMounted(load)
</script>

<template>
  <div class="billing">
    <h1 class="ai-sr-only">
      费用账单
    </h1>

    <BillingToolbar
      :preset="preset"
      :range="range"
      :days-span="daysSpan"
      :filters="filters"
      :options="options"
      :active-filter-count="activeFilterCount"
      @pick-preset="pickPreset"
      @pick-range="pickRange"
      @update-filter="updateFilter"
      @reset="resetAllFilters"
    />

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    >
      <el-button
        size="small"
        type="danger"
        plain
        @click="load()"
      >
        重试
      </el-button>
    </el-alert>

    <CardSkeleton
      v-if="initialLoading"
      :count="5"
      :columns="5"
      variant="kpi"
    />
    <section
      v-else
      class="billing__ledger"
      aria-label="合计"
    >
      <div
        v-for="card in ledgerCards"
        :key="card.key"
        class="billing__metric"
        :class="{ 'billing__metric--hero': card.main }"
      >
        <div class="billing__metric-head">
          <span class="billing__metric-label">{{ card.label }}</span>
          <span
            v-if="card.badge"
            class="billing__metric-rate"
            :class="{ 'is-zero': !card.progress }"
          >{{ card.badge }}</span>
        </div>
        <strong
          v-if="card.moneyParts"
          class="billing__hero-money"
          :title="card.value"
          :aria-label="`${card.label} ${card.value}`"
        >
          <span class="billing__hero-sym">{{ card.moneyParts.symbol }}</span>
          <span class="billing__hero-int">{{ card.moneyParts.integer }}</span>
          <span class="billing__hero-dec">{{ card.moneyParts.decimal }}</span>
        </strong>
        <strong
          v-else
          class="billing__metric-value"
          :title="card.value"
        >{{ card.value }}</strong>
        <div class="billing__metric-foot">
          <div
            v-if="card.splitBar"
            class="billing__micro-bar"
            aria-hidden="true"
          >
            <span
              v-if="card.splitBar.primary > 0"
              class="billing__micro-fill billing__micro-fill--primary"
              :style="{ width: `${Math.max(card.splitBar.primary * 100, 4)}%` }"
            />
            <span
              v-if="card.splitBar.secondary > 0"
              class="billing__micro-fill billing__micro-fill--ai"
              :style="{ width: `${Math.max(card.splitBar.secondary * 100, 4)}%` }"
            />
          </div>
          <div
            v-else-if="typeof card.progress === 'number'"
            class="billing__micro-bar"
            aria-hidden="true"
          >
            <span
              class="billing__micro-fill"
              :style="{ width: `${Math.max(card.progress * 100, card.progress > 0 ? 3 : 0)}%` }"
            />
          </div>
          <small
            class="billing__metric-note"
            :title="card.note"
          >{{ card.note }}</small>
        </div>
      </div>
    </section>

    <section
      class="billing__panel"
      :class="{ 'is-refreshing': loading && rows.length > 0 }"
      aria-label="每日费用趋势"
    >
      <header class="billing__panel-head">
        <div class="billing__title-wrap">
          <h2 class="billing__title">
            每日费用
          </h2>
          <p class="billing__subtitle">
            {{ range[0] }} 至 {{ range[1] }} · 批量任务的费用计入发起当日，悬停查看当日分项与日均对比
          </p>
        </div>
        <el-radio-group
          v-model="colorBy"
          size="small"
          class="ai-seg"
          aria-label="分色方式"
        >
          <el-radio-button value="model">
            按模型
          </el-radio-button>
          <el-radio-button value="purpose">
            按二级业务板块
          </el-radio-button>
        </el-radio-group>
      </header>
      <div class="billing__chart-body">
        <ChartSkeleton
          v-if="initialLoading"
          height="296px"
          :bars="9"
        />
        <BaseChart
          v-else-if="shown.length"
          :option="option"
          :label="chartLabel"
          :highlighted-series="hoveredSeries"
          :active-data-index="hoveredDayIndex"
          height="296px"
          @select="onChartSelect"
        />
        <div
          v-else
          class="billing__empty"
        >
          <span>这段时间没有花费</span>
          <span class="billing__empty-hint">可尝试调整上方日期范围或清空筛选条件</span>
        </div>
      </div>
    </section>

    <BillingTable
      :tab="tab"
      :tab-counts="tabCounts"
      :color-by="colorBy"
      :groups="groups"
      :total="total"
      :colors="colors"
      :loading="loading"
      :initial-loading="initialLoading"
      :active-filter-count="activeFilterCount"
      :pinned-models="filters.models"
      :pinned-purposes="filters.purposes"
      @update:tab="onTabChange"
      @row-click="onRowClick"
      @hover-series="name => hoveredSeries = name"
      @hover-day="day => hoveredDay = day"
      @reset="resetAllFilters"
    />
  </div>
</template>

<style src="./billing-page.css"></style>
