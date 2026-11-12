<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { errorMessage } from '@/api/errors'
import { getTenderStatistics, getTenderTotals, type TenderStatistics, type TenderTotals } from '@/api/tender'
import BaseChart from '@/components/charts/BaseChart.vue'
import { useChartPalette } from '@/components/charts/echarts'
import { statisticsChart, recentRange } from './statistics'
const range = ref<[string, string]>(recentRange())
const report = ref<TenderStatistics | null>(null)
const totals = ref<TenderTotals | null>(null)
const error = ref('')
const totalError = ref('')
const loading = ref(false)
const totalsLoading = ref(false)
let totalTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false
onBeforeUnmount(() => { disposed = true; clearTimeout(totalTimer) })
const palette = useChartPalette()
let sequence = 0
const intakeChart = computed(() => statisticsChart(report.value?.daily ?? [], palette.value, 'intake'))
const workChart = computed(() => statisticsChart(report.value?.daily ?? [], palette.value, 'work'))
const workload = computed(() => report.value?.daily.reduce((sum, row) => sum + row.tagged, 0) ?? 0)
async function load() {
  const current = ++sequence
  error.value = ''
  if (!range.value?.[0] || !range.value[1]) { error.value = '请选择统计日期范围'; return }
  loading.value = true
  try {
    const result = await getTenderStatistics(...range.value)
    if (current === sequence) report.value = result
  } catch (cause) {
    if (current === sequence) error.value = errorMessage(cause, '统计加载失败')
  } finally { if (current === sequence) loading.value = false }
}
async function loadTotals() {
  clearTimeout(totalTimer)
  totalsLoading.value = true
  totalError.value = ''
  try {
    const result = await getTenderTotals()
    if (disposed) return
    if (result.data) totals.value = result.data
    if (result.state === 'pending') {
      totalTimer = setTimeout(() => { void loadTotals() }, 3000)
      return
    }
    totalsLoading.value = false
    if (result.state === 'error') totalError.value = result.message
    else totals.value = result.data
  } catch (cause) {
    totalError.value = errorMessage(cause, '总量加载失败')
    totalsLoading.value = false
  }
}

const count = (value?: number) => value === undefined ? '—' : value.toLocaleString('zh-CN')
onMounted(() => { void load(); void loadTotals() })
</script>
<template>
  <div class="tender-statistics">
    <section
      v-loading="totalsLoading && !totals"
      class="panel"
    >
      <header>
        <h2>招中标数据总量</h2><el-button
          :loading="totalsLoading"
          @click="loadTotals"
        >
          刷新总量
        </el-button>
      </header>
      <el-alert
        v-if="totalError"
        :title="totalError"
        type="error"
        :closable="false"
      />
      <div
        v-if="totals || !totalError"
        class="metrics"
      >
        <div><span>数据总量</span><strong>{{ count(totals?.total) }}</strong></div>
        <div><span>招标总量</span><strong>{{ count(totals?.purchaser) }}</strong></div>
        <div><span>中标总量</span><strong>{{ count(totals?.winbid) }}</strong></div>
      </div>
      <p
        v-if="totals"
        class="note"
      >
        统计时间：{{ totals.as_of.replace('T', ' ').slice(0, 19) }} · 总量包含全部原始数据<span v-if="totalsLoading"> · 正在后台更新</span>
      </p>
    </section>
    <section class="panel">
      <el-form
        inline
        @submit.prevent="load"
      >
        <el-form-item label="统计日期（采集时间）">
          <el-date-picker
            v-model="range"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            :clearable="false"
            unlink-panels
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            native-type="submit"
            :loading="loading"
          >
            查询
          </el-button>
        </el-form-item>
      </el-form>
      <p class="note">
        按采集日期统计，单次最多 31 天。信息化标签与基础字段补充均按人工已处理记录计数，场景处理暂为 0；两项工序不相加计算数据条数。
      </p>
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
      >
        <el-button @click="load">
          重试
        </el-button>
      </el-alert>
    </section>
    <template v-if="report && !error">
      <p class="note">
        当前结果：{{ report.date_from }} 至 {{ report.date_to }} · 统计时间：{{ report.as_of.replace('T', ' ').slice(0, 19) }}
      </p>
      <section
        v-loading="loading"
        class="panel"
      >
        <h3>每天数据接入情况</h3>
        <BaseChart
          :option="intakeChart"
          label="招标与中标每日接入数量"
          height="300px"
        />
      </section>
      <section
        v-loading="loading"
        class="panel"
      >
        <h3>人工交付处理情况</h3>
        <div class="metrics">
          <div><span>打信息化标签</span><strong>{{ count(workload) }}</strong></div>
          <div><span>基础字段补充</span><strong>{{ count(workload) }}</strong></div>
          <div><span>场景补充（暂未开展）</span><strong>0</strong></div>
        </div>
        <BaseChart
          :option="workChart"
          label="每日信息化标签、基础字段补充与场景处理量"
          height="300px"
        />
      </section>
      <section class="panel">
        <h3>分省份数据量</h3>
        <el-table
          :data="report.provinces"
          stripe
          empty-text="所选日期暂无数据"
        >
          <el-table-column
            prop="province"
            label="省份"
            min-width="160"
          />
          <el-table-column
            prop="purchaser"
            label="招标数据量"
            align="right"
          />
          <el-table-column
            prop="winbid"
            label="中标数据量"
            align="right"
          />
          <el-table-column
            label="合计"
            align="right"
          >
            <template #default="{ row }">
              {{ count(row.purchaser + row.winbid) }}
            </template>
          </el-table-column>
        </el-table>
      </section>
      <section class="panel">
        <h3>每日统计明细</h3>
        <el-table
          :data="report.daily"
          stripe
        >
          <el-table-column
            prop="date"
            label="采集日期"
            width="140"
          />
          <el-table-column
            prop="purchaser"
            label="招标接入量"
            align="right"
          />
          <el-table-column
            prop="winbid"
            label="中标接入量"
            align="right"
          />
          <el-table-column
            prop="tagged"
            label="信息化标签"
            align="right"
          />
          <el-table-column
            prop="enriched"
            label="基础字段补充"
            align="right"
          />
          <el-table-column
            prop="scenario"
            label="场景补充"
            align="right"
          />
        </el-table>
      </section>
    </template>
    <p
      v-else-if="loading"
      role="status"
    >
      正在读取统计数据…
    </p>
  </div>
</template>
<style scoped>
.tender-statistics { display: grid; gap: 16px; }
.panel { padding: 20px 24px; border: 1px solid var(--zt-border); border-radius: 12px; background: var(--zt-panel); min-width: 0; }
header { display: flex; align-items: center; justify-content: space-between; }
h2, h3 { margin: 0 0 16px; font-size: 16px; color: var(--zt-ink-900); }
.metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; padding: 12px 0; }
.metrics > div { display: grid; gap: 10px; padding-left: 16px; border-left: 3px solid var(--zt-blue-600); }
.metrics span, .note { font-size: 13px; color: var(--zt-ink-500); line-height: 1.7; }
.metrics strong { font-size: 30px; font-variant-numeric: tabular-nums; color: var(--zt-ink-900); }
.note { margin: 8px 0 0; }
.el-form-item { margin-bottom: 8px; }
</style>
