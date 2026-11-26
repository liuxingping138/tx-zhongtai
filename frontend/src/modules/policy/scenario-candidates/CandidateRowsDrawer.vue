<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import type { ScenarioPath } from '@/api/codebook'
import { errorMessage } from '@/api/errors'
import { changeRowScenario, listCandidateRows, type CandidateDetail, type CandidateItem, type CandidateRow } from '@/api/scenarioCandidates'
import ScenarioPicker from '@/components/ScenarioPicker.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import { pathText } from './candidates'

/**
 * 提出这个场景的来源政策（解读行），可以按行业看、按政策名称搜，分页。上万条也只是翻页。
 * 个别政策该归到别的场景时在这里逐行改，不影响这个场景的决定。
 */
const props = defineProps<{ candidate: CandidateItem | null; industries?: CandidateDetail['industries'] }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const auth = useAuthStore()
const canReadInterpretations = computed(() => auth.canRead('policy.interpretations'))
const canEditRows = computed(() => auth.canFull('policy.interpretations') && auth.canRead('codebook.scenarios'))

const PAGE_SIZE = 20
const rows = ref<CandidateRow[]>([])
const total = ref(0)
const page = ref(1)
const keyword = ref('')
/** 选中的行业（详情 industries 的 path），空 = 全部 */
const industry = ref('')
const loading = ref(false)
const loadError = ref('')
const editing = ref<string | null>(null)
const picked = ref<ScenarioPath | null>(null)
const saving = ref(false)
let sequence = 0

async function load() {
  const id = props.candidate?.id
  if (!id) return
  const current = ++sequence
  loading.value = true
  loadError.value = ''
  try {
    const names = props.industries?.find(item => item.path === industry.value)?.names
    const result = await listCandidateRows(id, { keyword: keyword.value.trim() || undefined, industry: names, page: page.value, page_size: PAGE_SIZE })
    if (current !== sequence) return
    rows.value = result.items
    total.value = result.total
  } catch (error) {
    if (current === sequence) loadError.value = errorMessage(error, '来源政策没有加载出来')
  } finally {
    if (current === sequence) loading.value = false
  }
}

watch(() => props.candidate?.id, (id) => {
  rows.value = []
  page.value = 1
  keyword.value = ''
  industry.value = ''
  editing.value = null
  if (id) void load()
})

function search() {
  page.value = 1
  void load()
}

function startEdit(row: CandidateRow) {
  editing.value = row.id
  picked.value = null
}

async function save(row: CandidateRow) {
  const path = picked.value
  if (!path || saving.value) return
  saving.value = true
  try {
    const out = await changeRowScenario(row.id, {
      version: row.version,
      industry_l1: path.industry_l1,
      industry_l2: path.industry_l2,
      industry_l3: path.industry_l3,
      scenario_l1_name: path.scenario_l1_name,
      scenario_l2_name: path.scenario_l2_name,
      scenario_l3_name: path.scenario_l3_name,
    })
    ElMessage.success(`已改，这一行现在是「${out.scenario_state}」`)
    editing.value = null
    emit('changed')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '没改成，请重试'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-drawer
    :model-value="Boolean(candidate)"
    :title="candidate ? `来源政策 · ${candidate.name}（${candidate.policy_count.toLocaleString()} 条政策，${candidate.row_count.toLocaleString()} 行解读）` : ''"
    size="min(960px, 94vw)"
    @close="emit('close')"
  >
    <div class="rows__toolbar">
      <el-select
        v-if="(industries?.length ?? 0) > 1"
        v-model="industry"
        class="rows__industry"
        clearable
        :placeholder="`全部行业（${industries?.length} 个）`"
        aria-label="按行业看"
        @change="search"
      >
        <el-option
          v-for="item in industries"
          :key="item.path"
          :value="item.path"
          :label="`${item.path} · ${item.rows.toLocaleString()} 行`"
        />
      </el-select>
      <el-input
        v-model="keyword"
        clearable
        placeholder="政策名称关键词"
        aria-label="政策名称关键词"
        @keyup.enter="search"
        @clear="search"
      />
      <el-button @click="search">
        查询
      </el-button>
    </div>
    <el-alert
      v-if="loadError"
      type="error"
      :title="loadError"
      :closable="false"
      show-icon
    >
      <template #default>
        <el-button
          link
          type="primary"
          style="margin-left: 8px; font-weight: 500;"
          @click="load"
        >
          重试
        </el-button>
      </template>
    </el-alert>
    <TableSkeleton
      v-if="loading && rows.length === 0"
      :columns="4"
      :has-actions="true"
    />
    <el-table
      v-else-if="!loadError || rows.length > 0"
      :data="rows"
      class="data-table"
      :class="{ 'is-refreshing': loading }"
    >
      <template #empty>
        <span>{{ keyword.trim() || industry ? '没有符合筛选条件的来源政策' : '暂无来源政策记录' }}</span>
      </template>
      <el-table-column
        label="政策"
        min-width="300"
      >
        <template #default="{ row }">
          <div class="rows__title">
            <RouterLink
              v-if="canReadInterpretations"
              :to="{ name: 'policy-interpretation-review', params: { id: row.id } }"
            >
              {{ row.policy_title }}
            </RouterLink>
            <span v-else>{{ row.policy_title }}</span>
            <span class="rows__sub">入库 {{ row.created_at.slice(0, 10) }}<template v-if="row.opportunity_type"> · {{ row.opportunity_type }}</template></span>
            <div
              v-if="canEditRows && editing === row.id"
              class="rows__edit"
            >
              <ScenarioPicker
                v-model="picked"
                :industry-l1="row.industry_l1"
                :placeholder="`在「${row.industry_l1}」下搜码表里的场景`"
              />
              <el-button
                :disabled="saving"
                @click="editing = null"
              >
                取消
              </el-button>
              <el-button
                type="primary"
                :disabled="!picked"
                :loading="saving"
                @click="save(row)"
              >
                改这一行
              </el-button>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        label="行业 · 场景"
        min-width="260"
      >
        <template #default="{ row }">
          <div
            class="rows__place"
            :title="`${row.industry}\n${pathText([row.scenario_l1_name, row.scenario_l2_name, row.scenario_l3_name])}`"
          >
            <span>{{ pathText(row.industry.split('/')) }}</span>
            <span class="rows__sub">{{ pathText([row.scenario_l1_name, row.scenario_l2_name, row.scenario_l3_name]) }}<template v-if="row.scenario_state && row.scenario_state !== candidate?.status"> · {{ row.scenario_state }}</template></span>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        v-if="canEditRows"
        label="操作"
        width="100"
      >
        <template #default="{ row }">
          <button
            type="button"
            class="row-action row-action--primary"
            :aria-label="`修改《${row.policy_title}》的场景`"
            @click="startEdit(row)"
          >
            改场景
          </button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-if="total > PAGE_SIZE"
      v-model:current-page="page"
      class="rows__pager"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="PAGE_SIZE"
      @current-change="load"
    />
  </el-drawer>
</template>

<style scoped>
.rows__toolbar {
  display: flex;
  gap: var(--zt-space-2);
  margin-bottom: var(--zt-space-3);
}

.rows__industry {
  flex: 0 0 320px;
}

.rows__title {
  display: flex;
  flex-direction: column;
  gap: 4px;
  white-space: normal;
}

.rows__sub {
  color: var(--zt-ink-500);
  font-size: 12px;
  line-height: 18px;
}

.rows__place {
  display: flex;
  flex-direction: column;
  white-space: normal;
}

.rows__edit {
  display: flex;
  gap: var(--zt-space-2);
  align-items: center;
  margin-top: 6px;
}

.rows__pager {
  justify-content: flex-end;
  margin-top: var(--zt-space-3);
}
</style>
