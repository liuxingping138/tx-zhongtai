<script setup lang="ts">
import { computed } from 'vue'

import type { CrawlerConfigReport } from '@/api/crawlerConfig'
import { dayText, deltaText, weekProvinces } from './report'

/** 页面主角：本周各省配置网站数量，和每周给领导汇报的那张表一一对应（省份、数量、总计）。 */
const props = defineProps<{ report: CrawlerConfigReport; weekName: string }>()

const rows = computed(() => weekProvinces(props.report.provinces))
const delta = computed(() => deltaText(props.report.totals.new, props.report.previous_new))
const partial = computed(() => props.report.counted && props.report.report_start > props.report.week_from)
</script>

<template>
  <section
    class="hero"
    aria-labelledby="hero-title"
  >
    <div class="hero__total">
      <h2 id="hero-title">
        {{ weekName }}配置网站数量
      </h2>
      <strong>{{ report.counted ? report.totals.new.toLocaleString() : '—' }}</strong>
      <span class="hero__unit">{{ report.counted ? '个网站' : '不在统计范围' }}</span>
      <span
        v-if="delta"
        class="hero__delta"
        :class="`is-${delta.tone}`"
      >{{ delta.text }}</span>
      <span
        v-if="partial || !report.counted"
        class="hero__note"
      >{{ dayText(report.report_start) }}起统计{{ partial ? '，本周只算这天及以后' : '' }}</span>
    </div>

    <div
      v-if="!rows.length"
      class="hero__empty"
    >
      {{ report.counted ? '这一周还没有新配置的网站。爬虫同事更新规则表后，点「立即同步」就能看到。' : `每周配置数量从 ${dayText(report.report_start)}开始统计，之前配置的都算期初存量。` }}
    </div>
    <ol
      v-else
      class="hero__list"
      :class="{ 'is-wide': rows.length > 12 }"
    >
      <li
        v-for="row in rows"
        :key="row.name"
      >
        <span class="hero__name">{{ row.name }}</span>
        <span
          class="hero__bar"
          aria-hidden="true"
        ><i :style="{ width: `${row.share}%` }" /></span>
        <span class="hero__count">{{ row.count.toLocaleString() }}</span>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.hero {
  display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 28px; padding: 22px 24px;
  border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel);
}
.hero__total { display: flex; flex-direction: column; justify-content: center; gap: 2px; padding-right: 24px; border-right: 1px solid var(--zt-border); }
.hero__total h2 { margin: 0 0 10px; color: var(--zt-ink-900); font-size: 16px; font-weight: 600; }
.hero__total strong { color: var(--chart-normal); font-size: 56px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; }
.hero__unit { color: var(--zt-ink-700); font-size: 14px; }
.hero__delta { margin-top: 12px; font-size: 13px; font-variant-numeric: tabular-nums; color: var(--zt-ink-500); }
.hero__delta.is-good { color: var(--el-color-success); }
.hero__delta.is-bad { color: var(--el-color-danger); }
.hero__note { margin-top: 8px; color: var(--zt-ink-500); font-size: 12px; line-height: 1.5; }
.hero__empty { align-self: center; color: var(--zt-ink-500); font-size: 14px; line-height: 1.7; }
.hero__list { margin: 0; padding: 0; list-style: none; align-self: center; }
.hero__list.is-wide { columns: 2; column-gap: 48px; }
.hero__list li {
  display: grid; grid-template-columns: 96px minmax(0, 1fr) 48px; align-items: center; gap: 12px;
  height: 30px; break-inside: avoid; font-size: 14px; font-variant-numeric: tabular-nums;
}
.hero__name { color: var(--zt-ink-900); text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hero__bar { height: 14px; }
.hero__bar i { display: block; height: 100%; min-width: 3px; border-radius: 0 3px 3px 0; background: var(--chart-normal); }
.hero__count { color: var(--zt-ink-900); font-weight: 600; }
@media (max-width: 900px) {
  .hero { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .hero__total { padding: 0 0 16px; border-right: 0; border-bottom: 1px solid var(--zt-border); }
  .hero__list.is-wide { columns: 1; }
}
</style>
