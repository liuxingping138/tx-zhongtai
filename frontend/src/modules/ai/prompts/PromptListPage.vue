<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
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
    <header class="ai-panel prompt-list__hero">
      <div class="prompt-list__hero-main">
        <h1>提示词模板</h1>
        <p>统一编写、测试与版本发布各业务场景的 AI 提示词模板；选中一行即可进入工作台调优。</p>
      </div>
      <div class="prompt-list__kpis">
        <div class="prompt-list__kpi">
          <span>全部模板</span>
          <strong>{{ inScope.length }}</strong>
        </div>
        <div class="prompt-list__kpi is-online">
          <span>已上线</span>
          <strong>{{ counts.online }}</strong>
        </div>
        <div class="prompt-list__kpi is-changed">
          <span>有改动待发</span>
          <strong>{{ counts.changed }}</strong>
        </div>
        <div
          v-if="showTasks"
          class="prompt-list__kpi is-task"
        >
          <span>定时任务在用</span>
          <strong>{{ scheduled }}</strong>
        </div>
      </div>
      <el-button
        v-if="canCreate"
        type="primary"
        :icon="Plus"
        @click="create"
      >
        新建模板
      </el-button>
    </header>
    <div class="ai-panel prompt-list__panel">
      <div class="prompt-list__toolbar">
        <el-input
          v-model="keyword"
          class="prompt-list__search"
          :prefix-icon="Search"
          clearable
          placeholder="按模板名称搜索…"
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
      <el-alert
        v-if="loadError"
        :title="loadError"
        type="error"
        :closable="false"
        show-icon
      />
      <TableSkeleton
        v-if="loading && templates.length === 0"
        :columns="showTasks ? 9 : 8"
        :has-actions="true"
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
          min-width="150"
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
          width="74"
        >
          <template #default="{ row }">
            <el-tag
              size="small"
              round
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
          min-width="120"
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
          min-width="172"
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
          label="字段"
          width="58"
          align="center"
        >
          <template #default="{ row }">
            <span
              v-if="row.fields.length"
              class="prompt-list__field-badge"
            >{{ row.fields.length }}</span>
            <span
              v-else
              class="prompt-list__none"
            >—</span>
          </template>
        </el-table-column>
        <el-table-column
          label="模型"
          min-width="126"
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
          label="最近更新"
          width="116"
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
          label="操作"
          width="78"
          align="right"
        >
          <template #default="{ row }">
            <div
              class="row-actions"
              @click.stop
            >
              <router-link
                class="row-action row-action--primary"
                :to="{ name: 'ai-prompt-edit', params: { id: row.id } }"
              >
                调试
              </router-link>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </section>
</template>

<style scoped src="./prompt-list.css"></style>
