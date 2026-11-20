<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getAiBilling, type BillingRow } from '@/api/aiBilling'
import { errorMessage } from '@/api/errors'
import BaseChart from '@/components/charts/BaseChart.vue'
import { useChartPalette } from '@/components/charts/echarts'
import CardSkeleton from '@/components/CardSkeleton.vue'
import ChartSkeleton from '@/components/ChartSkeleton.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { useTheme } from '@/composables/useTheme'
import {
  colorMap, dailySeries, filterOptions, filterRows, groupBy,
  cachedText, money, presetRange, pruneInPlace, SCENES, summarize, tokens, totalCards,
  type BillingFilters, type GroupKey, type RangePreset,
} from './billing'
import { costOption } from './billingChart'
import '../shared/ai.css'

/** 所有模型调用的花费：批量任务、定时打标、样本试跑、试发，以及已下线的多轮对话留下的记录。改日期重新取数，
 * 业务分类 → 一级业务板块 → 二级业务板块三级联动、模型独立，都在页面上直接筛，卡片、图表和明细跟着变。 */
const route = useRoute()
const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const PRESETS: { value: RangePreset; label: string }[] = [
  { value: '7', label: '近 7 天' },
  { value: '30', label: '近 30 天' },
  { value: '90', label: '近 90 天' },
  { value: 'month', label: '本月' },
]
const TABS: { value: GroupKey; label: string }[] = [
  { value: 'model', label: '按模型' },
  { value: 'purpose', label: '按二级业务板块' },
  { value: 'day', label: '按日期' },
]
const preset = ref<RangePreset | ''>('30')
const range = ref<[string, string]>(presetRange('30', today))
const rows = ref<BillingRow[]>([])
const loading = ref(false)
const error = ref('')
// 从任务调度「查看账单」跳过来时带着用途（二级业务板块），进来就筛好。
const filters = reactive<BillingFilters>({
  scenes: [],
  categories: [],
  purposes: [route.query.purpose].flat().filter((item): item is string => typeof item === 'string' && !!item),
  models: [],
})
const colorBy = ref<'model' | 'purpose'>('model')
const tab = ref<GroupKey>('model')
const palette = useChartPalette()
const { isDark } = useTheme()

const options = computed(() => filterOptions(rows.value, filters))
const shown = computed(() => filterRows(rows.value, filters))
const total = computed(() => summarize(shown.value))
const colors = computed(() => colorMap(rows.value, colorBy.value, isDark.value))
const chart = computed(() => dailySeries(shown.value, range.value[0], range.value[1], colorBy.value, colors.value, isDark.value))
const option = computed(() => costOption(chart.value.days, chart.value.series, palette.value))
const chartLabel = computed(() =>
  `每日费用：${range.value[0]} 至 ${range.value[1]} 合计 ${money(total.value.cost)}。${groupBy(shown.value, colorBy.value)
    .slice(0, 5).map(group => `${group.name} ${money(group.cost)}`).join('；')}`,
)
const groups = computed(() => groupBy(shown.value, tab.value))
const nameLabel = computed(() => TABS.find(item => item.value === tab.value)?.label.slice(1) ?? '')

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

watch(() => [filters.scenes, filters.categories], pruneBelow)
watch(range, () => void load())
onMounted(load)
</script>

<template>
  <div class="billing">
    <h1 class="ai-sr-only">
      费用账单
    </h1>
    <section
      class="billing__bar"
      aria-label="账单范围"
    >
      <el-radio-group
        :model-value="preset"
        class="ai-seg"
        aria-label="快捷范围"
        @update:model-value="pickPreset"
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
        :disabled-date="(day: Date) => day.getTime() > Date.now()"
        aria-label="日期范围"
        style="width: 260px; flex: none"
        @update:model-value="pickRange"
      />
      <el-select
        v-model="filters.scenes"
        multiple
        collapse-tags
        collapse-tags-tooltip
        clearable
        placeholder="全部业务分类"
        aria-label="业务分类"
        class="billing__filter"
      >
        <el-option
          v-for="item in SCENES"
          :key="item"
          :label="item"
          :value="item"
        />
      </el-select>
      <el-select
        v-model="filters.categories"
        multiple
        collapse-tags
        collapse-tags-tooltip
        clearable
        placeholder="全部一级业务板块"
        aria-label="一级业务板块"
        class="billing__filter"
      >
        <el-option
          v-for="item in options.categories"
          :key="item"
          :label="item"
          :value="item"
        />
      </el-select>
      <el-select
        v-model="filters.purposes"
        multiple
        collapse-tags
        collapse-tags-tooltip
        clearable
        placeholder="全部二级业务板块"
        aria-label="二级业务板块"
        class="billing__filter"
      >
        <el-option
          v-for="item in options.purposes"
          :key="item"
          :label="item"
          :value="item"
        />
      </el-select>
      <el-select
        v-model="filters.models"
        multiple
        collapse-tags
        collapse-tags-tooltip
        clearable
        placeholder="全部模型"
        aria-label="模型"
        class="billing__filter"
      >
        <el-option
          v-for="item in options.models"
          :key="item"
          :label="item"
          :value="item"
        />
      </el-select>
    </section>
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
      v-if="loading && rows.length === 0"
      :count="5"
      :columns="5"
      variant="kpi"
    />
    <section
      v-else
      class="billing__totals"
      aria-label="合计"
    >
      <div
        v-for="card in totalCards(total)"
        :key="card.label"
        :class="{ billing__total: card.main }"
      >
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
        <small>{{ card.note }}</small>
      </div>
    </section>
    <section
      class="billing__panel"
      :class="{ 'is-refreshing': loading && rows.length > 0 }"
    >
      <header class="billing__head">
        <div>
          <h2>每日费用</h2>
          <p>{{ range[0] }} 至 {{ range[1] }}，北京时间。批量任务的费用算在发起那天，悬停看每天的明细</p>
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
      <ChartSkeleton
        v-if="loading && rows.length === 0"
        height="320px"
        :bars="9"
      />
      <BaseChart
        v-else-if="shown.length"
        :option="option"
        :label="chartLabel"
        height="320px"
      />
      <p
        v-else
        class="billing__empty"
      >
        这段时间没有花费
      </p>
    </section>
    <section class="billing__panel">
      <el-tabs v-model="tab">
        <el-tab-pane
          v-for="item in TABS"
          :key="item.value"
          :label="item.label"
          :name="item.value"
        />
      </el-tabs>
      <TableSkeleton
        v-if="loading && rows.length === 0"
        :columns="7"
      />
      <el-table
        v-else
        :data="groups"
        class="data-table"
        :class="{ 'is-refreshing': loading }"
        row-key="name"
        empty-text="这段时间没有花费"
      >
        <el-table-column
          :label="nameLabel"
          min-width="220"
        >
          <template #default="{ row }">
            <span class="billing__name">
              <i
                v-if="tab !== 'day' && tab === colorBy"
                class="billing__swatch"
                :style="{ background: colors.get(row.name) }"
              />{{ row.name }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          label="次数"
          width="100"
          align="right"
        >
          <template #default="{ row }">
            {{ row.calls.toLocaleString('zh-CN') }}
          </template>
        </el-table-column>
        <el-table-column
          label="输入 token"
          width="130"
          align="right"
        >
          <template #default="{ row }">
            {{ tokens(row.input_tokens) }}
          </template>
        </el-table-column>
        <el-table-column
          label="缓存命中"
          width="150"
          align="right"
        >
          <template #default="{ row }">
            {{ cachedText(row) }}
          </template>
        </el-table-column>
        <el-table-column
          label="输出 token"
          width="130"
          align="right"
        >
          <template #default="{ row }">
            {{ tokens(row.output_tokens) }}
          </template>
        </el-table-column>
        <el-table-column
          label="费用"
          width="130"
          align="right"
        >
          <template #default="{ row }">
            {{ money(row.cost) }}
          </template>
        </el-table-column>
        <el-table-column
          label="占比"
          min-width="190"
        >
          <template #default="{ row }">
            <span class="billing__share">
              <span class="billing__share-track">
                <span
                  class="billing__share-bar"
                  :style="{
                    width: `${Math.max(row.share * 100, row.cost ? 2 : 0)}%`,
                    background: tab !== 'day' && tab === colorBy ? colors.get(row.name) : undefined,
                  }"
                />
              </span>
              <span>{{ (row.share * 100).toFixed(1) }}%</span>
            </span>
          </template>
        </el-table-column>
      </el-table>
      <p class="billing__foot">
        次数：批量任务、定时任务和样本试跑一个任务算一次（一个任务里有很多行），试发每问一次算一次（已下线的多轮对话也是），从 2026-10-22 起记账，之前的没有记录。
      </p>
    </section>
  </div>
</template>

<style scoped src="./billing-page.css"></style>
