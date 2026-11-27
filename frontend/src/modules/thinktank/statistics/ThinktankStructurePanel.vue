<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type {
  AssetsSummary,
  DimensionGroup,
  ProposalWinSummary,
  ThinktankStatsLibrary,
} from '@/api/thinktankStats'
import BaseChart from '@/components/charts/BaseChart.vue'
import { useChartPalette } from '@/components/charts/echarts'
import { buildLibraryDonutOption } from './charts'

const props = defineProps<{
  assets: AssetsSummary
  library: ThinktankStatsLibrary
  dimensions: DimensionGroup[]
  proposalWin: ProposalWinSummary | null
  loading: boolean
}>()

const emit = defineEmits<{
  'select-library': [library: ThinktankStatsLibrary]
  drill: [payload: { library: ThinktankStatsLibrary; field: string; value: string }]
}>()

const palette = useChartPalette()
const activeDimKey = ref('')

watch(
  () => props.dimensions,
  (dims) => {
    if (!dims.some(d => d.key === activeDimKey.value)) {
      activeDimKey.value = dims[0]?.key ?? ''
    }
  },
  { immediate: true },
)

const activeDim = computed(() => props.dimensions.find(d => d.key === activeDimKey.value) ?? props.dimensions[0])
const donutOption = computed(() => buildLibraryDonutOption(props.assets.libraries, props.library, palette.value))

const centerLabel = computed(() => {
  if (props.library === 'all') return '三库累计资产'
  return `${props.assets.libraries.find(l => l.key === props.library)?.label ?? ''}资产`
})

const scopeTitle = computed(() => {
  if (props.library === 'all') return '全库 · 核心分类分布'
  const label = props.assets.libraries.find(l => l.key === props.library)?.label ?? ''
  return `${label} · 核心分类分布`
})

const maxItemCount = computed(() => {
  const items = activeDim.value?.items ?? []
  return Math.max(...items.map(i => i.count), 1)
})

const barFillClass = computed(() => {
  if (props.library === 'reports') return 'tt-bar-fill--reports'
  if (props.library === 'proposals') return 'tt-bar-fill--proposals'
  return ''
})

function toggleLibrary(key: 'knowledge' | 'reports' | 'proposals') {
  emit('select-library', props.library === key ? 'all' : key)
}

function onDrill(value: string) {
  if (!activeDim.value?.drill_field || value === '其他合并') return
  emit('drill', { library: props.library, field: activeDim.value.drill_field, value })
}

const fmt = (n: number) => n.toLocaleString('zh-CN')
</script>

<template>
  <section class="tt-grid-4-8">
    <div
      class="tt-panel"
      :class="{ 'is-refreshing': loading }"
    >
      <div class="tt-panel__head">
        <div>
          <h2 class="tt-panel__title">
            三库资产构成
          </h2>
          <p class="tt-panel__sub">
            点击任意子库卡片可一键联动筛选整页指标
          </p>
        </div>
      </div>
      <div class="tt-donut-wrap">
        <BaseChart
          :option="donutOption"
          label="资料库、报告库、方案库资产构成"
          height="186px"
        />
        <div
          class="tt-donut-center"
          aria-hidden="true"
        >
          <strong class="tabular">{{ fmt(assets.total_files) }}</strong>
          <span>{{ centerLabel }}</span>
        </div>
      </div>
      <div class="tt-lib-cards">
        <button
          v-for="lib in assets.libraries"
          :key="lib.key"
          type="button"
          class="tt-lib-card"
          :class="{ 'is-selected': library === lib.key }"
          @click="toggleLibrary(lib.key)"
        >
          <div class="tt-lib-card__top">
            <span class="tt-lib-card__name">
              <span
                class="tt-dot"
                :class="`tt-dot--${lib.key}`"
              />
              {{ lib.label }}
            </span>
            <span class="tabular">
              {{ fmt(lib.files) }} 份
              <small>({{ lib.share_pct.toFixed(1) }}%)</small>
            </span>
          </div>
          <div class="tt-lib-card__meta tabular">
            <span>存储 {{ lib.size_display }}</span>
            <span class="tt-lib-pill">打标率 {{ lib.files ? `${lib.defined_rate.toFixed(1)}%` : '—' }}</span>
          </div>
        </button>
      </div>
    </div>

    <div
      class="tt-panel"
      :class="{ 'is-refreshing': loading }"
    >
      <div class="tt-panel__head">
        <div>
          <h2 class="tt-panel__title">
            {{ scopeTitle }}
          </h2>
          <p class="tt-panel__sub">
            {{ activeDim?.note || '点击任意分类条可下钻跳转对应库并自动带入该筛选条件' }}
          </p>
        </div>
        <div class="tt-dim-tabs">
          <button
            v-for="dim in dimensions"
            :key="dim.key"
            type="button"
            class="tt-dim-tab"
            :class="{ 'is-active': dim.key === activeDim?.key }"
            @click="activeDimKey = dim.key"
          >
            {{ dim.label }}
          </button>
        </div>
      </div>

      <div
        v-if="activeDim?.show_win_banner && proposalWin && proposalWin.total > 0"
        class="tt-win-banner tabular"
      >
        <div class="tt-win-stat">
          <span>累计方案数</span>
          <strong>{{ fmt(proposalWin.total) }} 份</strong>
        </div>
        <div class="tt-win-stat">
          <span>已中标方案</span>
          <strong class="is-good">{{ fmt(proposalWin.won) }} 份</strong>
        </div>
        <div class="tt-win-stat">
          <span>结项中标率</span>
          <strong class="is-primary">{{ proposalWin.win_rate.toFixed(1) }}%</strong>
        </div>
        <div class="tt-win-stat">
          <span>累计中标金额</span>
          <strong class="is-warn">{{ proposalWin.win_amount_wan.toLocaleString('zh-CN') }} 万</strong>
        </div>
      </div>

      <div
        v-if="activeDim && activeDim.items.length > 0"
        class="tt-cat-list"
      >
        <div
          v-for="(item, idx) in activeDim.items"
          :key="item.name"
          class="tt-cat-row"
          role="button"
          tabindex="0"
          @click="onDrill(item.name)"
          @keydown.enter="onDrill(item.name)"
        >
          <div
            class="tt-cat-name"
            :title="item.name"
          >
            <span
              class="tt-cat-rank"
              :class="{ 'is-top': idx < 3 }"
            >{{ idx + 1 }}</span>
            <span class="tt-cat-name__text">{{ item.name }}</span>
          </div>
          <div class="tt-bar-track">
            <div
              class="tt-bar-fill"
              :class="barFillClass"
              :style="{ width: `${(item.count / maxItemCount) * 100}%` }"
            />
          </div>
          <div class="tt-cat-val tabular">
            <strong>{{ fmt(item.count) }}</strong>
            <small>{{ item.share_pct.toFixed(1) }}%</small>
          </div>
        </div>
      </div>

      <div
        v-else
        class="tt-empty"
      >
        <strong>当前视图暂无分类数据</strong>
        <p>该子库尚未入库文件，完成首批文件上传与打标后将自动展示分类分布排行。</p>
      </div>
    </div>
  </section>
</template>

<style scoped src="./thinktank-statistics.css"></style>
