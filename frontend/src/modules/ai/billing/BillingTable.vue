<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import TableSkeleton from '@/components/TableSkeleton.vue'
import { cacheHitText } from '../shared/aiText'
import {
  isFallbackColor, money, OTHER, sortGroups, tokens,
  type BillingGroup, type GroupKey, type SortKey, type SortOrder,
} from './billing'

const props = defineProps<{
  tab: GroupKey
  tabCounts: Record<GroupKey, number>
  colorBy: 'model' | 'purpose'
  groups: BillingGroup[]
  total: Omit<BillingGroup, 'name' | 'share'>
  colors: Map<string, string>
  loading: boolean
  initialLoading: boolean
  activeFilterCount: number
  pinnedModels: string[]
  pinnedPurposes: string[]
}>()

const emit = defineEmits<{
  'update:tab': [value: GroupKey]
  'row-click': [name: string]
  'hover-series': [seriesName: string | null]
  'hover-day': [day: string | null]
  reset: []
}>()

const TABS: { value: GroupKey; label: string }[] = [
  { value: 'model', label: '按模型' },
  { value: 'purpose', label: '按二级业务板块' },
  { value: 'day', label: '按日期' },
]

const SORTABLE_COLS: { key: SortKey; label: string }[] = [
  { key: 'calls', label: '次数' },
  { key: 'input_tokens', label: '输入 token' },
  { key: 'cached_rate', label: '缓存命中' },
  { key: 'output_tokens', label: '输出 token' },
  { key: 'cost', label: '费用' },
]

const sortKey = ref<SortKey>('cost')
const sortOrder = ref<SortOrder>('desc')

watch(() => props.tab, next => {
  sortKey.value = next === 'day' ? 'name' : 'cost'
  sortOrder.value = 'desc'
})

const sortedGroups = computed(() => sortGroups(props.groups, sortKey.value, sortOrder.value))
const nameLabel = computed(() => TABS.find(item => item.value === props.tab)?.label.slice(1) ?? '')
const showSwatch = computed(() => props.tab !== 'day' && props.tab === props.colorBy)
const totalHit = computed(() => cacheHitText(props.total.input_tokens, props.total.cached_tokens))

function toggleSort(key: SortKey): void {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortKey.value = key
    sortOrder.value = 'desc'
  }
}

function isPinned(name: string): boolean {
  if (props.tab === 'model') return props.pinnedModels.length === 1 && props.pinnedModels[0] === name
  if (props.tab === 'purpose') return props.pinnedPurposes.length === 1 && props.pinnedPurposes[0] === name
  return false
}

function hoverSeries(name: string): string | null {
  if (!showSwatch.value) return null
  return isFallbackColor(props.colors.get(name)) ? OTHER : name
}
function onRowEnter(name: string): void {
  if (props.tab === 'day') {
    emit('hover-day', name)
  } else {
    emit('hover-series', hoverSeries(name))
  }
}

function onRowLeave(): void {
  emit('hover-series', null)
  emit('hover-day', null)
}

function onRowActivate(name: string): void {
  if (props.tab === 'day') {
    emit('hover-day', name)
  } else {
    emit('row-click', name)
  }
}
</script>

<template>
  <section
    class="billing__panel"
    aria-label="费用分组明细"
  >
    <header class="billing__panel-head billing__panel-head--bordered">
      <div
        class="billing__tabs"
        role="tablist"
        aria-label="明细分组维度"
      >
        <button
          v-for="item in TABS"
          :key="item.value"
          type="button"
          role="tab"
          :aria-selected="tab === item.value"
          class="billing__tab"
          :class="{ 'is-active': tab === item.value }"
          @click="emit('update:tab', item.value)"
        >
          <span>{{ item.label }}</span>
          <span class="billing__tab-count">{{ tabCounts[item.value] }}</span>
        </button>
      </div>
      <span class="billing__table-hint">
        {{ tab !== 'day' ? '悬停行联动高亮上方图表 · 点击行快速聚焦筛选' : `共 ${groups.length} 个活跃记账日 · 悬停行联动定位上方趋势图` }}
      </span>
    </header>

    <TableSkeleton
      v-if="initialLoading"
      :columns="7"
    />
    <div
      v-else-if="groups.length === 0"
      class="billing__empty"
    >
      <span>这段时间没有花费</span>
      <el-button
        v-if="activeFilterCount > 0"
        size="small"
        plain
        @click="emit('reset')"
      >
        重置筛选条件
      </el-button>
    </div>
    <div
      v-else
      class="billing__table-wrap"
      :class="{ 'is-refreshing': loading }"
    >
      <table class="billing__table">
        <colgroup>
          <col class="billing__col-name">
          <col class="billing__col-calls">
          <col class="billing__col-input">
          <col class="billing__col-cached">
          <col class="billing__col-output">
          <col class="billing__col-cost">
          <col class="billing__col-share">
        </colgroup>
        <thead>
          <tr>
            <th scope="col">
              <button
                type="button"
                class="billing__sort-btn billing__sort-btn--left"
                :class="{ 'is-sorted': sortKey === 'name' }"
                @click="toggleSort('name')"
              >
                <span>{{ nameLabel }}</span>
                <span
                  class="billing__sort-arrow"
                  aria-hidden="true"
                >{{ sortKey === 'name' ? (sortOrder === 'asc' ? '↑' : '↓') : '↕' }}</span>
              </button>
            </th>
            <th
              v-for="col in SORTABLE_COLS"
              :key="col.key"
              scope="col"
            >
              <button
                type="button"
                class="billing__sort-btn"
                :class="{ 'is-sorted': sortKey === col.key }"
                @click="toggleSort(col.key)"
              >
                <span>{{ col.label }}</span>
                <span
                  class="billing__sort-arrow"
                  aria-hidden="true"
                >{{ sortKey === col.key ? (sortOrder === 'asc' ? '↑' : '↓') : '↕' }}</span>
              </button>
            </th>
            <th scope="col">
              占比
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in sortedGroups"
            :key="row.name"
            class="billing__row billing__row--interactive"
            :class="{ 'is-pinned': isPinned(row.name) }"
            @click="onRowActivate(row.name)"
            @mouseenter="onRowEnter(row.name)"
            @mouseleave="onRowLeave()"
          >
            <td>
              <span class="billing__name-cell">
                <i
                  v-if="showSwatch"
                  class="billing__swatch"
                  :style="{ background: colors.get(row.name) }"
                  aria-hidden="true"
                />
                <span
                  class="billing__name-text"
                  :title="row.name"
                >{{ row.name }}</span>
                <span
                  v-if="isPinned(row.name)"
                  class="billing__pin-tag"
                >已筛选</span>
              </span>
            </td>
            <td>{{ row.calls.toLocaleString('zh-CN') }}</td>
            <td>{{ tokens(row.input_tokens) }}</td>
            <td>
              <span class="billing__cached-cell">
                <span class="billing__cached-val">{{ tokens(row.cached_tokens) }}</span>
                <span
                  class="billing__cached-rate"
                  :class="{ 'billing__cached-rate--zero': !cacheHitText(row.input_tokens, row.cached_tokens) }"
                >{{ cacheHitText(row.input_tokens, row.cached_tokens) || '0.0%' }}</span>
              </span>
            </td>
            <td>{{ tokens(row.output_tokens) }}</td>
            <td>
              <span class="billing__cost-val">{{ money(row.cost) }}</span>
            </td>
            <td>
              <span class="billing__share-cell">
                <span
                  class="billing__share-track"
                  aria-hidden="true"
                >
                  <span
                    class="billing__share-bar"
                    :style="{
                      width: `${Math.max(row.share * 100, row.cost > 0 ? 2 : 0)}%`,
                      background: showSwatch ? colors.get(row.name) : undefined,
                    }"
                  />
                </span>
                <span class="billing__share-pct">{{ (row.share * 100).toFixed(1) }}%</span>
              </span>
            </td>
          </tr>
          <tr class="billing__summary-row">
            <td>合计（{{ groups.length }} 项）</td>
            <td>{{ total.calls.toLocaleString('zh-CN') }}</td>
            <td>{{ tokens(total.input_tokens) }}</td>
            <td>
              <span class="billing__cached-cell">
                <span class="billing__cached-val">{{ tokens(total.cached_tokens) }}</span>
                <span
                  class="billing__cached-rate"
                  :class="{ 'billing__cached-rate--zero': !totalHit }"
                >{{ totalHit || '0.0%' }}</span>
              </span>
            </td>
            <td>{{ tokens(total.output_tokens) }}</td>
            <td>{{ money(total.cost) }}</td>
            <td>
              <span class="billing__share-cell">
                <span class="billing__share-pct">100.0%</span>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer class="billing__foot">
      <span>次数：批量任务、定时任务和样本试跑一个任务算一次（内含多行），试发与已下线多轮对话每问一次算一次。</span>
      <span>记账起点：2026-10-22 起记账，之前没有记录</span>
    </footer>
  </section>
</template>
