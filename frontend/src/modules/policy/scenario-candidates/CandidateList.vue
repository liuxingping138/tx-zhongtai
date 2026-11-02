<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { listCandidates, type CandidateItem, type CandidateQuery, type CandidateSummary } from '@/api/scenarioCandidates'
import AuditLogButton from '@/components/AuditLogButton.vue'
import FilterBar from '@/components/FilterBar.vue'
import FilterKeyword from '@/components/FilterKeyword.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import ListEmpty from '@/components/ListEmpty.vue'
import ListPage from '@/components/ListPage.vue'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { hasActiveFilters, useListLoader } from '@/composables/useListLoader'
import { useListQuery } from '@/composables/useListQuery'
import { reviewQuery } from '../shared/reviewQuery'
import CandidateRowsDrawer from './CandidateRowsDrawer.vue'
import { PENDING, RESOURCE, STATUSES, decisionText, splitPath, summaryText } from './candidates'

const query = reactive({
  status: PENDING,
  keyword: [] as string[],
  industry_l1: [] as string[],
  level_label: [] as string[],
  similar_level: [] as string[],
  min_policies: '',
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions('/policy/scenario-candidates')
const summary = ref<CandidateSummary | null>(null)
const listQuery = useListQuery(query, (): Promise<void> => load())

async function fetchPage(params: Record<string, unknown>) {
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
// 页签不算筛选：待审为空时写「暂无记录」，不给「清除筛选」
const filtered = computed(() => hasActiveFilters({ ...listQuery.applied, status: '' }))
const counts = computed(() => summary.value?.by_status ?? {})

function switchStatus(value: string | number | boolean | undefined) {
  listQuery.replaceApplied('status', String(value))
  void load()
}

/** 「重置」只清筛选条件，留在当前页签。 */
function resetFilters() {
  Object.assign(query, { keyword: [], industry_l1: [], level_label: [], similar_level: [], min_policies: '' })
  listQuery.search()
}

function reviewRoute(row: CandidateItem, index: number) {
  const position = (query.page - 1) * query.page_size + index
  return { name: 'policy-scenario-candidate-review', params: { id: row.id }, query: reviewQuery(listQuery.applied, position, query.page_size) }
}

const drawer = ref<CandidateItem | null>(null)

onMounted(() => {
  void load()
  void filters.load()
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
      @retry="load"
      @update:page="query.page = $event"
      @update:page-size="query.page_size = $event"
      @change="load"
    >
      <template #summary>
        <p class="candidates__summary">
          {{ summaryText(summary) }}
          <span class="candidates__note">一行是一个场景：同一个说法被多少条政策提出都在这一行，决定一次对它们一起生效，以后再出现自动按决定处理。</span>
        </p>
      </template>
      <template #actions>
        <el-radio-group
          :model-value="listQuery.applied.status"
          aria-label="按状态看"
          @update:model-value="switchStatus"
        >
          <el-radio-button
            v-for="status in STATUSES"
            :key="status"
            :value="status"
          >
            {{ status }} {{ (counts[status] ?? 0).toLocaleString() }}
          </el-radio-button>
        </el-radio-group>
        <AuditLogButton :module="RESOURCE" />
      </template>
      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
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
          <el-form-item label="新增级别">
            <FilterSelect
              v-model="query.level_label"
              v-bind="filters.bind('level_label')"
              size="short"
            />
          </el-form-item>
          <template #advanced>
            <el-form-item label="码表相似">
              <FilterSelect
                v-model="query.similar_level"
                v-bind="filters.bind('similar_level')"
                size="short"
              />
            </el-form-item>
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
      <el-table
        v-loading="loading"
        class="data-table"
        :data="items"
      >
        <template #empty>
          <ListEmpty
            :loading="loading"
            :filtered="filtered"
            @reset="resetFilters"
          />
        </template>
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
          label="上级场景"
          min-width="150"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            {{ row.kind === '新场景' ? (splitPath(row).known.join(' › ') || '—（新的一级场景）') : `挂到 ${row.industry}` }}
          </template>
        </el-table-column>
        <el-table-column
          prop="level_label"
          label="新增级别"
          width="96"
        />
        <el-table-column
          label="一级行业"
          min-width="150"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            {{ row.main_industry }}{{ row.industry_count > 1 ? ` 等 ${row.industry_count} 个` : '' }}
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
          label="解读行数"
          width="96"
          align="right"
        >
          <template #default="{ row }">
            {{ row.row_count.toLocaleString() }}
          </template>
        </el-table-column>
        <template v-if="pending">
          <el-table-column
            label="码表相似"
            width="96"
          >
            <template #default="{ row }">
              <el-tag
                v-if="row.similar_level === '高' || row.similar_level === '中'"
                :type="row.similar_level === '高' ? 'warning' : 'info'"
                effect="plain"
              >
                {{ row.similar_level }}
              </el-tag>
              <span
                v-else
                class="candidates__none"
              >{{ row.similar_level || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="最像的已有场景"
            min-width="200"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              {{ row.similar_name || '—' }}
            </template>
          </el-table-column>
        </template>
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
          prop="last_seen_at"
          label="最近出现"
          width="170"
        />
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
  color: var(--zt-ink-400);
}

.candidates__min {
  width: 120px;
}
</style>
