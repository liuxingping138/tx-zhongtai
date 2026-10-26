<script setup lang="ts">
import { CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed } from 'vue'

import type { CrawlerConfigReport } from '@/api/crawlerConfig'
import { deltaText, periodRange, provinceRanking, provinceTableText } from './report'

/**
 * 点配置数量的柱子弹出：这一期各省配置了多少，排行榜一行一个省（名次、占比横条、数量、占比）。
 * 即每周汇报的那张表，可一键复制；点一行开抽屉看这个省配置的网站。
 */
const props = defineProps<{ report: CrawlerConfigReport; periodName: string; loading: boolean }>()
const emit = defineEmits<{ province: [name: string] }>()
const open = defineModel<boolean>({ required: true })

const range = computed(() => periodRange(props.report.unit, props.report.period_from, props.report.period_to))
const rows = computed(() => provinceRanking(props.report.provinces, props.report.new))
const delta = computed(() => deltaText(props.report.new, props.report.previous_new, props.report.unit))

async function copyTable(): Promise<void> {
  try {
    await navigator.clipboard.writeText(provinceTableText(props.report.provinces, props.report.new))
    ElMessage.success('已复制，可直接粘贴到 Excel 或微信')
  } catch {
    ElMessage.error('浏览器不允许复制，请用「下载报告」')
  }
}
</script>

<template>
  <el-dialog
    v-model="open"
    width="min(600px, calc(100vw - 32px))"
    class="province-dialog"
    :aria-label="`${periodName}各省配置`"
  >
    <template #header>
      <div class="head">
        <h2>{{ periodName }}各省配置</h2>
        <span class="range">{{ range }}</span>
      </div>
    </template>
    <div v-loading="loading">
      <div class="summary">
        <div class="total">
          <strong>{{ report.new.toLocaleString() }}</strong>
          <span>个网站</span>
        </div>
        <div class="facts">
          <span>{{ rows.length }} 个省份有配置</span>
          <span :class="`delta-${delta.tone}`">{{ delta.text }}</span>
        </div>
      </div>
      <p
        v-if="!rows.length"
        class="empty"
      >
        {{ periodName }}还没有配置网站。爬虫同事更新规则表后，每天 18:00 自动同步进来。
      </p>
      <ol
        v-else
        class="ranking"
      >
        <li
          v-for="row in rows"
          :key="row.province_name"
        >
          <button
            type="button"
            class="row"
            :title="`查看${row.province_name}${periodName}配置的网站`"
            @click="emit('province', row.province_name)"
          >
            <span
              class="rank"
              :class="{ top: row.rank <= 3 }"
            >{{ row.rank }}</span>
            <span class="name">{{ row.province_name }}</span>
            <span class="track"><span
              class="fill"
              :style="{ width: row.width }"
            /></span>
            <span class="count">{{ row.new.toLocaleString() }}</span>
            <span class="share">{{ row.share }}</span>
          </button>
        </li>
      </ol>
    </div>
    <template #footer>
      <span class="hint">点一行查看这个省配置的网站</span>
      <el-button
        :icon="CopyDocument"
        :disabled="!rows.length"
        @click="copyTable"
      >
        复制表格
      </el-button>
      <el-button
        type="primary"
        @click="open = false"
      >
        关闭
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.head { display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 10px; }
.head h2 { margin: 0; font-size: 16px; font-weight: 600; color: var(--zt-ink-900); }
.range { color: var(--zt-ink-500); font-size: 13px; font-variant-numeric: tabular-nums; }
.summary { display: flex; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; gap: 8px 16px; padding: 14px 16px; border-radius: var(--zt-radius); background: var(--zt-soft); }
.total { display: flex; align-items: baseline; gap: 6px; color: var(--zt-ink-500); font-size: 13px; }
.total strong { color: var(--zt-blue-600); font-size: 30px; font-weight: 600; line-height: 1; font-variant-numeric: tabular-nums; }
.facts { display: flex; flex-wrap: wrap; gap: 4px 16px; color: var(--zt-ink-700); font-size: 13px; }
.delta-good { color: var(--el-color-success); }
.delta-bad { color: var(--el-color-danger); }
.ranking { max-height: min(420px, 52vh); margin: 12px 0 0; padding: 0; overflow-y: auto; list-style: none; }
.row { display: grid; grid-template-columns: 24px minmax(72px, 8em) 1fr 52px 48px; align-items: center; gap: 12px; width: 100%; padding: 8px; border: 0; border-radius: 4px; background: none; color: var(--zt-ink-900); font: inherit; font-size: 13px; text-align: left; cursor: pointer; }
.row:hover { background: var(--zt-soft); }
.ranking li + li .row { border-top: 1px solid var(--zt-border); border-radius: 0; }
.rank { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: var(--zt-soft); color: var(--zt-ink-500); font-size: 12px; font-variant-numeric: tabular-nums; }
.rank.top { background: var(--zt-blue-600); color: #fff; font-weight: 600; }
.name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.track { height: 8px; border-radius: 4px; background: var(--zt-soft); overflow: hidden; }
.fill { display: block; height: 100%; border-radius: 4px; background: var(--zt-blue-600); }
.count { font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; }
.share { color: var(--zt-ink-500); font-size: 12px; text-align: right; font-variant-numeric: tabular-nums; }
.empty { margin: 0; padding: 40px 16px; color: var(--zt-ink-500); font-size: 13px; text-align: center; }
.hint { margin-right: auto; color: var(--zt-ink-500); font-size: 12px; }
:global(.province-dialog .el-dialog__footer) { display: flex; align-items: center; gap: 8px; }
:global(.province-dialog .el-dialog__footer .el-button + .el-button) { margin-left: 0; }
@media (max-width: 480px) {
  .row { grid-template-columns: 22px minmax(56px, 6em) 1fr 44px; gap: 8px; }
  .share { display: none; }
}
</style>
