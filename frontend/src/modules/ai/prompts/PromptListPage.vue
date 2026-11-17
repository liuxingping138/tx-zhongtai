<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Search } from '@element-plus/icons-vue'

import { listPrompts, type PromptTemplate, type TemplateCategory } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import { ALL_CATEGORIES, defaultCategory, inCategory } from '../shared/categories'
import { shortTime } from './sampleView'
import { releaseState, sampleState, type ReleaseKind } from './templateStatus'
import { useTaskFit } from './useTaskFit'
import '../shared/ai.css'

/**
 * 模板列表：一眼看出每个模板走到哪一步。管理员按「有改动未上线」找要审核上线的，业务人员找自己在调的。
 */
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const templates = ref<PromptTemplate[]>([])
const categories = ref<TemplateCategory[]>([])
const loading = ref(false)
const loadError = ref('')
const category = ref(typeof route.query.category === 'string' ? route.query.category : ALL_CATEGORIES)
const status = ref<ReleaseKind | ''>((typeof route.query.status === 'string' && ['changed', 'online', 'offline'].includes(route.query.status) ? route.query.status : '') as ReleaseKind | '')
const keyword = ref(typeof route.query.q === 'string' ? route.query.q : '')
// 「定时任务在用」做成和旁边按钮组一样的按钮，只有一个选项，选中即只看在用的。
const scheduledFilter = ref<string[]>(route.query.sched === '1' ? ['scheduled'] : [])
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
function shortModel(name: string): string {
  return name ? name.replace(/^(字节|百度)\s*[-－]\s*/, '') : '未选'
}

function outputPreview(fields: string[]): string {
  if (!fields.length) return ''
  return fields.length <= 2 ? fields.join('、') : `${fields.slice(0, 2).join('、')}…`
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
        </div>
        <div class="prompt-list__actions">
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
      <el-table
        v-else
        :data="visible"
        row-key="id"
        class="data-table prompt-list__table"
        :class="{ 'is-refreshing': loading }"
        :empty-text="emptyText"
        height="100%"
        @row-click="open"
      >
        <el-table-column
          label="模板名称"
          min-width="148"
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
          width="62"
        >
          <template #default="{ row }">
            <span class="prompt-list__cat">{{ row.category_name }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-if="showTasks"
          label="定时任务"
          min-width="110"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <div
              v-if="tasksOf(row).length"
              class="prompt-list__task-pills"
            >
              <span
                v-for="taskName in tasksOf(row)"
                :key="taskName"
                class="prompt-list__task-pill"
              >{{ taskName }}</span>
            </div>
            <span
              v-else
              class="prompt-list__none"
            >—</span>
          </template>
        </el-table-column>
        <el-table-column
          label="上线状态"
          min-width="154"
        >
          <template #default="{ row }">
            <!-- 有改动没上线：一行写完，改了什么放悬停提示，「看改动」直接打开逐行对比。 -->
            <span
              v-if="row.release?.unreleased_changes.length"
              class="prompt-list__state is-changed"
              :title="`草稿改了${row.release.unreleased_changes.join('、')}，还没上线`"
            >第 {{ row.release.release_no }} 版 · 有改动<router-link
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
          min-width="134"
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
          label="输出字段"
          min-width="144"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span
              v-if="row.fields.length"
              class="prompt-list__fields"
              :title="row.fields.join('、')"
            ><strong>{{ row.fields.length }} 个</strong><span>{{ outputPreview(row.fields) }}</span></span>
            <span
              v-else
              class="prompt-list__none"
            >自由文本输出</span>
          </template>
        </el-table-column>
        <el-table-column
          label="模型"
          min-width="112"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span
              class="prompt-list__model"
              :title="row.model_name"
            >{{ shortModel(row.model_name) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="创建人"
          width="88"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span class="prompt-list__creator">{{ row.created_by_name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="最近更新"
          width="88"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span
              class="prompt-list__time"
              :title="`${row.updated_by_name} · ${row.updated_at}`"
            >{{ shortTime(row.updated_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          width="54"
          align="right"
        >
          <template #default>
            <span class="prompt-list__open">打开 →</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </section>
</template>

<style scoped src="./prompt-list.css"></style>
