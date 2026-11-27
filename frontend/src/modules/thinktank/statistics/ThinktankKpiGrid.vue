<script setup lang="ts">
import { computed } from 'vue'

import type { AssetsSummary, BehaviorSummary, ThinktankStatsLibrary } from '@/api/thinktankStats'
import { formatDelta } from './charts'

const props = defineProps<{
  assets: AssetsSummary
  behavior: BehaviorSummary
  library: ThinktankStatsLibrary
  windowLabel: string
  windowDays: number
}>()

defineEmits<{
  'go-undefined': []
}>()

const LIB_LABELS: Record<ThinktankStatsLibrary, string> = {
  all: '三库合计',
  knowledge: '资料库',
  reports: '报告库',
  proposals: '方案库',
}

const totalAll = computed(() => props.assets.libraries.reduce((s, item) => s + item.files, 0) || 1)
const shareOf = (key: 'knowledge' | 'reports' | 'proposals') => {
  const item = props.assets.libraries.find(x => x.key === key)
  return item ? (item.files * 100) / totalAll.value : 0
}

const uploadDelta = computed(() => formatDelta(props.behavior.uploads_delta_pct))
const previewDelta = computed(() => formatDelta(props.behavior.previews_delta_pct))
const activeDelta = computed(() => formatDelta(props.behavior.active_users_delta_pct))

const dailyAvgUploads = computed(() => {
  const days = props.windowDays > 0 ? props.windowDays : 30
  return (props.behavior.uploads / days).toFixed(1)
})

const dlRatio = computed(() => {
  if (!props.behavior.previews) return '0.0%'
  return `${((props.behavior.downloads * 100) / props.behavior.previews).toFixed(1)}%`
})

const perUserViews = computed(() => {
  if (!props.behavior.active_users) return '0.0'
  return (props.behavior.previews / props.behavior.active_users).toFixed(1)
})

const fmt = (n: number) => n.toLocaleString('zh-CN')
</script>

<template>
  <section
    class="tt-kpi-grid"
    aria-label="核心统计指标"
  >
    <article class="tt-kpi tt-kpi--hero">
      <div class="tt-kpi__head">
        <span class="tt-kpi__label">累计资产总量</span>
        <span class="tt-delta tt-delta--flat">{{ LIB_LABELS[library] }}</span>
      </div>
      <div class="tt-kpi__val-row">
        <span class="tt-kpi__val tt-kpi__val--primary tabular">{{ fmt(assets.total_files) }}</span>
        <span class="tt-kpi__unit">份</span>
      </div>
      <div
        class="tt-mini-stack"
        title="资料库 / 报告库 / 方案库占比"
      >
        <span
          class="tt-mini-stack__k"
          :style="{ width: `${shareOf('knowledge')}%` }"
        />
        <span
          class="tt-mini-stack__r"
          :style="{ width: `${shareOf('reports')}%` }"
        />
        <span
          class="tt-mini-stack__p"
          :style="{ width: `${shareOf('proposals')}%` }"
        />
      </div>
      <div class="tt-kpi__foot tabular">
        <span>占用存储 <strong>{{ assets.total_size_display }}</strong></span>
        <span>3 个子库</span>
      </div>
    </article>

    <article class="tt-kpi">
      <div class="tt-kpi__head">
        <span class="tt-kpi__label">标签治理完善率</span>
        <span
          class="tt-delta tabular"
          :class="assets.undefined_files > 0 ? 'tt-delta--down' : 'tt-delta--up'"
        >
          {{ assets.undefined_files > 0 ? `待补 ${fmt(assets.undefined_files)} 份` : '全量达标' }}
        </span>
      </div>
      <div class="tt-kpi__val-row">
        <span class="tt-kpi__val tabular">{{ assets.total_files ? `${assets.defined_rate.toFixed(1)}%` : '—' }}</span>
      </div>
      <div class="tt-prog-track">
        <div
          class="tt-prog-fill"
          :style="{ width: `${assets.defined_rate}%` }"
        />
      </div>
      <div class="tt-kpi__foot tabular">
        <span>已定义 {{ fmt(assets.defined_files) }} 份</span>
        <button
          v-if="assets.undefined_files > 0"
          type="button"
          class="tt-kpi__link"
          @click="$emit('go-undefined')"
        >
          去治理 →
        </button>
        <span v-else>治理健康</span>
      </div>
    </article>

    <article class="tt-kpi">
      <div class="tt-kpi__head">
        <span class="tt-kpi__label">{{ windowLabel }}新增入库</span>
        <span
          class="tt-delta tabular"
          :class="`tt-delta--${uploadDelta.tone}`"
        >
          {{ uploadDelta.text }}
        </span>
      </div>
      <div class="tt-kpi__val-row">
        <span class="tt-kpi__val tabular">{{ fmt(behavior.uploads) }}</span>
        <span class="tt-kpi__unit">份</span>
      </div>
      <div class="tt-kpi__foot tabular">
        <span>打标/编辑 {{ fmt(behavior.governance) }} 次</span>
        <span v-if="windowDays > 0">日均 {{ dailyAvgUploads }} 份</span>
      </div>
    </article>

    <article class="tt-kpi">
      <div class="tt-kpi__head">
        <span class="tt-kpi__label">{{ windowLabel }}知识消费</span>
        <span
          class="tt-delta tabular"
          :class="`tt-delta--${previewDelta.tone}`"
        >
          {{ previewDelta.text }}
        </span>
      </div>
      <div class="tt-kpi__val-row">
        <span class="tt-kpi__val tabular">{{ fmt(behavior.previews) }}</span>
        <span class="tt-kpi__unit">次预览</span>
      </div>
      <div class="tt-kpi__foot tabular">
        <span>下载 <strong>{{ fmt(behavior.downloads) }}</strong> · 收藏 +{{ fmt(behavior.favorites_added) }}</span>
        <span>转化 {{ dlRatio }}</span>
      </div>
    </article>

    <article class="tt-kpi">
      <div class="tt-kpi__head">
        <span class="tt-kpi__label">{{ windowLabel }}活跃人数</span>
        <span
          class="tt-delta tabular"
          :class="`tt-delta--${activeDelta.tone}`"
        >
          {{ activeDelta.text }}
        </span>
      </div>
      <div class="tt-kpi__val-row">
        <span class="tt-kpi__val tabular">{{ fmt(behavior.active_users) }}</span>
        <span class="tt-kpi__unit">人</span>
      </div>
      <div class="tt-kpi__foot tabular">
        <span>人均预览 {{ perUserViews }} 次</span>
        <span>去重参与成员</span>
      </div>
    </article>
  </section>
</template>

<style scoped src="./thinktank-statistics.css"></style>
