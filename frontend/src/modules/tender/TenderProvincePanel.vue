<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TenderPoint } from '@/api/tender'
import { shortProvinceName } from './statistics'

const props = defineProps<{ provinces: TenderPoint[] }>()
const mode = ref<'rank' | 'table'>('rank')
const keyword = ref('')

const filtered = computed(() => {
  const q = keyword.value.trim()
  if (!q) return props.provinces
  return props.provinces.filter(row => (row.province ?? '').includes(q))
})

const totalSum = computed(() =>
  props.provinces.reduce((sum, row) => sum + row.purchaser + row.winbid, 0),
)
const maxTotal = computed(() =>
  Math.max(1, ...props.provinces.map(row => row.purchaser + row.winbid)),
)

const ranked = computed(() =>
  filtered.value.map((row, index) => {
    const total = row.purchaser + row.winbid
    return {
      rank: index + 1,
      name: row.province || '未填写省份',
      shortName: shortProvinceName(row.province || '未填写省份'),
      purchaser: row.purchaser,
      winbid: row.winbid,
      total,
      purchaserPct: (row.purchaser / maxTotal.value) * 100,
      winbidPct: (row.winbid / maxTotal.value) * 100,
      share: totalSum.value ? `${((total * 100) / totalSum.value).toFixed(1)}%` : '0%',
    }
  }),
)

const columns = computed(() => {
  const mid = Math.ceil(ranked.value.length / 2)
  return [ranked.value.slice(0, mid), ranked.value.slice(mid)]
})
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <div>
        <h3>分省份数据分布（全部 {{ provinces.length }} 项）</h3>
        <p class="panel-note">
          蓝色为招标、绿色为中标，按各省合计降序排列，完整展示全部省级区域及未填写项
        </p>
      </div>
      <div class="panel-tools">
        <el-input
          v-model="keyword"
          placeholder="筛选省份"
          clearable
          size="small"
          style="width: 140px"
        />
        <el-radio-group
          v-model="mode"
          size="small"
          aria-label="省份展示方式"
        >
          <el-radio-button value="rank">
            分布排行
          </el-radio-button>
          <el-radio-button value="table">
            完整明细表
          </el-radio-button>
        </el-radio-group>
      </div>
    </header>

    <div
      v-if="!filtered.length"
      class="empty-note"
    >
      {{ provinces.length ? '未匹配到相关省份' : '所选日期暂无分省数据' }}
    </div>

    <div
      v-else-if="mode === 'rank'"
      class="rank-grid"
    >
      <ul
        v-for="(col, colIdx) in columns"
        :key="colIdx"
        class="rank-col"
      >
        <li
          v-for="row in col"
          :key="row.name"
          class="rank-row"
          :title="`${row.name}：招标 ${row.purchaser.toLocaleString('zh-CN')} · 中标 ${row.winbid.toLocaleString('zh-CN')}（占 ${row.share}）`"
        >
          <span
            class="rank-num"
            :class="{ 'is-top': row.rank <= 3 }"
          >{{ row.rank }}</span>
          <span class="rank-name">{{ row.shortName }}</span>
          <span
            class="rank-track"
            aria-hidden="true"
          >
            <span
              class="seg seg-p"
              :style="{ width: `${row.purchaserPct}%` }"
            />
            <span
              class="seg seg-w"
              :style="{ width: `${row.winbidPct}%` }"
            />
          </span>
          <span class="rank-meta">
            <strong>{{ row.total.toLocaleString('zh-CN') }}</strong>
            <span class="rank-share">{{ row.share }}</span>
          </span>
        </li>
      </ul>
    </div>

    <el-table
      v-else
      :data="ranked"
      stripe
      max-height="420"
      empty-text="所选日期暂无数据"
    >
      <el-table-column
        prop="rank"
        label="排名"
        width="70"
        align="center"
      />
      <el-table-column
        prop="name"
        label="省份"
        min-width="160"
      />
      <el-table-column
        label="招标数据量"
        align="right"
      >
        <template #default="{ row }">
          <span class="tabular">{{ row.purchaser.toLocaleString('zh-CN') }}</span>
        </template>
      </el-table-column>
      <el-table-column
        label="中标数据量"
        align="right"
      >
        <template #default="{ row }">
          <span class="tabular">{{ row.winbid.toLocaleString('zh-CN') }}</span>
        </template>
      </el-table-column>
      <el-table-column
        label="合计"
        align="right"
      >
        <template #default="{ row }">
          <strong class="tabular">{{ row.total.toLocaleString('zh-CN') }}</strong>
        </template>
      </el-table-column>
      <el-table-column
        prop="share"
        label="占比"
        width="90"
        align="right"
      />
    </el-table>
  </section>
</template>

<style scoped>
.panel {
  padding: 18px 22px;
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: 12px;
  box-shadow: var(--zt-shadow);
  min-width: 0;
}
.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.panel-head h3 { margin: 0; font-size: 15px; font-weight: 650; color: var(--zt-ink-900); }
.panel-note { margin: 4px 0 0; font-size: 12px; color: var(--zt-ink-500); }
.panel-tools { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.empty-note { padding: 24px 0; text-align: center; font-size: 13px; color: var(--zt-ink-500); }
.rank-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 28px; }
.rank-col { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; }
.rank-row {
  display: grid;
  grid-template-columns: 24px 68px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: var(--zt-radius);
  transition: background-color 140ms ease;
}
.rank-row:hover { background: var(--zt-row-hover); }
.rank-num { font-size: 12px; font-weight: 600; color: var(--zt-ink-400); text-align: center; font-variant-numeric: tabular-nums; }
.rank-num.is-top { color: var(--zt-blue-600); }
.rank-name { font-size: 13px; font-weight: 500; color: var(--zt-ink-900); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank-track { display: flex; gap: 2px; height: 9px; border-radius: 999px; background: var(--zt-soft); overflow: hidden; }
.seg { height: 100%; }
.seg-p { background: var(--zt-blue-600); border-radius: 999px 0 0 999px; }
.seg-w { background: var(--chart-normal); border-radius: 0 999px 999px 0; }
.rank-meta { display: inline-flex; align-items: baseline; gap: 8px; font-variant-numeric: tabular-nums; }
.rank-meta strong { font-size: 13px; font-weight: 600; color: var(--zt-ink-900); min-width: 58px; text-align: right; }
.rank-share { font-size: 12px; color: var(--zt-ink-500); min-width: 40px; text-align: right; }
.tabular { font-variant-numeric: tabular-nums; }
@media (max-width: 960px) {
  .rank-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
