<script setup lang="ts">
import { CircleCheck, Clock, Collection, TrendCharts, Warning } from '@element-plus/icons-vue'
import { computed } from 'vue'

import type { CrawlerConfigReport } from '@/api/crawlerConfig'
import { deltaText } from './report'

/** 总览：所选这周配置了多少，以及到今天为止的整体配置情况，一条五格。 */
const props = defineProps<{
  report: CrawlerConfigReport
  weekName: string
  abnormalLink: { path: string; query: Record<string, string> } | null
}>()

const delta = computed(() => deltaText(props.report.totals.new, props.report.previous_new))
</script>

<template>
  <section
    class="overview"
    aria-label="总览"
  >
    <div class="cell cell--week">
      <span class="cell__icon"><el-icon><TrendCharts /></el-icon></span>
      <div class="cell__body">
        <span class="cell__label">{{ weekName }}配置</span>
        <strong class="cell__value">{{ report.totals.new.toLocaleString() }}<small>个网站</small></strong>
        <span
          class="cell__foot"
          :class="`is-${delta.tone}`"
        >{{ delta.text }}（上周 {{ report.previous_new.toLocaleString() }}）</span>
      </div>
    </div>
    <div class="cell cell--online">
      <span class="cell__icon"><el-icon><CircleCheck /></el-icon></span>
      <div class="cell__body">
        <span class="cell__label">已配置</span>
        <strong class="cell__value">{{ report.totals.online.toLocaleString() }}</strong>
        <span class="cell__foot cell__coverage">
          <i
            class="cell__meter"
            aria-hidden="true"
          ><b :style="{ width: `${report.totals.coverage}%` }" /></i>
          覆盖率 {{ report.totals.coverage }}%
        </span>
      </div>
    </div>
    <div class="cell cell--pending">
      <span class="cell__icon"><el-icon><Clock /></el-icon></span>
      <div class="cell__body">
        <span class="cell__label">未配置</span>
        <strong class="cell__value">{{ report.totals.pending.toLocaleString() }}</strong>
        <span class="cell__foot">信源表里还没爬的网站</span>
      </div>
    </div>
    <div class="cell cell--abnormal">
      <span class="cell__icon"><el-icon><Warning /></el-icon></span>
      <div class="cell__body">
        <span class="cell__label">异常</span>
        <strong class="cell__value">{{ report.totals.abnormal.toLocaleString() }}</strong>
        <router-link
          v-if="abnormalLink && report.totals.abnormal"
          :to="abnormalLink"
          class="cell__foot cell__link"
        >
          去信源管理核对
        </router-link>
        <span
          v-else
          class="cell__foot"
        >需要业务核对的网站</span>
      </div>
    </div>
    <div class="cell cell--total">
      <span class="cell__icon"><el-icon><Collection /></el-icon></span>
      <div class="cell__body">
        <span class="cell__label">信源网站</span>
        <strong class="cell__value">{{ report.totals.total.toLocaleString() }}</strong>
        <span
          class="cell__foot"
          :title="`${report.backfill_date} 统一补录上线时间、规则表里也查不到配置日期的 ${report.baseline.toLocaleString()} 个已配置网站，不计入任何一周`"
        >含历史补录 {{ report.baseline.toLocaleString() }} 个</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.overview {
  display: grid; grid-template-columns: minmax(0, 1.3fr) repeat(4, minmax(0, 1fr));
  border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel);
}
.cell { display: flex; gap: 12px; align-items: flex-start; padding: 18px 20px; min-width: 0; --tone: var(--zt-blue-600); }
.cell + .cell { border-left: 1px solid var(--zt-border); }
.cell--week { --tone: var(--chart-normal); }
.cell--pending { --tone: var(--zt-ink-500); }
.cell--abnormal { --tone: var(--chart-stale); }
.cell--total { --tone: var(--zt-ink-700); }
.cell__icon {
  display: grid; place-items: center; flex: none; width: 36px; height: 36px; border-radius: 9px;
  font-size: 18px; color: var(--tone); background: color-mix(in srgb, var(--tone) 12%, transparent);
}
.cell__body { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.cell__label { color: var(--zt-ink-700); font-size: 13px; }
.cell__value { color: var(--zt-ink-900); font-size: 26px; font-weight: 600; line-height: 1.15; font-variant-numeric: tabular-nums; }
.cell__value small { margin-left: 4px; color: var(--zt-ink-500); font-size: 13px; font-weight: 400; }
.cell--week .cell__value { color: var(--tone); font-size: 34px; }
.cell--abnormal .cell__value { color: var(--tone); }
.cell__foot { color: var(--zt-ink-500); font-size: 12px; line-height: 1.5; font-variant-numeric: tabular-nums; }
.cell__foot.is-good { color: var(--el-color-success); }
.cell__foot.is-bad { color: var(--el-color-danger); }
.cell__coverage { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.cell__meter { display: block; flex: none; width: 48px; height: 6px; border-radius: 3px; overflow: hidden; background: var(--zt-border); }
.cell__meter b { display: block; height: 100%; background: var(--zt-blue-600); }
.cell__link { color: var(--zt-blue-600); text-decoration: none; }
.cell__link:hover { text-decoration: underline; }
@media (max-width: 1200px) {
  .overview { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .cell--week { grid-column: 1 / -1; }
  .cell + .cell { border-left: 0; }
  .cell:not(.cell--week) { border-top: 1px solid var(--zt-border); }
  .cell:nth-child(3), .cell:nth-child(4), .cell:nth-child(5) { border-left: 1px solid var(--zt-border); }
}
@media (max-width: 640px) {
  .overview { grid-template-columns: minmax(0, 1fr); }
  .cell:nth-child(n) { border-left: 0; }
}
</style>
