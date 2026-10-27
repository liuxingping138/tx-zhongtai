<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Search } from '@element-plus/icons-vue'

import { listPrompts, type PromptTemplate, type TemplateCategory } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { ALL_CATEGORIES, defaultCategory, inCategory } from '../shared/categories'
import { releaseState, sampleState, type ReleaseKind } from './templateStatus'
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
const canCreate = computed(() => auth.canFull('ai.prompts') && categories.value.some(item => item.editable))

const STATUS_OPTIONS: { value: ReleaseKind | ''; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'changed', label: '有改动未上线' },
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
  return inScope.value.filter(item => (!status.value || releaseState(item).kind === status.value) && (!needle || item.title.includes(needle)))
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
onMounted(load)

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
        <span
          v-if="categories.length > 1"
          class="prompt-list__label"
          aria-hidden="true"
        >类型</span>
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
        <el-input
          v-model="keyword"
          class="prompt-list__search"
          :prefix-icon="Search"
          clearable
          placeholder="按名称查找"
          aria-label="按名称查找模板"
        />
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
        class="prompt-list__table"
        :empty-text="emptyText"
        height="100%"
        @row-click="open"
      >
        <el-table-column
          label="模板名称"
          min-width="190"
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
          prop="category_name"
          label="类型"
          width="70"
        />
        <el-table-column
          label="上线状态"
          min-width="200"
        >
          <template #default="{ row }">
            <span
              class="prompt-list__state"
              :class="`is-${releaseState(row).kind}`"
              :title="releaseState(row).detail"
            >{{ releaseState(row).text }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="样本试跑"
          min-width="180"
          show-overflow-tooltip
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
          width="80"
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
            {{ row.model_name || '未选' }}
          </template>
        </el-table-column>
        <el-table-column
          prop="updated_by_name"
          label="更新人"
          width="100"
          show-overflow-tooltip
        />
        <el-table-column
          prop="updated_at"
          label="更新时间"
          width="170"
        />
      </el-table>
    </div>
  </section>
</template>

<style scoped>
.prompt-list { height: calc(100dvh - var(--workspace-header-height) - 48px); min-height: 480px; }
.prompt-list__panel { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.prompt-list__toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 12px; padding: 12px 16px; border-bottom: 1px solid var(--zt-border); }
.prompt-list__toolbar .el-button { margin: 0; }
.prompt-list__search { width: 168px; }
/* 两组切换前的小标签；和后面的按钮组挨着，组与组之间留开。 */
.prompt-list__label { margin-right: -4px; color: var(--zt-ink-500); font-size: 13px; }
.prompt-list__label + .el-radio-group + .prompt-list__label { margin-left: 8px; }
.prompt-list__spacer { flex: 1; }
.prompt-list__count { margin-left: 6px; color: var(--zt-ink-500); font-size: 12px; font-variant-numeric: tabular-nums; }
.prompt-list :deep(.is-active) .prompt-list__count { color: inherit; opacity: .8; }
.prompt-list__table { flex: 1; min-height: 0; }
.prompt-list__table :deep(.el-table__row) { cursor: pointer; }
.prompt-list__name { color: var(--zt-ink-900); font-weight: 600; text-decoration: none; }
.prompt-list__name:hover { color: var(--zt-blue-600); }
.prompt-list__state, .prompt-list__sample { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; white-space: nowrap; }
.prompt-list__state::before { content: ""; flex: none; width: 7px; height: 7px; border-radius: 50%; background: #b3bdca; }
.prompt-list__state.is-online::before { background: #3d8c6e; }
.prompt-list__state.is-changed { color: #9a6418; }
.prompt-list__state.is-changed::before { background: #c4842a; }
.prompt-list__sample { color: var(--zt-ink-500); }
.prompt-list__sample.is-passed { color: #2f7558; }
.prompt-list__sample.is-failed, .prompt-list__sample.is-stale { color: #9a6418; }
.prompt-list__sample.is-running { color: var(--zt-blue-600); }
</style>
