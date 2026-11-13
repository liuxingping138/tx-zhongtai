<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'

import {
  CRAWLER_CONFIG_BASE,
  getCrawlerConfigReport,
  type ConfigUnit,
  type CrawlerConfigReport,
} from '@/api/crawlerConfig'
import { errorMessage } from '@/api/errors'
import CardSkeleton from '@/components/CardSkeleton.vue'
import ExportButton from '@/components/ExportButton.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { useExcelExport } from '@/composables/useExcelExport'
import { configResultText } from '@/modules/system/scheduler/crawlerConfig'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import ConfigNewSites from './ConfigNewSites.vue'
import ConfigOverview from './ConfigOverview.vue'
import ConfigPeriodPanel from './ConfigPeriodPanel.vue'
import ConfigProvinceDialog from './ConfigProvinceDialog.vue'
import ConfigStatusPanel from './ConfigStatusPanel.vue'
import { periodName as nameOf } from './report'
import { useConfigSync } from './useConfigSync'

const RESOURCE = 'policy.crawler_config'
const auth = useAuthStore()

const unit = ref<ConfigUnit>('week')
/** 所选这期的第一天；空表示用后端的默认（周看上周，月、季度、年看当前这期）。 */
const period = ref('')
const report = ref<CrawlerConfigReport | null>(null)
const loading = ref(false)
const error = ref('')
/** 各省配置弹窗：点配置数量的柱子或「各省明细」打开。 */
const provincesOpen = ref(false)
/** 弹窗里点中的省份：抽屉里看这个省这期配置的网站。 */
const province = ref('')
let sequence = 0

// 同步在排队或执行时轮询状态，结束后刷新统计；离开页面就停。
const { syncing, running, failure, poll: pollStatus, syncNow } = useConfigSync(load)

const periodName = computed(() => (report.value ? nameOf(report.value) : ''))
/** 卡片和透视表的数字点了去信源管理；没有信源管理权限就只是数字。 */
const sourcesLink = computed(() => (auth.canRead('policy.sources')
  ? (crawlerStatus: string, provinceName = '') => ({
      path: '/policy/sources',
      query: { ...(crawlerStatus ? { crawler_status: crawlerStatus } : {}), ...(provinceName ? { province_name: provinceName } : {}) },
    })
  : null))
/** 领导只看数据更新时间；能同步的人再看规则表的对账细节（没填编码、信源表里没有的）。 */
const lastSync = computed(() => {
  const sync = report.value?.last_sync
  if (!sync) return '规则表还没有同步过'
  return `数据更新于 ${formatTime(sync.finished_at).slice(0, 16)}`
})
const syncDetail = computed(() => {
  const sync = report.value?.last_sync
  return sync && auth.canFull(RESOURCE) ? `${configResultText(sync)}。每天 18:00 按爬虫同事的规则表自动更新` : '每天 18:00 按爬虫同事的规则表自动更新'
})

const { exporting, onExport } = useExcelExport({
  path: `${CRAWLER_CONFIG_BASE}/report/export`,
  filename: () => `爬虫配置统计_${report.value?.period_from ?? ''}至${report.value?.period_to ?? ''}.xlsx`,
  filters: (): Record<string, string> => ({ unit: unit.value, ...(period.value ? { period: period.value } : {}) }),
})

function pickUnit(value: ConfigUnit): void {
  void load(value, '')
}

/** 点柱子：整页换到那一期（卡片、下载报告跟着走），同时弹出这期各省配置。 */
function pickPeriod(from: string): void {
  provincesOpen.value = true
  if (from === report.value?.period_from) return
  void load(unit.value, from)
}

/** 拿到那一期的数据才换过去：原来先改了「当前期」再请求，失败时页面显示旧一期、下载的却是新一期，
 * 再点同一根柱子还会被当成「已经在这期」拦下、没法重试。 */
async function load(nextUnit: ConfigUnit = unit.value, nextPeriod: string = period.value): Promise<void> {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const data = await getCrawlerConfigReport(nextUnit, nextPeriod || undefined)
    if (current === sequence) {
      report.value = data
      unit.value = data.unit
      period.value = data.period_from
    }
  } catch (cause) {
    if (current === sequence) error.value = errorMessage(cause, '暂时无法获取统计，请稍后重试。')
  } finally {
    if (current === sequence) loading.value = false
  }
}

onMounted(() => {
  void load()
  void pollStatus()
})
</script>

<template>
  <div class="config">
    <div class="heading">
      <div class="caption">
        <h1>爬虫配置统计</h1>
        <span
          class="sync-time"
          :title="syncDetail"
        >{{ lastSync }}</span>
      </div>
      <div class="actions">
        <el-button
          v-if="auth.canFull(RESOURCE)"
          :icon="Refresh"
          :loading="syncing || running"
          @click="syncNow"
        >
          {{ running ? '正在同步规则表' : '立即同步' }}
        </el-button>
        <ExportButton
          :allowed="auth.canExport(RESOURCE)"
          :loading="exporting"
          :disabled="!report"
          hint="第一张是正在看的这一期各省配置网站数量（省份 / 配置网站数量 / 总计），另有配置明细、分省爬虫状态、各期趋势、异常清单。"
          @click="onExport"
        >
          下载报告
        </ExportButton>
      </div>
    </div>
    <el-alert
      v-if="failure || error"
      :title="failure || error"
      type="error"
      :closable="false"
      show-icon
    />

    <template v-if="loading && !report">
      <CardSkeleton
        :count="4"
        :columns="4"
      />
      <TableSkeleton
        :rows="6"
        :columns="5"
      />
    </template>

    <template v-else-if="report">
      <ConfigOverview
        :report="report"
        :period-name="periodName"
        :sources-link="sourcesLink"
      />
      <ConfigPeriodPanel
        :report="report"
        :period-name="periodName"
        :loading="loading"
        @unit="pickUnit"
        @period="pickPeriod"
        @provinces="provincesOpen = true"
      />
      <ConfigStatusPanel
        :report="report"
        :sources-link="sourcesLink"
      />
      <ConfigProvinceDialog
        v-model="provincesOpen"
        :report="report"
        :period-name="periodName"
        :loading="loading"
        @province="province = $event"
      />
      <ConfigNewSites
        :report="report"
        :period-name="periodName"
        :province="province"
        @close="province = ''"
      />
    </template>
  </div>
</template>

<style scoped>
.config { display: flex; flex-direction: column; gap: var(--zt-space-3); }
.heading, .caption, .actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 16px; }
.heading { justify-content: space-between; }
.caption h1 { margin: 0; font-size: 14px; font-weight: 600; color: var(--zt-ink-900); }
.sync-time { color: var(--zt-ink-500); font-size: 12px; font-variant-numeric: tabular-nums; }
.actions { gap: 8px; }
.actions .el-button + .el-button { margin-left: 0; }
</style>
