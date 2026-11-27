<script setup lang="ts">
import { Download, Lightning, Refresh } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { errorMessage } from '@/api/errors'
import {
  getThinktankStatistics,
  type RankedDocItem,
  type ThinktankStatisticsPayload,
  type ThinktankStatsGranularity,
  type ThinktankStatsLibrary,
  type ThinktankStatsPreset,
} from '@/api/thinktankStats'
import { useExcelExport } from '@/composables/useExcelExport'
import { useAuthStore } from '@/stores/auth'
import ThinktankDocPeekDrawer from './ThinktankDocPeekDrawer.vue'
import ThinktankKpiGrid from './ThinktankKpiGrid.vue'
import ThinktankLeaderboards from './ThinktankLeaderboards.vue'
import ThinktankStructurePanel from './ThinktankStructurePanel.vue'
import ThinktankTrendPanel from './ThinktankTrendPanel.vue'

const LIBRARIES: { key: ThinktankStatsLibrary; label: string; dot?: string }[] = [
  { key: 'all', label: '全部三库' },
  { key: 'knowledge', label: '资料库', dot: 'knowledge' },
  { key: 'reports', label: '报告库', dot: 'reports' },
  { key: 'proposals', label: '方案库', dot: 'proposals' },
]

const GRANULARITIES: { key: ThinktankStatsGranularity; label: string }[] = [
  { key: 'day', label: '按日' },
  { key: 'week', label: '按周' },
  { key: 'month', label: '按月' },
  { key: 'quarter', label: '按季' },
  { key: 'year', label: '按年' },
]

const PRESETS: { key: ThinktankStatsPreset; label: string }[] = [
  { key: '7d', label: '近 7 天' },
  { key: '30d', label: '近 30 天' },
  { key: 'quarter', label: '本季度' },
  { key: 'year', label: '今年以来' },
  { key: 'all', label: '全部' },
]

const auth = useAuthStore()
const router = useRouter()

const library = ref<ThinktankStatsLibrary>('all')
const granularity = ref<ThinktankStatsGranularity>('week')
const preset = ref<ThinktankStatsPreset>('30d')
const customRange = ref<[string, string] | null>(null)

const data = ref<ThinktankStatisticsPayload | null>(null)
const loading = ref(false)
const loadError = ref('')

const peekVisible = ref(false)
const peekTarget = ref<RankedDocItem | null>(null)

let seq = 0
const canExport = computed(() => auth.canExport('thinktank.statistics'))

const windowLabel = computed(() => {
  if (customRange.value) return `${customRange.value[0]} 至 ${customRange.value[1]}`
  return PRESETS.find(p => p.key === preset.value)?.label ?? '本周期'
})

const scopeLabel = computed(() => LIBRARIES.find(l => l.key === library.value)?.label ?? '智库三库')
const topCategory = computed(() => data.value?.dimensions[0]?.items[0] ?? null)

function buildQueryParams(): Record<string, string> {
  return {
    library: library.value,
    granularity: granularity.value,
    preset: preset.value,
    ...(customRange.value ? { date_from: customRange.value[0], date_to: customRange.value[1] } : {}),
  }
}

const { exporting, onExport } = useExcelExport({
  path: '/thinktank/statistics/export',
  filename: () => `智库统计简报_${scopeLabel.value}_${windowLabel.value}.xlsx`,
  filters: buildQueryParams,
})

async function load() {
  const current = ++seq
  loading.value = true
  loadError.value = ''
  try {
    const res = await getThinktankStatistics(buildQueryParams())
    if (current === seq) data.value = res
  } catch (err) {
    if (current === seq) loadError.value = errorMessage(err, '智库统计加载失败')
  } finally {
    if (current === seq) loading.value = false
  }
}

function selectLibrary(next: ThinktankStatsLibrary) {
  library.value = next
  void load()
}

function selectGranularity(next: ThinktankStatsGranularity) {
  granularity.value = next
  void load()
}

function selectPreset(next: ThinktankStatsPreset) {
  preset.value = next
  customRange.value = null
  void load()
}

function onCustomRangeChange(val: [string, string] | null) {
  customRange.value = val
  void load()
}

function goUndefined() {
  const targetLib = library.value === 'all' ? 'knowledge' : library.value
  const routeName = { knowledge: 'thinktank-knowledge', reports: 'thinktank-reports', proposals: 'thinktank-proposals' }[targetLib]
  void router.push({ name: routeName, query: { tag_status: '未定义' } })
}

function onDrill(payload: { library: ThinktankStatsLibrary; field: string; value: string }) {
  const targetLib = payload.library === 'all' ? 'knowledge' : payload.library
  const routeName = { knowledge: 'thinktank-knowledge', reports: 'thinktank-reports', proposals: 'thinktank-proposals' }[targetLib]
  const queryValue = payload.value === '未定义' || payload.value === '未填写' ? undefined : payload.value
  const query = queryValue ? { [payload.field]: queryValue } : { tag_status: '未定义' }
  void router.push({ name: routeName, query })
}

function openDocPeek(doc: RankedDocItem) {
  peekTarget.value = doc
  peekVisible.value = true
}

const fmt = (n?: number) => (n ?? 0).toLocaleString('zh-CN')

onMounted(() => { void load() })
</script>

<template>
  <div class="tt-stats">
    <h1 class="sr-only">
      智库统计中心
    </h1>

    <header class="tt-ctrl">
      <div class="tt-ctrl__group">
        <div
          class="tt-seg"
          role="tablist"
          aria-label="库范围"
        >
          <button
            v-for="item in LIBRARIES"
            :key="item.key"
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': library === item.key }"
            @click="selectLibrary(item.key)"
          >
            <span
              v-if="item.dot"
              class="tt-dot"
              :class="`tt-dot--${item.dot}`"
            />
            {{ item.label }}
          </button>
        </div>

        <div
          class="tt-seg"
          role="tablist"
          aria-label="时间粒度"
        >
          <button
            v-for="g in GRANULARITIES"
            :key="g.key"
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': granularity === g.key }"
            @click="selectGranularity(g.key)"
          >
            {{ g.label }}
          </button>
        </div>

        <div class="tt-pills">
          <button
            v-for="p in PRESETS"
            :key="p.key"
            type="button"
            class="tt-pill"
            :class="{ 'is-active': !customRange && preset === p.key }"
            @click="selectPreset(p.key)"
          >
            {{ p.label }}
          </button>
        </div>

        <el-date-picker
          :model-value="customRange"
          type="daterange"
          size="small"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          unlink-panels
          class="tt-ctrl__date"
          @update:model-value="onCustomRangeChange"
        />
      </div>

      <div class="tt-ctrl__group">
        <el-button
          size="small"
          :icon="Refresh"
          :loading="loading"
          @click="load"
        >
          刷新
        </el-button>
        <el-button
          v-if="canExport"
          size="small"
          type="primary"
          :icon="Download"
          :loading="exporting"
          @click="onExport"
        >
          导出统计简报
        </el-button>
      </div>
    </header>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
    >
      <el-button
        size="small"
        @click="load"
      >
        重试
      </el-button>
    </el-alert>

    <template v-if="data">
      <section
        class="tt-insight"
        aria-live="polite"
      >
        <span
          class="tt-insight__icon"
          aria-hidden="true"
        >
          <el-icon><Lightning /></el-icon>
        </span>
        <div class="tt-insight__body">
          <template v-if="data.assets.total_files > 0">
            {{ scopeLabel }}累计沉淀
            <strong class="tt-hl tabular">{{ fmt(data.assets.total_files) }}</strong> 份资产（<strong class="tabular">{{ data.assets.total_size_display }}</strong>），标签完善率
            <strong class="tt-good tabular">{{ data.assets.defined_rate.toFixed(1) }}%</strong>；
            {{ windowLabel }}新增入库 <strong class="tt-hl tabular">{{ fmt(data.behavior.uploads) }}</strong> 份，累计产生
            <strong class="tt-hl tabular">{{ fmt(data.behavior.previews) }}</strong> 次预览与
            <strong class="tt-hl tabular">{{ fmt(data.behavior.downloads) }}</strong> 次下载
            <template v-if="topCategory">
              ，其中「<strong>{{ topCategory.name }}</strong>」体量居首（{{ fmt(topCategory.count) }} 份）
            </template>。
          </template>
          <template v-else>
            当前 <strong class="tt-hl">{{ scopeLabel }}</strong> 尚未入库文件，完成首批上传与打标后将自动纳入全盘大盘统计。
          </template>
        </div>
        <span class="tt-insight__meta tabular">
          <span class="tt-live-dot" />
          全局统计 · 更新于 {{ data.as_of.slice(11, 16) }}
        </span>
      </section>

      <ThinktankKpiGrid
        :assets="data.assets"
        :behavior="data.behavior"
        :library="library"
        :window-label="windowLabel"
        :window-days="data.window.days"
        @go-undefined="goUndefined"
      />

      <ThinktankStructurePanel
        :assets="data.assets"
        :library="library"
        :dimensions="data.dimensions"
        :proposal-win="data.proposal_win"
        :loading="loading"
        @select-library="selectLibrary"
        @drill="onDrill"
      />

      <ThinktankTrendPanel
        :trend="data.trend"
        :granularity="granularity"
        :window-label="windowLabel"
        :loading="loading"
      />

      <ThinktankLeaderboards
        :top-documents="data.top_documents"
        :top-contributors="data.top_contributors"
        :loading="loading"
        @peek-doc="openDocPeek"
      />
    </template>

    <el-skeleton
      v-else-if="loading"
      :rows="10"
      animated
    />

    <ThinktankDocPeekDrawer
      v-model="peekVisible"
      :target="peekTarget"
    />
  </div>
</template>

<style scoped src="./thinktank-statistics.css"></style>
