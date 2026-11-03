<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import type { ScenarioPath } from '@/api/codebook'
import { errorMessage } from '@/api/errors'
import type { InterpretationItem } from '@/api/policy'
import {
  changeRowScenario,
  getCandidate,
  getCandidateContext,
  type CandidateContext,
  type CandidateDetail,
  type CandidateItem,
} from '@/api/scenarioCandidates'
import ScenarioPicker from '@/components/ScenarioPicker.vue'
import { useAuthStore } from '@/stores/auth'
import DecisionDialog from './DecisionDialog.vue'
import { PENDING, RESOURCE, aiText, decisionText, type DecisionMode } from './candidates'

/**
 * 解读核对页上这一行的场景情况：新增场景还在待审的，就地看 AI 的判断、直接采纳 / 合并 / 驳回（对所有提出它的政策一起生效）；
 * 已经决定过的写一句结果；行业不在码表、场景不完整的可以就地改成码表里的场景。
 */
const props = defineProps<{ row: InterpretationItem }>()
const emit = defineEmits<{ changed: [] }>()

const auth = useAuthStore()
const canDecide = computed(() => auth.canFull(RESOURCE))
const canWriteCodebook = computed(() => canDecide.value && auth.canFull('codebook.scenarios'))
const canEditRow = computed(() => auth.canFull('policy.interpretations'))
const FIXABLE = ['行业不在码表', '场景不完整']
const FIX_HINTS: Record<string, string> = {
  行业不在码表: '这一行的三级行业在行业场景码表里没有：新场景不新增行业，请改成码表里的行业场景。',
  场景不完整: '这一行的场景名称不完整（没有一级场景，或有三级没二级），请改成码表里的场景。',
}

const candidate = ref<CandidateDetail | null>(null)
const context = ref<CandidateContext | null>(null)
watch(() => [props.row.candidate_id, props.row.version], async () => {
  candidate.value = null
  context.value = null
  const id = props.row.candidate_id
  if (!id) return
  try {
    const found = await getCandidate(id)
    if (props.row.candidate_id === id) candidate.value = found
  } catch {
    /* 取不到就不显示卡片，不影响核对 */
  }
}, { immediate: true })

const dialog = ref<DecisionMode | null>(null)
async function open(mode: DecisionMode) {
  const current = candidate.value
  if (!current) return
  if (!context.value) {
    try {
      context.value = await getCandidateContext(current.id)
    } catch {
      context.value = { siblings: [], similar: [], industries: [] }
    }
  }
  dialog.value = mode
}
function decided(row: CandidateItem) {
  dialog.value = null
  ElMessage.success(`已${row.status === '已驳回' ? '驳回' : row.status === '已合并' ? '合并' : '采纳'}，提出这个场景的 ${row.row_count} 行一起改好了`)
  emit('changed')
}

const fixing = ref(false)
const picked = ref<ScenarioPath | null>(null)
const saving = ref(false)
async function fix() {
  const path = picked.value
  if (!path || saving.value) return
  saving.value = true
  try {
    // 码表路径里还带着编码，接口只收六级名称（多余字段会被拒）
    const out = await changeRowScenario(props.row.id, {
      version: props.row.version,
      industry_l1: path.industry_l1,
      industry_l2: path.industry_l2,
      industry_l3: path.industry_l3,
      scenario_l1_name: path.scenario_l1_name,
      scenario_l2_name: path.scenario_l2_name,
      scenario_l3_name: path.scenario_l3_name,
    })
    ElMessage.success(`已改，这一行现在是「${out.scenario_state}」`)
    fixing.value = false
    emit('changed')
  } catch (error) {
    ElMessage.error(errorMessage(error, '没改成，请重试'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section
    v-if="candidate && candidate.status === PENDING"
    class="inline-card"
    aria-label="这一行的新增场景"
  >
    <p>
      <strong>这一行的场景「{{ candidate.name }}」是新增的（{{ candidate.level_label }}），还在待审</strong>
      <span class="inline-card__muted">一共 {{ candidate.policy_count }} 条政策提出过，在这里决定对它们一起生效</span>
    </p>
    <p class="inline-card__muted">
      {{ aiText(candidate) }}
    </p>
    <div class="inline-card__actions">
      <template v-if="canDecide">
        <el-button
          size="small"
          :disabled="!canWriteCodebook"
          @click="open('merge')"
        >
          合并到已有场景…
        </el-button>
        <el-button
          size="small"
          :disabled="!canWriteCodebook"
          @click="open('adopt')"
        >
          采纳为新场景…
        </el-button>
        <el-button
          size="small"
          @click="open('reject')"
        >
          驳回…
        </el-button>
      </template>
      <RouterLink :to="{ name: 'policy-scenario-candidates', query: { focus: candidate.id } }">
        去新增场景审核看全部依据 →
      </RouterLink>
    </div>
    <DecisionDialog
      :mode="dialog"
      :candidate="candidate"
      :context="context"
      :preset-target="candidate.ai_target ? candidate.ai_target.split(' > ') : null"
      @close="dialog = null"
      @done="decided"
    />
  </section>
  <p
    v-else-if="candidate"
    class="inline-card__line"
  >
    这一行的场景：{{ decisionText(candidate) }}
  </p>
  <section
    v-else-if="FIXABLE.includes(row.scenario_state)"
    class="inline-card"
    aria-label="这一行的场景要改"
  >
    <p><strong>场景{{ row.scenario_state }}</strong> <span class="inline-card__muted">{{ FIX_HINTS[row.scenario_state] }}</span></p>
    <div
      v-if="canEditRow"
      class="inline-card__actions"
    >
      <template v-if="fixing">
        <ScenarioPicker
          v-model="picked"
          :industry-l1="row.industry_l1"
        />
        <el-button
          size="small"
          @click="fixing = false"
        >
          取消
        </el-button>
        <el-button
          size="small"
          type="primary"
          :disabled="!picked"
          :loading="saving"
          @click="fix"
        >
          改这一行
        </el-button>
      </template>
      <el-button
        v-else
        size="small"
        @click="fixing = true"
      >
        改成码表里的场景
      </el-button>
    </div>
  </section>
</template>

<style scoped>
.inline-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: var(--zt-space-3);
  padding: var(--zt-space-3) var(--zt-space-4);
  border: 1px solid var(--zt-warning-border);
  border-radius: var(--zt-radius);
  background: var(--zt-warning-soft);
}

.inline-card p,
.inline-card__line {
  margin: 0;
  line-height: 22px;
}

.inline-card__line {
  margin-top: var(--zt-space-3);
  color: var(--zt-ink-700);
  font-size: 13px;
}

.inline-card__muted {
  color: var(--zt-ink-700);
  font-size: 13px;
}

.inline-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-2);
  align-items: center;
}
</style>
