<script setup lang="ts">
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

import type { CrawlerConfigReport } from '@/api/crawlerConfig'
import { deltaText } from './report'

/** 一句话结论 + 四张卡：这期配置了多少，信源表已爬、未爬、异常各多少。状态卡点了去信源管理看是哪些网站。 */
const props = defineProps<{ report: CrawlerConfigReport; periodName: string; sourcesLink: ((status: string) => RouteLocationRaw) | null }>()

const delta = computed(() => deltaText(props.report.new, props.report.previous_new, props.report.unit))
/** 一句话的各段：数字加粗，涨跌上色。拼成数组而不是写在模板里，中文之间才不会冒出换行带来的空格。 */
const headline = computed(() => {
  const { report: data, periodName: name } = props
  const top = data.provinces[0]
  const parts: { text: string; strong?: boolean; tone?: string }[] = [
    { text: `${name}新配置 ` }, { text: data.new.toLocaleString(), strong: true }, { text: ' 个网站' },
  ]
  if (top) {
    parts.push(
      { text: '，分布在 ' }, { text: String(data.provinces.length), strong: true },
      { text: ` 个省，${top.province_name}最多（${top.new.toLocaleString()} 个）` },
    )
  }
  parts.push(
    { text: `，${delta.value.text}`, tone: delta.value.tone },
    { text: '；信源表共 ' }, { text: data.totals.total.toLocaleString(), strong: true },
    { text: ' 个网站，已爬 ' }, { text: data.totals.online.toLocaleString(), strong: true },
    { text: ' 个，覆盖率 ' }, { text: `${data.totals.coverage}%`, strong: true }, { text: '。' },
  )
  return parts
})
const share = (value: number) => {
  const total = props.report.totals.total
  return total ? `${((value * 100) / total).toFixed(1)}%` : '0%'
}
/** 卡片顺序：总数、已爬、未爬、这期配置、异常。link 为 null 的不跳（未爬含状态为空的，信源管理筛不出空值）。 */
const cards = computed(() => {
  const { totals, previous_new: previous } = props.report
  return [
    { key: 'total', label: '信源总数', link: '', value: totals.total, foot: '信源表全部网站（栏目）', tone: '' },
    { key: 'online', label: '已爬', link: '已爬', value: totals.online, foot: `占总数 ${share(totals.online)}（覆盖率）`, tone: '' },
    { key: 'pending', label: '未爬', link: null, value: totals.pending, foot: `占总数 ${share(totals.pending)}，还没配置爬虫`, tone: '' },
    { key: 'main', label: `${props.periodName}配置`, link: null, value: props.report.new, foot: `${delta.value.text}（${previous.toLocaleString()}）`, tone: delta.value.tone },
    { key: 'abnormal', label: '异常', link: '异常', value: totals.abnormal, foot: `占总数 ${share(totals.abnormal)}，需要业务核对`, tone: '' },
  ]
})
</script>

<template>
  <p
    class="headline"
    aria-live="polite"
  >
    <span
      v-for="(part, index) in headline"
      :key="index"
      :class="[part.strong && 'headline-strong', part.tone && `delta-${part.tone}`]"
    >{{ part.text }}</span>
  </p>
  <div class="cards">
    <component
      :is="sourcesLink && card.link !== null ? 'router-link' : 'div'"
      v-for="card in cards"
      :key="card.key"
      :to="sourcesLink && card.link !== null ? sourcesLink(card.link) : undefined"
      class="card"
      :class="[`card--${card.key}`, { 'card--link': sourcesLink && card.link !== null }]"
      :title="sourcesLink && card.link !== null ? `到信源管理查看${card.key === 'total' ? '全部' : card.label}网站` : undefined"
    >
      <span class="card-label"><span
        v-if="['online', 'pending', 'abnormal'].includes(card.key)"
        class="dot"
      />{{ card.label }}</span>
      <strong class="card-value">{{ card.value.toLocaleString() }}</strong>
      <span
        class="card-foot"
        :class="card.tone && `delta-${card.tone}`"
      >{{ card.foot }}</span>
    </component>
  </div>
</template>

<style scoped>
.headline {
  margin: 0; padding: 10px 16px;
  background: var(--zt-panel); border: 1px solid var(--zt-border); border-left: 3px solid var(--zt-blue-600);
  border-radius: var(--zt-radius); box-shadow: var(--zt-shadow);
  font-size: 13.5px; line-height: 1.8; color: var(--zt-ink-700);
}
.headline-strong { font-size: 15px; font-weight: 650; color: var(--zt-ink-900); font-variant-numeric: tabular-nums; }
.cards { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: var(--zt-space-3); }
.card {
  display: flex; flex-direction: column; gap: 4px; min-height: 104px; padding: 14px 16px;
  background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius);
  box-shadow: var(--zt-shadow); color: inherit; text-decoration: none;
}
.card--link { transition: background-color 160ms ease, border-color 160ms ease, box-shadow 160ms ease; }
.card--link:hover { border-color: var(--zt-border-strong); box-shadow: 0 4px 12px var(--zt-shadow-soft); }
.card--link:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.card-label { display: flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 500; color: var(--zt-ink-500); }
.card-value { margin: 2px 0; font-size: 26px; font-weight: 650; letter-spacing: -0.02em; line-height: 1.15; color: var(--zt-ink-900); font-variant-numeric: tabular-nums; }
.card--main .card-value { color: var(--zt-blue-600); }
.card-foot { font-size: 12px; color: var(--zt-ink-500); font-variant-numeric: tabular-nums; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.card--online .dot { background: var(--zt-blue-600); }
.card--pending .dot { background: var(--zt-blue-600); opacity: 0.25; }
.card--abnormal .dot { background: var(--chart-stale); }
.delta-good { color: var(--zt-success-text); }
.delta-bad { color: var(--zt-danger-text); }
.delta-flat { color: var(--zt-ink-500); }

@media (max-width: 1280px) {
  .cards { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 767px) {
  .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
