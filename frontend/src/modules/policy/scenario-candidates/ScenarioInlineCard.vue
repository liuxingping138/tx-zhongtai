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
import DecisionButtons from './DecisionButtons.vue'
import DecisionDialog from './DecisionDialog.vue'
import { PENDING, RESOURCE, decisionText, defaultMergeTarget, doneText, levelTag, matchSentence, type DecisionMode } from './candidates'

/**
 * 解读核对页「行业与场景」组里，这一行的场景情况压成一行（2026-11-03 用户嫌原来的橙色大框乱）：
 * 新增场景还在待审的，一行写几级、名称、几条政策、码表里像它的，按钮和新增场景审核列表同一个（只露建议的那个）；
 * 已经决定过的只剩一句灰字；行业不在码表、场景不完整的就地改成码表里的场景。码表里本来就有的什么都不显示。
 */
const props = defineProps<{ row: InterpretationItem }>()
const emit = defineEmits<{ changed: [] }>()

const auth = useAuthStore()
const canReadCandidate = computed(() => auth.canRead('policy.scenario_candidates'))
const canReadCodebook = computed(() => auth.canRead('codebook.scenarios'))
const canDecide = computed(() => auth.canFull(RESOURCE))
const canWriteCodebook = computed(() => canDecide.value && auth.canFull('codebook.scenarios'))
const canEditRow = computed(() => auth.canFull('policy.interpretations'))
const FIXABLE = ['行业不在码表', '场景不完整']
const FIX_HINTS: Record<string, string> = {
  行业不在码表: '这一行的三级行业码表里没有；新场景不新增行业，请改成码表里的',
  场景不完整: '没有一级场景，或有三级没二级，请改成码表里的场景',
}

const candidate = ref<CandidateDetail | null>(null)
const context = ref<CandidateContext | null>(null)
watch(() => [props.row.candidate_id, props.row.version, canReadCandidate.value], async () => {
  candidate.value = null
  context.value = null
  const id = props.row.candidate_id
  if (!id || !canReadCandidate.value) return
  try {
    const found = await getCandidate(id)
    if (props.row.candidate_id === id) candidate.value = found
  } catch {
    /* 取不到就不显示卡片，不影响核对 */
  }
}, { immediate: true })

const dialog = ref<DecisionMode | null>(null)
const opening = ref<DecisionMode | null>(null)
const preset = ref<string[] | null>(null)
async function open(mode: DecisionMode) {
  const current = candidate.value
  if (!current || opening.value) return
  opening.value = mode
  if (!context.value) {
    try {
      context.value = await getCandidateContext(current.id)
    } catch {
      context.value = { siblings: [], similar: [], industries: [] }
    }
  }
  // 和列表一样：「合并」预选这一行写着的那个场景
  preset.value = mode === 'merge' ? defaultMergeTarget(current, context.value.similar) : null
  opening.value = null
  dialog.value = mode
}
function decided(row: CandidateItem) {
  dialog.value = null
  ElMessage.success(doneText(row))
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
  <div
    v-if="candidate && candidate.status === PENDING"
    class="scenario-line"
    role="region"
    aria-label="这一行的新增场景"
  >
    <span class="scenario-line__tag">{{ levelTag(candidate) }} · 待审</span>
    <strong>{{ candidate.name }}</strong>
    <span class="scenario-line__muted">{{ candidate.policy_count.toLocaleString() }} 条政策 · {{ matchSentence(candidate) }}</span>
    <span class="scenario-line__space" />
    <DecisionButtons
      v-if="canDecide"
      :candidate="candidate"
      :can-write-codebook="canWriteCodebook"
      :busy="opening"
      @open="open"
    />
    <RouterLink :to="{ name: 'policy-scenario-candidates', query: { focus: candidate.id } }">
      去新增场景审核 →
    </RouterLink>
    <DecisionDialog
      :mode="dialog"
      :candidate="candidate"
      :context="context"
      :preset-target="preset"
      @close="dialog = null"
      @done="decided"
    />
  </div>
  <p
    v-else-if="candidate"
    class="scenario-line__done"
  >
    场景{{ decisionText(candidate) }} · <RouterLink :to="{ name: 'policy-scenario-candidates', query: { focus: candidate.id } }">
      去新增场景审核看
    </RouterLink>
  </p>
  <div
    v-else-if="FIXABLE.includes(row.scenario_state)"
    class="scenario-line"
    role="region"
    aria-label="这一行的场景要改"
  >
    <span class="scenario-line__tag scenario-line__tag--fix">{{ row.scenario_state }}</span>
    <span class="scenario-line__muted">{{ FIX_HINTS[row.scenario_state] }}</span>
    <span class="scenario-line__space" />
    <template v-if="canEditRow && canReadCodebook">
      <template v-if="fixing">
        <ScenarioPicker
          v-model="picked"
          class="scenario-line__picker"
          :industry-l1="row.industry_l1"
        />
        <el-button @click="fixing = false">
          取消
        </el-button>
        <el-button
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
        type="primary"
        plain
        @click="fixing = true"
      >
        改成码表里的场景
      </el-button>
    </template>
  </div>
</template>

<style scoped>
/* 一行浅灰底：不用警告色，不抢「核对无误」的风头 */
.scenario-line {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-2) var(--zt-space-3);
  align-items: center;
  margin-bottom: var(--zt-space-3);
  padding: var(--zt-space-2) var(--zt-space-3);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-surface-subtle);
  font-size: 13px;
  line-height: 20px;
}

.scenario-line strong {
  color: var(--zt-ink-900);
  font-size: 14px;
}

.scenario-line .el-button {
  height: 30px;
  margin: 0;
}

.scenario-line__tag {
  padding: 0 8px;
  border: 1px solid var(--zt-warning-border);
  border-radius: 4px;
  background: var(--zt-warning-soft);
  color: var(--zt-warning-text);
  font-size: 12px;
  white-space: nowrap;
}

.scenario-line__tag--fix {
  border-color: var(--zt-danger-border);
  background: var(--zt-danger-soft);
  color: var(--zt-danger-text);
}

.scenario-line__muted {
  color: var(--zt-ink-500);
}

.scenario-line__space {
  flex-grow: 1;
}

.scenario-line__picker {
  width: 320px;
}

.scenario-line__done {
  margin: 0 0 var(--zt-space-3);
  color: var(--zt-ink-500);
  font-size: 13px;
}
</style>
