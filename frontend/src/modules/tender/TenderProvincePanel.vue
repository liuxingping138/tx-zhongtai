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
        <div class="head-title-wrap">
          <span class="head-marker" />
          <h3>分省份数据分布（全部 {{ provinces.length }} 项）</h3>
        </div>
        <p class="panel-note">
          <template v-if="mode === 'delivery'">
            按人工审核通过量降序排列；绿色条为审核通过量，灰条为未通过储备；清晰呈现招标与中标细分及审核通过率
          </template>
          <template v-else-if="mode === 'table'">
            分省数据完整明细；展示各省招标/中标接入量、全量合计、招标审核通过、中标审核通过、人工审核通过及审核通过率
          </template>
          <template v-else>
            蓝色为招标、绿色为中标，按各省合计降序排列；醒目展示省级接入规模、人工审核通过数据及审核通过率
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
          aria-label="省份展示方式"
        >
          <el-radio-button value="rank">
            全量分布
          </el-radio-button>
          <el-radio-button value="delivery">
            审核通过排行
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
          :title="`${row.name}：总量 ${row.total.toLocaleString('zh-CN')}（招标 ${row.purchaser.toLocaleString('zh-CN')} / 中标 ${row.winbid.toLocaleString('zh-CN')}）· 人工审核通过 ${row.passed.toLocaleString('zh-CN')}（招标通过 ${row.passPurchaser.toLocaleString('zh-CN')} · 中标通过 ${row.passWinbid.toLocaleString('zh-CN')}）· 未通过 ${row.unpassed.toLocaleString('zh-CN')}（审核通过率 ${row.passRate}）`"
        >
          <span
            class="rank-num"
            :class="{ 'is-top-1': row.rank === 1, 'is-top-2': row.rank === 2, 'is-top-3': row.rank === 3 }"
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
              <div class="meta-col">
                <div class="pass-pill pass-pill--delivery">
                  <span class="pass-tag">审核通过</span>
                  <strong class="pass-val pass-val--lg">{{ row.passed.toLocaleString('zh-CN') }}</strong>
                  <span
                    v-if="row.passed > 0"
                    class="pass-split"
                  >
                    <span class="pass-seg pass-seg--p">招 {{ row.passPurchaser.toLocaleString('zh-CN') }}</span>
                    <span class="pass-sep">/</span>
                    <span class="pass-seg pass-seg--w">中 {{ row.passWinbid.toLocaleString('zh-CN') }}</span>
                  </span>
                </div>
              </div>
              <span
                class="rate-chip rate-chip--success tabular"
                title="审核通过率"
              >{{ row.passRate }}</span>
            </template>
            <template v-else>
              <div class="meta-col">
                <strong class="total-num tabular">{{ row.total.toLocaleString('zh-CN') }}</strong>
                <div
                  v-if="row.passed > 0"
                  class="pass-pill"
                  :title="`审核通过：招标 ${row.passPurchaser.toLocaleString('zh-CN')} · 中标 ${row.passWinbid.toLocaleString('zh-CN')}`"
                >
                  <span class="pass-tag">审核通过</span>
                  <span class="pass-val tabular">{{ row.passed.toLocaleString('zh-CN') }}</span>
                  <span class="pass-split">
                    <span class="pass-seg pass-seg--p">招 {{ row.passPurchaser }}</span>
                    <span class="pass-sep">/</span>
                    <span class="pass-seg pass-seg--w">中 {{ row.passWinbid }}</span>
                  </span>
                </div>
                <span
                  v-else
                  class="pass-pill pass-pill--zero"
                >未审核</span>
              </div>
              <span
                class="rate-chip tabular"
                :class="{ 'is-zero': row.passed === 0 }"
                title="审核通过率"
              >{{ row.passRate }}</span>
            </template>
          </span>
        </li>
      </ul>
    </div>

    <div
      v-else
      class="table-wrap"
    >
      <el-table
        :data="ranked"
        stripe
        max-height="420"
        empty-text="所选日期暂无数据"
        class="data-table google-data-table"
      >
        <el-table-column
          prop="rank"
          label="排名"
          width="62"
          align="center"
        >
          <template #default="{ row }">
            <span
              class="table-rank-badge"
              :class="{ 'is-top-1': row.rank === 1, 'is-top-2': row.rank === 2, 'is-top-3': row.rank === 3 }"
            >{{ row.rank }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="name"
          label="省份"
          min-width="110"
        >
          <template #default="{ row }">
            <span class="prov-name-cell">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="招标接入量"
          align="right"
          min-width="100"
        >
          <template #default="{ row }">
            <span class="tabular col-purchaser">{{ row.purchaser.toLocaleString('zh-CN') }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="中标接入量"
          align="right"
          min-width="100"
        >
          <template #default="{ row }">
            <span class="tabular col-winbid">{{ row.winbid.toLocaleString('zh-CN') }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="全量合计"
          align="right"
          min-width="105"
        >
          <template #default="{ row }">
            <strong class="tabular col-total">{{ row.total.toLocaleString('zh-CN') }}</strong>
          </template>
        </el-table-column>
        <el-table-column
          label="招标审核通过"
          align="right"
          min-width="116"
        >
          <template #default="{ row }">
            <span
              v-if="row.passPurchaser > 0"
              class="cell-pill cell-pill--purchaser tabular"
            >{{ row.passPurchaser.toLocaleString('zh-CN') }}</span>
            <span
              v-else
              class="cell-pill cell-pill--zero"
            >0</span>
          </template>
        </el-table-column>
        <el-table-column
          label="中标审核通过"
          align="right"
          min-width="116"
        >
          <template #default="{ row }">
            <span
              v-if="row.passWinbid > 0"
              class="cell-pill cell-pill--winbid tabular"
            >{{ row.passWinbid.toLocaleString('zh-CN') }}</span>
            <span
              v-else
              class="cell-pill cell-pill--zero"
            >0</span>
          </template>
        </el-table-column>
        <el-table-column
          label="人工审核通过"
          align="right"
          min-width="120"
        >
          <template #default="{ row }">
            <span
              v-if="row.passed > 0"
              class="cell-pill cell-pill--total-pass tabular"
            >{{ row.passed.toLocaleString('zh-CN') }}</span>
            <span
              v-else
              class="cell-pill cell-pill--zero"
            >0</span>
          </template>
        </el-table-column>
        <el-table-column
          label="未通过"
          align="right"
          min-width="95"
        >
          <template #default="{ row }">
            <span class="tabular col-unpassed">{{ row.unpassed.toLocaleString('zh-CN') }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="审核通过率"
          align="right"
          min-width="100"
        >
          <template #default="{ row }">
            <span
              class="cell-pill cell-pill--rate tabular"
              :class="{ 'is-high': parseFloat(row.passRate) >= 10 }"
            >{{ row.passRate }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="share"
          label="区间占比"
          width="88"
          align="right"
        >
          <template #default="{ row }">
            <span class="tabular col-share">{{ row.share }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </section>
</template>

<style scoped src="./tender-province.css"></style>
