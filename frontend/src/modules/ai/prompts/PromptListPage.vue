<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Search } from '@element-plus/icons-vue'

import { listPrompts, type PromptTemplate, type TemplateCategory } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { ALL_CATEGORIES, defaultCategory, inCategory } from '../shared/categories'
import { shortTime } from './sampleView'
import { releaseState, sampleState, type ReleaseKind } from './templateStatus'
import { useTaskFit } from './useTaskFit'
import '../shared/ai.css'

/**
 * 模板列表：一眼看出每个模板走到哪一步。管理员按「有改动未上线」找要审核上线的，业务人员找自己在调的。
 */
const router = useRouter()
const auth = useAuthStore()
const templates = ref<PromptTemplate[]>([])
const categories = ref<TemplateCategory[]>([])
const loading = ref(false)
const loadError = ref('')
const category = ref(ALL_CATEGORIES)
const status = ref<ReleaseKind | ''>('')
const keyword = ref('')
// 「定时任务在用」做成和旁边按钮组一样的按钮，只有一个选项，选中即只看在用的。
const scheduledFilter = ref<string[]>([])
const onlyScheduled = computed(() => scheduledFilter.value.length > 0)
// 哪些模板正被定时任务用：只有政策类会被选用；看不到政策打标约定（没权限）时这一列和筛选都不显示。
const taskFit = useTaskFit(reactive({ category: 'policy', content: '', output_fields: '', code_table: '' }))
const showTasks = computed(() => taskFit.usedBy('') !== null)
const tasksOf = (item: PromptTemplate) => (item.category === 'policy' ? taskFit.usedBy(item.id) ?? [] : [])
const scheduled = computed(() => inScope.value.filter(item => tasksOf(item).length).length)
const canCreate = computed(() => auth.canFull('ai.prompts') && categories.value.some(item => item.editable))

const STATUS_OPTIONS: { value: ReleaseKind | ''; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'changed', label: '有改动' },
  { value: 'online', label: '已上线' },
  { value: 'offline', label: '未上线' },
]
const inScope = computed(() => templates.value.filter(item => inCategory(item.category, category.value)))
const counts = computed(() => {
  const result: Record<ReleaseKind | '', number> = { '': inScope.value.length, changed: 0, online: 0, offline: 0 }
  for (const item of inScope.value) result[releaseState(item).kind] += 1
  return result
})
const visible = computed(() => {
  const needle = keyword.value.trim()
  return inScope.value.filter(item => (!status.value || releaseState(item).kind === status.value) && (!needle || item.title.includes(needle))
    && (!onlyScheduled.value || tasksOf(item).length > 0))
})
const emptyText = computed(() => {
  if (loading.value) return ' '
  if (!categories.value.length) return '还没有分配可查看的模板类型，请联系管理员'
  if (!templates.value.length) return canCreate.value ? '还没有模板，点「新建模板」写第一个' : '还没有模板'
  return '没有符合条件的模板'
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

/** 「字节-DeepSeek-V3.2」→「DeepSeek-V3.2」：厂商前缀每行都一样，省下宽度给名称；悬停看全名。 */
/** 类型用颜色区分，一眼分出政策、客户、招投标；颜色只区分取值，不表示好坏。 */
const CATEGORY_TAGS: Record<string, 'primary' | 'success' | 'warning'> = { policy: 'primary', customer: 'success', tender: 'warning' }

function shortModel(name: string): string {
  return name ? name.replace(/^(字节|百度)\s*[-－]\s*/, '') : '未选'
}

function open(template: PromptTemplate): void {
  void router.push({ name: 'ai-prompt-edit', params: { id: template.id } })
}

function create(): void {
  const editable = categories.value.filter(item => item.editable)
  void router.push({ name: 'ai-prompt-edit', params: { id: 'new' }, query: { category: defaultCategory(editable, category.value) } })
}
</script>

<template>
  <section class="prompt-list">
    <h1 class="ai-sr-only">
      提示词模板
    </h1>
    <div class="ai-panel prompt-list__panel">
      <div class="prompt-list__toolbar">
        <el-input
          v-model="keyword"
          class="prompt-list__search"
          :prefix-icon="Search"
          clearable
          placeholder="按名称查找"
          aria-label="按名称查找模板"
        />
        <el-radio-group
          v-if="categories.length > 1"
          v-model="category"
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
          class="prompt-list__label"
          aria-hidden="true"
        >上线状态</span>
        <el-radio-group
          v-model="status"
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
          aria-label="只看定时任务在用的模板"
        >
          <el-checkbox-button value="scheduled">
            定时任务在用<span class="prompt-list__count">{{ scheduled }}</span>
          </el-checkbox-button>
        </el-checkbox-group>
        <span class="prompt-list__spacer" />
        <el-button
          v-if="canCreate"
          type="primary"
          :icon="Plus"
          @click="create"
        >
          新建模板
        </el-button>
      </div>
      <el-alert
        v-if="loadError"
        :title="loadError"
        type="error"
        :closable="false"
        show-icon
      />
      <el-table
        v-loading="loading"
        :data="visible"
        row-key="id"
        class="data-table prompt-list__table"
        :empty-text="emptyText"
        height="100%"
        @row-click="open"
      >
        <el-table-column
          label="模板名称"
          min-width="192"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <router-link
              class="prompt-list__name"
              :to="{ name: 'ai-prompt-edit', params: { id: row.id } }"
              @click.stop
            >
              {{ row.title }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column
          label="类型"
          width="80"
        >
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="CATEGORY_TAGS[row.category] ?? 'info'"
              disable-transitions
            >
              {{ row.category_name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          v-if="showTasks"
          label="定时任务"
          min-width="116"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span
              v-if="tasksOf(row).length"
              class="prompt-list__task"
            >{{ tasksOf(row).join('、') }}</span>
            <span
              v-else
              class="prompt-list__none"
            >不在用</span>
          </template>
        </el-table-column>
        <el-table-column
          label="上线状态"
          min-width="176"
        >
          <template #default="{ row }">
            <!-- 有改动没上线：一行写完，改了什么放悬停提示，「看改动」直接打开逐行对比。 -->
            <span
              v-if="row.release?.unreleased_changes.length"
              class="prompt-list__state is-changed"
              :title="`草稿改了${row.release.unreleased_changes.join('、')}，还没上线`"
            >第 {{ row.release.release_no }} 版，有改动<router-link
              class="prompt-list__diff"
              :to="{ name: 'ai-prompt-edit', params: { id: row.id }, query: { review: '1' } }"
              @click.stop
            >看改动</router-link></span>
            <span
              v-else
              class="prompt-list__state"
              :class="`is-${releaseState(row).kind}`"
              :title="releaseState(row).detail"
            >{{ releaseState(row).text }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="样本试跑"
          min-width="168"
        >
          <template #default="{ row }">
            <span
              class="prompt-list__sample"
              :class="`is-${sampleState(row).kind}`"
              :title="sampleState(row).detail"
            >{{ sampleState(row).text }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="字段数"
          width="72"
          align="right"
        >
          <template #default="{ row }">
            {{ row.fields.length || '—' }}
          </template>
        </el-table-column>
        <el-table-column
          label="模型"
          min-width="150"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span :title="row.model_name">{{ shortModel(row.model_name) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="updated_by_name"
          label="更新人"
          width="96"
          show-overflow-tooltip
        />
        <el-table-column
          label="更新时间"
          width="108"
        >
          <template #default="{ row }">
            <span
              class="prompt-list__time"
              :title="row.updated_at"
            >{{ shortTime(row.updated_at) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </section>
</template>

<style scoped>
.prompt-list { height: calc(100dvh - var(--workspace-header-height) - 48px); min-height: 480px; }
.prompt-list__panel { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.prompt-list__toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 12px; padding: 12px 16px; border-bottom: 1px solid var(--zt-border); }
.prompt-list__toolbar .el-button { margin: 0; }
.prompt-list__search { width: 180px; }
/* 两组切换前的小标签；和后面的按钮组挨着，组与组之间留开。 */
.prompt-list__label { margin: 0 -4px 0 8px; color: var(--zt-ink-500); font-size: 13px; }
.prompt-list__spacer { flex: 1; }
.prompt-list__count { margin-left: 6px; color: var(--zt-ink-500); font-size: 12px; font-variant-numeric: tabular-nums; }
.prompt-list :deep(.is-active) .prompt-list__count, .prompt-list :deep(.is-checked) .prompt-list__count { color: inherit; opacity: .8; }
.prompt-list__table { flex: 1; min-height: 0; }
.prompt-list__table :deep(.el-table__row) { cursor: pointer; }
/* 和业务列表一样左右各 12px：九列在常见宽度下放得下，不用横向滚动 */
.prompt-list__table :deep(.cell) { padding: 0 12px; }
/* 每格只占一行，所有行一样高：放不下的截断，悬停看全文。 */
.prompt-list__table :deep(.cell) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.prompt-list__name { color: var(--zt-ink-900); font-weight: 600; text-decoration: none; }
.prompt-list__name:hover { color: var(--zt-blue-600); }
.prompt-list__state { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; white-space: nowrap; }
.prompt-list__state::before { content: ""; flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--zt-muted-mark); }
.prompt-list__state.is-online::before { background: var(--zt-success); }
.prompt-list__state.is-changed { color: var(--zt-warning-text); }
.prompt-list__state.is-changed::before { background: var(--zt-warning); }
.prompt-list__diff { margin-left: 2px; color: var(--zt-blue-600); text-decoration: none; }
.prompt-list__diff:hover { text-decoration: underline; }
.prompt-list__sample { color: var(--zt-ink-500); font-size: 13px; }
.prompt-list__sample.is-passed { color: var(--zt-success-text); }
.prompt-list__sample.is-failed, .prompt-list__sample.is-stale { color: var(--zt-warning-text); }
.prompt-list__sample.is-running { color: var(--zt-blue-600); }
.prompt-list__task { color: var(--zt-ink-700); font-size: 13px; }
.prompt-list__time { font-variant-numeric: tabular-nums; }
.prompt-list__none { color: var(--zt-ink-400); font-size: 13px; }
</style>
