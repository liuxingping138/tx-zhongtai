<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Search } from '@element-plus/icons-vue'

import { listPrompts, type PromptTemplate, type TemplateCategory } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import { ALL_CATEGORIES, defaultCategory, inCategory } from '../shared/categories'
import PromptListTable, { type ListSortKey } from './PromptListTable.vue'
import ReleaseDrawer from './ReleaseDrawer.vue'
import { fitSummary } from './taskFit'
import { releaseState, type ReleaseKind } from './templateStatus'
import { useTaskFit } from './useTaskFit'
import '../shared/ai.css'

/**
 * 提示词模板列表：10 列完整信息零溢出呈现。
 * 管理员按「有改动」快速定位待审核上线的模板，业务人员按分类/搜索找自己在调的模板。
 */
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const templates = ref<PromptTemplate[]>([])
const categories = ref<TemplateCategory[]>([])
const loading = ref(false)
const loadError = ref('')
const category = ref(typeof route.query.category === 'string' ? route.query.category : ALL_CATEGORIES)
const status = ref<ReleaseKind | ''>((
  typeof route.query.status === 'string' && ['changed', 'online', 'offline'].includes(route.query.status)
    ? route.query.status
    : ''
) as ReleaseKind | '')
const keyword = ref(typeof route.query.q === 'string' ? route.query.q : '')
const scheduledFilter = ref<string[]>(route.query.sched === '1' ? ['scheduled'] : [])
const sortKey = ref<ListSortKey>('updated_at')
const sortAsc = ref(false)

watch([category, status, keyword, scheduledFilter], ([cat, st, q, sched]) => {
  const nextQuery = {
    ...route.query,
    category: cat !== ALL_CATEGORIES ? cat : undefined,
    status: st || undefined,
    q: q.trim() ? q : undefined,
    sched: sched.length ? '1' : undefined,
  }
  void router.replace({ query: nextQuery })
})

const onlyScheduled = computed(() => scheduledFilter.value.length > 0)
const hasActiveFilters = computed(() =>
  Boolean(keyword.value.trim() || status.value || category.value !== ALL_CATEGORIES || onlyScheduled.value))

const fitDraft = reactive({ category: 'policy', content: '', output_fields: '', code_table: '' })
const taskFit = useTaskFit(fitDraft)
const showTasks = computed(() => taskFit.usedBy('') !== null)
const tasksOf = (item: PromptTemplate) => (item.category === 'policy' ? taskFit.usedBy(item.id) ?? [] : [])
const canCreate = computed(() => auth.canFull('ai.prompts') && categories.value.some(item => item.editable))
const canRelease = computed(() => auth.canFull('ai.releases'))

const reviewId = ref('')
const reviewTarget = computed(() => templates.value.find(item => item.id === reviewId.value) ?? null)
const reviewOpen = computed({
  get: () => Boolean(reviewTarget.value),
  set: (val: boolean) => { if (!val) reviewId.value = '' },
})
const reviewFit = computed(() =>
  (reviewTarget.value?.category === 'policy' ? fitSummary(taskFit.results.value) : null))
const reviewUsedBy = computed(() =>
  (reviewTarget.value?.category === 'policy' ? taskFit.usedBy(reviewTarget.value.id) : []))

const STATUS_OPTIONS: { value: ReleaseKind | ''; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'online', label: '已上线' },
  { value: 'offline', label: '未上线' },
  { value: 'changed', label: '草稿有改动' },
]

const RELEASE_RANK: Record<ReleaseKind, number> = { changed: 3, online: 2, offline: 1 }

const inScope = computed(() => templates.value.filter(item => inCategory(item.category, category.value)))
const scheduled = computed(() => inScope.value.filter(item => tasksOf(item).length).length)
const counts = computed(() => {
  const result: Record<ReleaseKind | '', number> = { '': inScope.value.length, changed: 0, online: 0, offline: 0 }
  for (const item of inScope.value) {
    if (item.release) {
      result.online += 1
      if (item.release.unreleased_changes.length) result.changed += 1
    } else {
      result.offline += 1
    }
  }
  return result
})

function matchesStatus(item: PromptTemplate, wanted: ReleaseKind | ''): boolean {
  if (!wanted) return true
  if (wanted === 'online') return Boolean(item.release)
  if (wanted === 'offline') return !item.release
  return Boolean(item.release?.unreleased_changes.length)
}

function compareRows(a: PromptTemplate, b: PromptTemplate): number {
  const factor = sortAsc.value ? 1 : -1
  if (sortKey.value === 'title') return a.title.localeCompare(b.title, 'zh-CN') * factor
  if (sortKey.value === 'fields') return (a.fields.length - b.fields.length) * factor || b.updated_at.localeCompare(a.updated_at)
  if (sortKey.value === 'release') {
    const diff = RELEASE_RANK[releaseState(a).kind] - RELEASE_RANK[releaseState(b).kind]
    return diff ? diff * factor : b.updated_at.localeCompare(a.updated_at)
  }
  return a.updated_at.localeCompare(b.updated_at) * factor
}

const visible = computed(() => {
  const needle = keyword.value.trim().toLowerCase()
  const filtered = inScope.value.filter(item =>
    matchesStatus(item, status.value)
    && (!needle || item.title.toLowerCase().includes(needle))
    && (!onlyScheduled.value || tasksOf(item).length > 0))
  return [...filtered].sort(compareRows)
})

const emptyText = computed(() => {
  if (!categories.value.length) return '还没有分配可查看的模板类型，请联系管理员'
  if (!templates.value.length) return canCreate.value ? '还没有模板，点右上角「新建模板」编写第一个' : '还没有模板'
  return '没有符合当前筛选条件的提示词模板'
})

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listPrompts()
    templates.value = data.items
    categories.value = data.categories
    loadError.value = ''
  } catch (error) {
    loadError.value = errorMessage(error, '模板加载失败，请刷新重试')
  } finally {
    loading.value = false
  }
}
onMounted(() => { void load(); void taskFit.load() })

function toggleSort(key: ListSortKey): void {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = key === 'title'
  }
}

function resetFilters(): void {
  keyword.value = ''
  status.value = ''
  category.value = ALL_CATEGORIES
  scheduledFilter.value = []
}

function open(template: PromptTemplate): void {
  void router.push({ name: 'ai-prompt-edit', params: { id: template.id } })
}

function openReview(template: PromptTemplate): void {
  Object.assign(fitDraft, {
    content: template.content,
    output_fields: template.output_fields,
    code_table: template.code_table || template.code_name,
  })
  reviewId.value = template.id
}

function onReviewed(updated: PromptTemplate): void {
  templates.value = templates.value.map(item => (item.id === updated.id ? updated : item))
}

function create(): void {
  const editable = categories.value.filter(item => item.editable)
  void router.push({ name: 'ai-prompt-edit', params: { id: 'new' }, query: { category: defaultCategory(editable, category.value) } })
}
</script>

<template>
  <section
    class="prompt-list"
    aria-label="提示词模板列表"
  >
    <h1 class="ai-sr-only">
      提示词模板
    </h1>

    <div class="ai-panel prompt-list__panel">
      <div class="prompt-list__toolbar">
        <div class="prompt-list__filters">
          <el-input
            v-model="keyword"
            class="prompt-list__search"
            :prefix-icon="Search"
            clearable
            placeholder="搜索模板名称…"
            aria-label="按名称查找模板"
          />
          <el-radio-group
            v-if="categories.length > 1"
            v-model="category"
            class="ai-seg"
            aria-label="按模板类型查看"
          >
            <el-radio-button :value="ALL_CATEGORIES">
              全部
            </el-radio-button>
            <el-radio-button
              v-for="item in categories"
              :key="item.code"
              :value="item.code"
            >
              {{ item.name }}
            </el-radio-button>
          </el-radio-group>
          <span
            v-if="categories.length > 1"
            class="prompt-list__sep"
            aria-hidden="true"
          />
          <el-radio-group
            v-model="status"
            class="ai-seg"
            aria-label="按上线状态查看"
          >
            <el-radio-button
              v-for="item in STATUS_OPTIONS"
              :key="item.value"
              :value="item.value"
            >
              {{ item.label }}<span class="prompt-list__count">{{ counts[item.value] }}</span>
            </el-radio-button>
          </el-radio-group>
          <el-checkbox-group
            v-if="showTasks"
            v-model="scheduledFilter"
            class="prompt-list__toggle"
            aria-label="只看定时任务在用的模板"
          >
            <el-checkbox-button value="scheduled">
              定时任务在用<span class="prompt-list__count">{{ scheduled }}</span>
            </el-checkbox-button>
          </el-checkbox-group>
        </div>

        <div class="prompt-list__actions">
          <el-button
            v-if="canCreate"
            type="primary"
            :icon="Plus"
            @click="create"
          >
            新建模板
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="loadError"
        :title="loadError"
        type="error"
        :closable="false"
        show-icon
      >
        <el-button
          size="small"
          type="danger"
          plain
          @click="load()"
        >
          重试
        </el-button>
      </el-alert>

      <TableSkeleton
        v-if="loading && templates.length === 0"
        :columns="showTasks ? 10 : 9"
        :has-actions="false"
      />

      <div
        v-else-if="visible.length === 0"
        class="prompt-list__empty"
      >
        <p>{{ emptyText }}</p>
        <el-button
          v-if="hasActiveFilters && templates.length > 0"
          size="small"
          plain
          @click="resetFilters"
        >
          重置筛选条件
        </el-button>
      </div>

      <PromptListTable
        v-else
        :rows="visible"
        :show-tasks="showTasks"
        :can-release="canRelease"
        :loading="loading"
        :sort-key="sortKey"
        :sort-asc="sortAsc"
        :tasks-of="tasksOf"
        @open="open"
        @review="openReview"
        @sort="toggleSort"
      />
    </div>

    <ReleaseDrawer
      v-if="reviewTarget"
      v-model="reviewOpen"
      from-list
      :template="reviewTarget"
      :can-release="canRelease && Boolean(reviewTarget.editable)"
      :dirty="false"
      :fit="reviewFit"
      :used-by="reviewUsedBy"
      @changed="onReviewed"
      @edit="open(reviewTarget)"
    />
  </section>
</template>

<style src="./prompt-list.css"></style>
