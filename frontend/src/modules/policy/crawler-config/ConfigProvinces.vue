<script setup lang="ts">
import { MapLocation } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'

import type { CrawlerConfigReport } from '@/api/crawlerConfig'
import ConfigProvinceWeekly from './ConfigProvinceWeekly.vue'
import { provinceBars, type ProvinceSort } from './report'

/** 分省：配置进度（覆盖率进度条，本周有新增挂绿色「+N」）、每周配置数（省 × 周）、表格三种看法。 */
const props = defineProps<{ report: CrawlerConfigReport; current: boolean }>()

const sort = ref<ProvinceSort>('total')
const view = ref<'bars' | 'weekly' | 'table'>('bars')
const bars = computed(() => provinceBars(props.report.provinces, sort.value))
const tableRows = computed(() => [...bars.value.map(bar => bar.item), { ...props.report.totals, province_name: '合计' }])

function totalRow({ rowIndex }: { rowIndex: number }): string {
  return rowIndex === props.report.provinces.length ? 'is-total' : ''
}
</script>

<template>
  <section class="provinces">
    <header class="provinces__head">
      <div class="provinces__title">
        <el-icon aria-hidden="true">
          <MapLocation />
        </el-icon>
        <div>
          <h2>分省配置情况</h2>
          <p v-if="view === 'weekly'">
            每个省每周新配置上线的栏目数，绿色越深配得越多
          </p>
          <p v-else>
            进度条是已配置占该省栏目的比例，红色是异常；绿色数字是本周新配置
          </p>
        </div>
      </div>
      <div class="provinces__switches">
        <el-radio-group
          v-model="sort"
          size="small"
          aria-label="排序"
        >
          <el-radio-button value="total">
            按栏目数
          </el-radio-button>
          <el-radio-button value="new">
            本周新增多的在前
          </el-radio-button>
          <el-radio-button value="coverage">
            覆盖率低的在前
          </el-radio-button>
        </el-radio-group>
        <el-radio-group
          v-model="view"
          size="small"
          aria-label="展示方式"
        >
          <el-radio-button value="bars">
            配置进度
          </el-radio-button>
          <el-radio-button value="weekly">
            每周配置数
          </el-radio-button>
          <el-radio-button value="table">
            表格
          </el-radio-button>
        </el-radio-group>
      </div>
    </header>

    <ul
      v-if="view === 'bars'"
      class="provinces__list"
    >
      <li
        v-for="bar in bars"
        :key="bar.item.province_name"
        class="province"
        :title="bar.hint"
      >
        <span class="province__name">{{ bar.item.province_name }}</span>
        <span
          class="province__track"
          role="img"
          :aria-label="bar.hint"
        >
          <span
            class="province__fill"
            :style="{ width: `${bar.online}%` }"
          />
          <span
            class="province__abnormal"
            :style="{ width: `${bar.abnormal}%` }"
          />
        </span>
        <span class="province__count">{{ bar.item.online.toLocaleString() }}<small> / {{ bar.item.total.toLocaleString() }}</small></span>
        <span class="province__rate">{{ bar.item.coverage }}%</span>
        <span
          class="province__new"
          :class="{ 'is-zero': !bar.item.new }"
        >{{ bar.item.new ? `+${bar.item.new}` : '—' }}</span>
      </li>
    </ul>

    <ConfigProvinceWeekly
      v-else-if="view === 'weekly'"
      :rows="bars.map(bar => bar.item)"
      :weeks="report.trend"
      :report-start="report.report_start"
      :current="current"
    />
    <el-table
      v-else
      :data="tableRows"
      :row-class-name="totalRow"
    >
      <el-table-column
        prop="province_name"
        label="省份"
        min-width="130"
      />
      <el-table-column
        prop="total"
        label="栏目总数"
        width="100"
        align="right"
      />
      <el-table-column
        prop="online"
        label="已爬"
        width="90"
        align="right"
      />
      <el-table-column
        prop="pending"
        label="未爬"
        width="90"
        align="right"
      />
      <el-table-column
        prop="abnormal"
        label="异常"
        width="90"
        align="right"
      />
      <el-table-column
        prop="new"
        label="本周新增"
        width="100"
        align="right"
      />
      <el-table-column
        label="覆盖率"
        width="100"
        align="right"
      >
        <template #default="{ row }">
          {{ row.coverage }}%
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<style scoped>
.provinces { padding: 16px 20px 18px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); min-width: 0; }
.provinces__head { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 14px; }
.provinces__title { display: flex; gap: 10px; align-items: flex-start; }
.provinces__title > .el-icon { margin-top: 2px; font-size: 18px; color: var(--zt-blue-600); }
.provinces__title h2 { margin: 0; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; }
.provinces__title p { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 12px; }
.provinces__switches { display: flex; flex-wrap: wrap; gap: 8px; }
.provinces__list {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 40px;
  margin: 0; padding: 0; list-style: none;
}
.province {
  display: grid; grid-template-columns: 84px minmax(80px, 1fr) 104px 52px 44px; align-items: center; gap: 12px;
  padding: 7px 0; border-bottom: 1px solid var(--zt-border);
  font-size: 13px; color: var(--zt-ink-700); font-variant-numeric: tabular-nums;
}
.province__name { color: var(--zt-ink-900); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.province__track { display: flex; height: 10px; border-radius: 5px; overflow: hidden; background: var(--zt-border); }
.province__fill { background: var(--zt-blue-600); }
.province__abnormal { background: var(--chart-stale); }
.province__count { text-align: right; color: var(--zt-ink-900); }
.province__count small { font-size: 12px; color: var(--zt-ink-500); }
.province__rate { text-align: right; font-weight: 600; color: var(--zt-ink-900); }
.province__new { justify-self: end; min-width: 36px; padding: 1px 6px; border-radius: 4px; text-align: center; font-size: 12px; font-weight: 600; color: var(--chart-normal); background: color-mix(in srgb, var(--chart-normal) 12%, transparent); }
.province__new.is-zero { font-weight: 400; color: var(--zt-ink-500); background: none; }
.provinces :deep(.el-table .cell) { font-variant-numeric: tabular-nums; }
.provinces :deep(.el-table .is-total td) { font-weight: 600; background: var(--zt-soft); }
@media (max-width: 1280px) {
  .provinces__list { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 560px) {
  .province { grid-template-columns: 64px minmax(60px, 1fr) 52px 40px; }
  .province__count { display: none; }
}
</style>
