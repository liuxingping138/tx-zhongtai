<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { TenderPoint } from '@/api/tender'
import FilterSelect from '@/components/FilterSelect.vue'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useAuthStore } from '@/stores/auth'
import { buildProvinceRows } from './statistics'

const props = defineProps<{ provinces: TenderPoint[] }>()
const mode = ref<'rank' | 'delivery' | 'table'>('rank')
const selectedProvinces = ref<string[]>([])

const auth = useAuthStore()
const areaFilters = useFilterOptions('/codebook/area-codes')
onMounted(() => {
  if (auth.canRead('codebook.area_codes')) void areaFilters.load()
})

const ranked = computed(() =>
  buildProvinceRows(props.provinces, selectedProvinces.value, mode.value === 'delivery' ? 'delivery' : 'total'),
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
          <template v-if="mode === 'delivery'">
            按已通过（状态 1 交付量）降序排列；绿色为已通过交付量，浅灰为未通过量，右侧展示交付数与通过率
          </template>
          <template v-else>
            蓝色为招标、绿色为中标，按各省合计降序排列，完整展示全部省级区域、交付量及通过率
          </template>
        </p>
      </div>
      <div class="panel-tools">
        <div class="province-select">
          <FilterSelect
            v-model="selectedProvinces"
            v-bind="areaFilters.bind('prov_name')"
            placeholder="筛选省份（码表枚举）"
            size="short"
          />
        </div>
        <el-radio-group
          v-model="mode"
          size="small"
          aria-label="省份展示方式"
        >
          <el-radio-button value="rank">
            全量分布
          </el-radio-button>
          <el-radio-button value="delivery">
            交付排行
          </el-radio-button>
          <el-radio-button value="table">
            完整明细表
          </el-radio-button>
        </el-radio-group>
      </div>
    </header>

    <div
      v-if="!ranked.length"
      class="empty-note"
    >
      {{ provinces.length ? '未匹配到相关省份' : '所选日期暂无分省数据' }}
    </div>

    <div
      v-else-if="mode === 'rank' || mode === 'delivery'"
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
          :title="`${row.name}：总量 ${row.total.toLocaleString('zh-CN')}（招标 ${row.purchaser.toLocaleString('zh-CN')} / 中标 ${row.winbid.toLocaleString('zh-CN')}）· 已通过 ${row.passed.toLocaleString('zh-CN')} · 未通过 ${row.unpassed.toLocaleString('zh-CN')}（通过率 ${row.passRate}）`"
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
            <template v-if="mode === 'delivery'">
              <span
                class="seg seg-w"
                :style="{ width: `${row.passedPct}%` }"
              />
              <span
                class="seg seg-u"
                :style="{ width: `${row.unpassedPct}%` }"
              />
            </template>
            <template v-else>
              <span
                class="seg seg-p"
                :style="{ width: `${row.purchaserPct}%` }"
              />
              <span
                class="seg seg-w"
                :style="{ width: `${row.winbidPct}%` }"
              />
            </template>
          </span>
          <span class="rank-meta">
            <template v-if="mode === 'delivery'">
              <strong class="meta-pass">{{ row.passed.toLocaleString('zh-CN') }}</strong>
              <span class="rank-share">{{ row.passRate }}</span>
            </template>
            <template v-else>
              <strong>{{ row.total.toLocaleString('zh-CN') }}</strong>
              <span class="rank-share">过 {{ row.passRate }}</span>
            </template>
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
        width="64"
        align="center"
      />
      <el-table-column
        prop="name"
        label="省份"
        min-width="140"
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
        label="全量合计"
        align="right"
      >
        <template #default="{ row }">
          <strong class="tabular">{{ row.total.toLocaleString('zh-CN') }}</strong>
        </template>
      </el-table-column>
      <el-table-column
        label="已通过（交付）"
        align="right"
      >
        <template #default="{ row }">
          <span class="tabular meta-pass">{{ row.passed.toLocaleString('zh-CN') }}</span>
        </template>
      </el-table-column>
      <el-table-column
        label="未通过"
        align="right"
      >
        <template #default="{ row }">
          <span class="tabular">{{ row.unpassed.toLocaleString('zh-CN') }}</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="passRate"
        label="通过率"
        width="86"
        align="right"
      />
      <el-table-column
        prop="share"
        label="全库占比"
        width="88"
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
.province-select { width: 210px; }
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
.seg-u { background: var(--zt-ink-300); border-radius: 0 999px 999px 0; }
.rank-meta { display: inline-flex; align-items: baseline; gap: 8px; font-variant-numeric: tabular-nums; }
.rank-meta strong { font-size: 13px; font-weight: 600; color: var(--zt-ink-900); min-width: 58px; text-align: right; }
.meta-pass { color: var(--zt-success-text); }
.rank-share { font-size: 12px; color: var(--zt-ink-500); min-width: 48px; text-align: right; }
.tabular { font-variant-numeric: tabular-nums; }
@media (max-width: 960px) {
  .rank-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
