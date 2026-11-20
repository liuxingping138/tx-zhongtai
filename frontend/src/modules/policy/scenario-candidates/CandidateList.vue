<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

import { listEnrichPending } from '@/api/codebook'
import { errorMessage } from '@/api/errors'
import {
  getCandidate,
  listCandidates,
  reopenCandidate,
  type CandidateItem,
  type CandidateQuery,
  type CandidateSummary,
} from '@/api/scenarioCandidates'
import AuditLogButton from '@/components/AuditLogButton.vue'
import FilterBar from '@/components/FilterBar.vue'
import FilterChipInput from '@/components/FilterChipInput.vue'
import FilterChipSelect from '@/components/FilterChipSelect.vue'
import FilterKeyword from '@/components/FilterKeyword.vue'
import ListPage from '@/components/ListPage.vue'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { hasActiveFilters, useListLoader } from '@/composables/useListLoader'
import { useListQuery } from '@/composables/useListQuery'
import { refreshMenuBadges } from '@/layouts/menuBadges'
import { useAuthStore } from '@/stores/auth'
import CandidateBatchActions from './CandidateBatchActions.vue'
import CandidateRowsDrawer from './CandidateRowsDrawer.vue'
import CandidateTable from './CandidateTable.vue'
import DecisionDialog from './DecisionDialog.vue'
import EnrichConfirm from './EnrichConfirm.vue'
import StatusTabs from './StatusTabs.vue'
import { PENDING, RESOURCE, summaryText } from './candidates'
import { useCandidateExtras } from './useCandidateExtras'
import { useListDecision } from './useListDecision'

/**
 * 新增场景审核：一行一个场景，就在这一行决定（采纳、合并、改名、驳回都先开确认框），点名称展开看依据。
 * 不再有单个场景的页面；从别处带 ?focus=<场景ID> 过来时，按它的名称筛出来并展开这一行。
 */
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
const route = useRoute()
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

// 「补充待确认」页签：采纳进码表的新场景，AI 补好描述等人确认（码表的数据，要能看码表）
const ENRICH_TAB = '补充待确认'
const pending = computed(() => listQuery.applied.status === PENDING)
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

const canDecide = computed(() => auth.canFull(RESOURCE))
const canWriteCodebook = computed(() => canDecide.value && auth.canFull('codebook.scenarios'))

const extras = useCandidateExtras()
const table = ref<{ clearSelection: () => void }>()
const checked = ref<CandidateItem[]>([])
/** 做完决定、批量、并入、改判之后：丢掉缓存的依据，重新载入，侧栏待审数跟着变 */
async function refreshAfter(ids: string[] = []) {
  extras.drop(...ids)
  table.value?.clearSelection()
  checked.value = []
  await load()
  refreshMenuBadges()
}
const decision = useListDecision(extras, () => refreshAfter())

const drawer = ref<CandidateItem | null>(null)
const drawerIndustries = computed(() => (drawer.value ? extras.get(drawer.value.id)?.detail?.industries ?? [] : []))
function openRows(row: CandidateItem) {
  drawer.value = row
  void extras.ensure(row.id)
}

const reopeningId = ref('')
async function reopen(row: CandidateItem) {
  if (reopeningId.value === row.id) return
  reopeningId.value = row.id
  try {
    await reopenCandidate(row.id, { version: row.version })
    ElMessage.success(`「${row.name}」已改判回待审`)
    await refreshAfter([row.id])
  } catch (error) {
    ElMessage.error(errorMessage(error, '没能改判，请重试'))
  } finally {
    if (reopeningId.value === row.id) reopeningId.value = ''
  }
}

/** ?focus=<场景ID>：从解读核对页、旧的审核页地址过来，筛出这个场景并展开 */
const focus = typeof route.query.focus === 'string' ? route.query.focus : ''
async function openFocus() {
  try {
    const found = await getCandidate(focus)
    Object.assign(query, { status: found.status, keyword: [found.name], industry_l1: [], level_label: [], match: [], min_policies: '' })
    listQuery.search()
  } catch {
    void load()
  }
}

onMounted(() => {
  if (focus) void openFocus()
  else void load()
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
      <!-- 顶部只留一句结论；「补充待确认」页签和待审无关，不显示 -->
      <template
        v-if="!enriching"
        #summary
      >
        <p class="candidates__summary">
          {{ summaryText(summary) }}
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
          @done="refreshAfter(checked.map(row => row.id))"
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
          variant="chips"
          @search="listQuery.search"
          @reset="resetFilters"
        >
          <template #search>
            <FilterKeyword
              v-model="query.keyword"
              label="场景名称"
              placeholder="搜索场景名称关键词…"
              class="filter-search-main"
            />
          </template>
          <FilterChipSelect
            v-model="query.industry_l1"
            label="一级行业"
            v-bind="filters.bind('industry_l1')"
          />
          <FilterChipSelect
            v-model="query.level_label"
            label="新增场景级别"
            v-bind="filters.bind('level_label')"
          />
          <FilterChipSelect
            v-model="query.match"
            label="码表里像它的"
            v-bind="filters.bind('match')"
          />
          <FilterChipInput
            v-model="query.min_policies"
            label="政策数"
            prefix="≥ "
            inputmode="numeric"
            placeholder="输入最少政策数，如 3"
          />
        </FilterBar>
      </template>
      <EnrichConfirm
        v-if="enriching"
        @count="enrichCount = $event"
      />
      <CandidateTable
        v-else
        ref="table"
        :items="items"
        :loading="loading"
        :filtered="filtered"
        :status="String(listQuery.applied.status)"
        :can-decide="canDecide"
        :can-write-codebook="canWriteCodebook"
        :extras="extras"
        :busy="decision.busy.value"
        :reopening-id="reopeningId"
        :focus="focus"
        @open="decision.open"
        @rows="openRows"
        @reopen="reopen"
        @changed="refreshAfter"
        @selection="checked = $event"
        @reset="resetFilters"
      />
    </ListPage>
    <DecisionDialog
      v-if="decision.current.value"
      :mode="decision.mode.value"
      :candidate="decision.current.value.candidate"
      :context="decision.current.value.context"
      :preset-target="decision.current.value.target"
      @close="decision.close"
      @done="decision.done"
    />
    <CandidateRowsDrawer
      :candidate="drawer"
      :industries="drawerIndustries"
      @close="drawer = null"
      @changed="refreshAfter(drawer ? [drawer.id] : [])"
    />
  </div>
</template>

<style scoped>
.candidates__summary {
  margin: 0;
  padding: 10px 16px;
  border: 1px solid var(--zt-border);
  border-left: 3px solid var(--zt-blue-600);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
  box-shadow: var(--zt-shadow);
  color: var(--zt-ink-900);
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
}

.candidates__min {
  width: 120px;
}
</style>
