<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { listCandidates, type CandidateItem, type CandidateQuery, type CandidateSummary } from '@/api/scenarioCandidates'
import AuditLogButton from '@/components/AuditLogButton.vue'
import { useAuthStore } from '@/stores/auth'
import FilterBar from '@/components/FilterBar.vue'
import FilterKeyword from '@/components/FilterKeyword.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import ListEmpty from '@/components/ListEmpty.vue'
import ListPage from '@/components/ListPage.vue'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { hasActiveFilters, useListLoader } from '@/composables/useListLoader'
import { useListQuery } from '@/composables/useListQuery'
import { reviewQuery } from '../shared/reviewQuery'
import CandidateBatchActions from './CandidateBatchActions.vue'
import EnrichConfirm from './EnrichConfirm.vue'
import StatusTabs from './StatusTabs.vue'
import { listEnrichPending } from '@/api/codebook'
import CandidateRowsDrawer from './CandidateRowsDrawer.vue'
import { PENDING, RESOURCE, decisionText, levelTag, matchOf, summaryText, whereText } from './candidates'

const query = reactive({
  status: PENDING,
  keyword: [] as string[],
  industry_l1: [] as string[],
  level_label: [] as string[],
  match: [] as string[],
  min_policies: '',
  page: 1,
  page_size: 20,
})
const auth = useAuthStore()
const filters = useFilterOptions('/policy/scenario-candidates')
const summary = ref<CandidateSummary | null>(null)
const listQuery = useListQuery(query, (): Promise<void> => load())

async function fetchPage(params: Record<string, unknown>) {
  if (params.status === ENRICH_TAB) {
    // 补充待确认是码表里的数据，不查候选列表；只取一下各页签的数
    summary.value = (await listCandidates({ status: PENDING, page_size: 1 })).summary
    return { items: [], total: 0 }
  }
  const cleaned = Object.fromEntries(Object.entries(params).filter(([, value]) => value !== '')) as CandidateQuery
  const page = await listCandidates(cleaned)
  summary.value = page.summary
  return page
}

const { items, total, loading, loadError, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: fetchPage,
  errorText: '加载新增场景失败',
})

const pending = computed(() => listQuery.applied.status === PENDING)
// 「补充待确认」页签：采纳进码表的新场景，AI 补好描述等人确认（码表的数据，要能看码表）
const ENRICH_TAB = '补充待确认'
const enriching = computed(() => listQuery.applied.status === ENRICH_TAB)
const enrichCount = ref(0)
async function loadEnrichCount() {
  if (!auth.canRead('codebook.scenarios')) return
  try {
    enrichCount.value = (await listEnrichPending()).items.length
  } catch {
    enrichCount.value = 0
  }
}
// 页签不算筛选：不计入「已筛选 N 项」，待审为空时写「暂无记录」、不给「清除筛选」
const draftFilters = computed(() => ({ ...query, status: '' }))
const appliedFilters = computed(() => ({ ...listQuery.applied, status: '' }))
const filtered = computed(() => hasActiveFilters(appliedFilters.value))
const counts = computed(() => summary.value?.by_status ?? {})

function switchStatus(value: string | number | boolean | undefined) {
  listQuery.replaceApplied('status', String(value))
  void load()
}

/** 「重置」只清筛选条件，留在当前页签。 */
function resetFilters() {
  Object.assign(query, { keyword: [], industry_l1: [], level_label: [], match: [], min_policies: '' })
  listQuery.search()
}

function reviewRoute(row: CandidateItem, index: number) {
  const position = (query.page - 1) * query.page_size + index
  return { name: 'policy-scenario-candidate-review', params: { id: row.id }, query: reviewQuery(listQuery.applied, position, query.page_size) }
}

const drawer = ref<CandidateItem | null>(null)

const canDecide = computed(() => auth.canFull(RESOURCE))
const canWriteCodebook = computed(() => canDecide.value && auth.canFull('codebook.scenarios'))
// 批量只在待审页签、只勾当前页
const table = ref<{ clearSelection: () => void }>()
const checked = ref<CandidateItem[]>([])
async function afterBatch() {
  table.value?.clearSelection()
  checked.value = []
  await load()
}

onMounted(() => {
  void load()
  void filters.load()
  void loadEnrichCount()
})
</script>

<template>
  <div>
    <ListPage
      title="新增场景审核"
      :total="total"
      :page="query.page"
      :page-size="query.page_size"
      :loading="loading"
      :error="loadError"
      :hide-pager="enriching"
      @retry="load"
      @update:page="query.page = $event"
      @update:page-size="query.page_size = $event"
      @change="load"
    >
      <template #summary>
        <p class="candidates__summary">
          {{ summaryText(summary) }}
          <span class="candidates__note">AI 从政策解读里写出来、码表里没有的场景，一行一个。看清是几级、码表里有没有像它的，再决定；决定一次，提出它的政策一起生效。</span>
        </p>
      </template>
      <template #actions>
        <StatusTabs
          :value="String(listQuery.applied.status)"
          :counts="counts"
          :enrich-tab="auth.canRead('codebook.scenarios') ? ENRICH_TAB : ''"
          :enrich-count="enrichCount"
          @change="switchStatus"
        />
        <CandidateBatchActions
          v-if="pending && canDecide"
          :checked="checked"
          :can-write-codebook="canWriteCodebook"
          @done="afterBatch"
        />
        <AuditLogButton :module="RESOURCE" />
      </template>
      <template
        v-if="!enriching"
        #filters
      >
        <FilterBar
          :query="draftFilters"
          :applied="appliedFilters"
          @search="listQuery.search"
          @reset="resetFilters"
        >
          <el-form-item label="场景名称">
            <FilterKeyword
              v-model="query.keyword"
              label="场景名称"
              placeholder="输入场景名称关键词"
              @search="listQuery.search"
            />
          </el-form-item>
          <el-form-item label="一级行业">
            <FilterSelect
              v-model="query.industry_l1"
              v-bind="filters.bind('industry_l1')"
              size="short"
            />
          </el-form-item>
          <el-form-item label="几级">
            <FilterSelect
              v-model="query.level_label"
              v-bind="filters.bind('level_label')"
              size="short"
            />
          </el-form-item>
          <el-form-item label="码表里像它的">
            <FilterSelect
              v-model="query.match"
              v-bind="filters.bind('match')"
              size="short"
            />
          </el-form-item>
          <template #advanced>
            <el-form-item label="政策数不少于">
              <el-input
                v-model="query.min_policies"
                class="candidates__min"
                inputmode="numeric"
                placeholder="如 3"
                @keyup.enter="listQuery.search"
              />
            </el-form-item>
          </template>
        </FilterBar>
      </template>
      <EnrichConfirm
        v-if="enriching"
        @count="enrichCount = $event"
      />
      <el-table
        v-else
        ref="table"
        v-loading="loading"
        class="data-table"
        :data="items"
        @selection-change="checked = $event"
      >
        <template #empty>
          <ListEmpty
            :loading="loading"
            :filtered="filtered"
            @reset="resetFilters"
          />
        </template>
        <el-table-column
          v-if="pending && canDecide"
          type="selection"
          width="44"
        />
        <el-table-column
          label="新增场景"
          min-width="200"
          show-overflow-tooltip
        >
          <template #default="{ row, $index }">
            <RouterLink
              v-if="row.id"
              class="candidates__name"
              :to="reviewRoute(row, $index)"
            >
              {{ row.name }}
            </RouterLink>
          </template>
        </el-table-column>
        <el-table-column
          label="几级"
          width="88"
        >
          <template #default="{ row }">
            <span class="candidates__level">{{ levelTag(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="挂在哪"
          min-width="200"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            {{ whereText(row) }}
          </template>
        </el-table-column>
        <el-table-column
          v-if="pending"
          label="码表里像它的"
          min-width="280"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <template v-if="row.id">
              <span :class="['candidates__match', `candidates__match--${matchOf(row).kind}`]">{{ matchOf(row).label }}</span>
              {{ matchOf(row).name }}<span
                v-if="matchOf(row).note"
                class="candidates__none"
              > · {{ matchOf(row).note }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column
          v-else
          label="决定"
          min-width="320"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            {{ decisionText(row) }}
          </template>
        </el-table-column>
        <el-table-column
          label="政策数"
          width="90"
          align="right"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              :aria-label="`看提出「${row.name}」的 ${row.policy_count} 条政策`"
              @click="drawer = row"
            >
              {{ row.policy_count.toLocaleString() }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="80"
          class-name="table-action"
        >
          <template #default="{ row, $index }">
            <RouterLink
              v-if="row.id"
              class="table-link"
              :to="reviewRoute(row, $index)"
            >
              {{ pending ? '审核' : '查看' }}
            </RouterLink>
          </template>
        </el-table-column>
      </el-table>
    </ListPage>
    <CandidateRowsDrawer
      :candidate="drawer"
      @close="drawer = null"
      @changed="load"
    />
  </div>
</template>

<style scoped>
.candidates__summary {
  margin: 0;
  font-size: 15px;
  line-height: 24px;
}

.candidates__note {
  display: block;
  color: var(--zt-ink-500);
  font-size: 13px;
}

.candidates__name {
  font-weight: 600;
}

.candidates__none {
  color: var(--zt-ink-500);
}

.candidates__level {
  padding: 1px 8px;
  border: 1px solid var(--zt-warning-border);
  border-radius: 4px;
  background: var(--zt-warning-soft);
  color: var(--zt-warning-text);
  font-size: 12px;
}

.candidates__match {
  margin-right: 6px;
  padding: 1px 8px;
  border: 1px solid var(--zt-border);
  border-radius: 4px;
  background: var(--zt-soft);
  color: var(--zt-ink-700);
  font-size: 12px;
}

.candidates__match--ai {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary);
  color: var(--zt-panel);
}

.candidates__match--none {
  margin-right: 0;
  padding: 0;
  border: 0;
  background: none;
  color: var(--zt-ink-500);
  font-size: 14px;
}

.candidates__min {
  width: 120px;
}
</style>
