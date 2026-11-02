<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import type { ScenarioPath } from '@/api/codebook'
import { errorMessage } from '@/api/errors'
import { changeRowScenario, listCandidateRows, type CandidateItem, type CandidateRow } from '@/api/scenarioCandidates'
import ScenarioPicker from '@/components/ScenarioPicker.vue'
import { pathText } from './candidates'

/** 提出这个场景的来源政策（解读行）。个别政策该归到别的场景时在这里逐行改，不影响这个场景的决定。 */
const props = defineProps<{ candidate: CandidateItem | null }>()
const emit = defineEmits<{ close: []; changed: [] }>()

const PAGE_SIZE = 20
const rows = ref<CandidateRow[]>([])
const total = ref(0)
const page = ref(1)
const keyword = ref('')
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
    const result = await listCandidateRows(id, { keyword: keyword.value.trim() || undefined, page: page.value, page_size: PAGE_SIZE })
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
    />
    <el-table
      v-loading="loading"
      :data="rows"
      class="data-table"
    >
      <el-table-column
        label="政策原文名称"
        min-width="260"
      >
        <template #default="{ row }">
          <div class="rows__title">
            <RouterLink :to="{ name: 'policy-interpretation-review', params: { id: row.id } }">
              {{ row.policy_title }}
            </RouterLink>
            <p
              v-if="row.remark"
              class="rows__remark"
            >
              {{ row.remark }}
            </p>
            <div
              v-if="editing === row.id"
              class="rows__edit"
            >
              <ScenarioPicker
                v-model="picked"
                :industry-l1="row.industry_l1"
                :placeholder="`在「${row.industry_l1}」下搜码表里的场景`"
              />
              <el-button @click="editing = null">
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
        prop="created_at"
        label="入库"
        width="170"
      />
      <el-table-column
        label="这一行的场景"
        min-width="200"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          {{ pathText([row.scenario_l1_name, row.scenario_l2_name, row.scenario_l3_name]) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="opportunity_type"
        label="机会类型"
        width="110"
      />
      <el-table-column
        prop="scenario_state"
        label="场景状态"
        width="100"
      />
      <el-table-column
        label="操作"
        width="90"
      >
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            @click="startEdit(row)"
          >
            改场景
          </el-button>
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

.rows__title {
  display: flex;
  flex-direction: column;
  gap: 4px;
  white-space: normal;
}

.rows__remark {
  margin: 0;
  color: var(--zt-ink-500);
  font-size: 12px;
  line-height: 18px;
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
