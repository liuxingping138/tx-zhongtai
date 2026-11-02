<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { errorMessage } from '@/api/errors'
import {
  getCandidate,
  getCandidateContext,
  listCandidateRows,
  listCandidates,
  reopenCandidate,
  type CandidateContext,
  type CandidateDetail,
  type CandidateRow,
} from '@/api/scenarioCandidates'
import AuditLogButton from '@/components/AuditLogButton.vue'
import { useAuthStore } from '@/stores/auth'
import { useReviewRecord } from '../shared/useReviewRecord'
import CandidateEvidence from './CandidateEvidence.vue'
import CandidateRowsDrawer from './CandidateRowsDrawer.vue'
import DecisionDialog from './DecisionDialog.vue'
import DecisionOptions from './DecisionOptions.vue'
import { FILTER_KEYS, KIND_NEW, PENDING, RESOURCE, aiText, decisionText, mergeTargetOf, positionParts, suggest, suggestionText, type DecisionMode } from './candidates'
import { useAfterDecision } from './useAfterDecision'

const auth = useAuthStore()
const canDecide = computed(() => auth.canFull(RESOURCE))
// 采纳、合并写的是行业场景码表：还要码表可管理
const canWriteCodebook = computed(() => canDecide.value && auth.canFull('codebook.scenarios'))

const review = useReviewRecord<CandidateDetail>({
  routeName: 'policy-scenario-candidate-review',
  listName: 'policy-scenario-candidates',
  filterKeys: FILTER_KEYS,
  get: getCandidate,
  list: params => listCandidates(params),
})
const candidate = computed(() => review.record.value)
const context = ref<CandidateContext | null>(null)
const contextError = ref('')
const rows = ref<CandidateRow[]>([])

watch(() => candidate.value?.id, async (id) => {
  context.value = null
  contextError.value = ''
  rows.value = []
  if (!id) return
  const [found, page] = await Promise.allSettled([getCandidateContext(id), listCandidateRows(id, { page_size: 5 })])
  if (id !== candidate.value?.id) return
  if (found.status === 'fulfilled') context.value = found.value
  else contextError.value = errorMessage(found.reason, '码表暂时取不到，同级场景和相似场景先看不了')
  if (page.status === 'fulfilled') rows.value = page.value.items
})

const suggestion = computed(() => (candidate.value ? suggest(candidate.value) : null))
// 合并时预选的目标：AI 说的、码表里对得上的；AI 没看过时用同一行业下名称很像的。其余让人自己在确认框里选
const mergeTarget = computed(() => (candidate.value ? mergeTargetOf(candidate.value, context.value?.similar ?? []) : null))
const reasonText = computed(() => (candidate.value ? suggestionText(candidate.value, suggestion.value) : ''))
const dialog = ref<DecisionMode | null>(null)
const presetTarget = ref<string[] | null>(null)
const drawer = ref(false)

function open(mode: DecisionMode, target: string[] | null = null) {
  presetTarget.value = target
  dialog.value = mode
}

const { finished } = useAfterDecision(review)
async function decided(row: Parameters<typeof finished>[0]) {
  dialog.value = null
  await finished(row)
}

const reopening = ref(false)
async function reopen() {
  const row = candidate.value
  if (!row || reopening.value) return
  reopening.value = true
  try {
    await reopenCandidate(row.id, { version: row.version })
    ElMessage.success('已改判回待审')
    await review.load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '没能改判，请重试'))
  } finally {
    reopening.value = false
  }
}
</script>

<template>
  <div class="candidate">
    <nav class="candidate__nav">
      <el-button
        link
        type="primary"
        @click="review.backToList"
      >
        ‹ 返回新增场景审核
      </el-button>
      <span
        v-if="review.position.value !== null && review.total.value !== null"
        class="candidate__position"
      >第 {{ review.position.value + 1 }} 个，共 {{ review.total.value.toLocaleString() }} 个（当前筛选）</span>
      <el-button
        :disabled="!review.hasPrev.value || review.moving.value"
        @click="review.move(-1)"
      >
        ‹ 上一个
      </el-button>
      <el-button
        :disabled="!review.hasNext.value || review.moving.value"
        @click="review.move(1)"
      >
        下一个 ›
      </el-button>
    </nav>

    <el-alert
      v-if="review.loadError.value"
      type="error"
      :title="review.loadError.value"
      :closable="false"
      show-icon
    />
    <template v-else-if="candidate">
      <section
        v-loading="review.loading.value"
        class="candidate__summary"
      >
        <div class="candidate__title">
          <h1>{{ candidate.name }}</h1>
          <el-tag effect="plain">
            新增{{ candidate.level_label === '新关联' ? '关联' : candidate.level_label }}
          </el-tag>
          <el-tag
            :type="candidate.status === PENDING ? 'warning' : 'info'"
            effect="plain"
          >
            {{ candidate.status }}
          </el-tag>
          <AuditLogButton :module="RESOURCE" />
        </div>
        <p
          class="candidate__where"
          aria-label="在码表里的位置"
        >
          <span class="candidate__where-label">位置</span>
          <span>{{ candidate.kind === KIND_NEW ? candidate.main_industry : candidate.industry }}</span>
          <template
            v-for="part in positionParts(candidate)"
            :key="part.level"
          >
            <span aria-hidden="true">›</span>
            <span :class="['candidate__part', { 'candidate__part--new': part.added }]">
              {{ part.name }}<small>{{ part.level }} · {{ part.added ? '新增' : '码表已有' }}</small>
            </span>
          </template>
          <span
            v-if="candidate.kind !== KIND_NEW"
            class="candidate__where-label"
          >场景码表里都有，这次是新挂到这个行业下</span>
        </p>
        <p class="candidate__ai">
          {{ aiText(candidate) }}
        </p>
        <dl class="candidate__facts">
          <div><dt>挂在</dt><dd>{{ candidate.kind === KIND_NEW ? (candidate.parent || '（新的一级场景）') : candidate.industry }}</dd></div>
          <div><dt>一级行业</dt><dd>{{ candidate.main_industry }}{{ candidate.industry_count > 1 ? ` 等 ${candidate.industry_count} 个` : '' }}</dd></div>
          <div>
            <dt>来源政策</dt>
            <dd>
              <el-button
                link
                type="primary"
                @click="drawer = true"
              >
                {{ candidate.policy_count.toLocaleString() }} 条
              </el-button>
            </dd>
          </div>
          <div><dt>解读行数</dt><dd>{{ candidate.row_count.toLocaleString() }}</dd></div>
          <div><dt>首次出现</dt><dd>{{ candidate.first_seen_at.slice(0, 10) }}</dd></div>
          <div><dt>最近出现</dt><dd>{{ candidate.last_seen_at.slice(0, 10) }}</dd></div>
        </dl>
      </section>

      <DecisionOptions
        v-if="candidate.status === PENDING && canDecide"
        :candidate="candidate"
        :suggestion="suggestion"
        :reason="reasonText"
        :merge-target="mergeTarget"
        :can-write-codebook="canWriteCodebook"
        @open="open"
      />
      <section
        v-else
        class="candidate__decided"
      >
        <p>{{ decisionText(candidate) || '待审。你只有查看权限，决定要「新增场景审核」的管理权限。' }}</p>
        <el-button
          v-if="candidate.status === '已驳回' && canDecide"
          :loading="reopening"
          @click="reopen"
        >
          改判回待审
        </el-button>
      </section>

      <CandidateEvidence
        :candidate="candidate"
        :context="context"
        :context-error="contextError"
        :rows="rows"
        :can-merge="canWriteCodebook"
        @merge="path => open('merge', path)"
        @open-rows="drawer = true"
      />

      <DecisionDialog
        :mode="dialog"
        :candidate="candidate"
        :context="context"
        :preset-target="presetTarget"
        @close="dialog = null"
        @done="decided"
      />
      <CandidateRowsDrawer
        :candidate="drawer ? candidate : null"
        @close="drawer = false"
        @changed="review.load"
      />
    </template>
  </div>
</template>

<style scoped>
.candidate {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-4);
}

.candidate__nav {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-2);
  align-items: center;
}

.candidate__position {
  margin-left: auto;
  color: var(--zt-ink-500);
  font-size: 13px;
}

.candidate__summary,
.candidate__decided {
  padding: var(--zt-space-4) var(--zt-space-6);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
}

.candidate__title {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-3);
  align-items: center;
}

.candidate__title h1 {
  margin: 0;
  font-size: 22px;
}

.candidate__title > :last-child {
  margin-left: auto;
}

.candidate__where {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-2);
  align-items: center;
  margin: var(--zt-space-3) 0 0;
  font-size: 14px;
}

.candidate__where-label {
  color: var(--zt-ink-500);
  font-size: 13px;
}

.candidate__part {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  padding: 2px 10px;
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-surface-subtle);
}

.candidate__part small {
  color: var(--zt-ink-500);
  font-size: 12px;
}

.candidate__part--new {
  border: 1px dashed var(--zt-warning);
  background: var(--zt-warning-soft);
  color: var(--zt-warning-text);
  font-weight: 600;
}

.candidate__part--new small {
  color: var(--zt-warning-text);
}

.candidate__ai {
  margin: var(--zt-space-3) 0 0;
  color: var(--zt-ink-700);
  font-size: 13px;
  line-height: 20px;
}

.candidate__facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-2) var(--zt-space-8);
  margin: var(--zt-space-3) 0 0;
  font-size: 13px;
}

.candidate__facts div {
  display: flex;
  gap: var(--zt-space-2);
  align-items: baseline;
}

.candidate__facts dt {
  color: var(--zt-ink-500);
}

.candidate__facts dd {
  margin: 0;
}

.candidate__decided {
  display: flex;
  gap: var(--zt-space-4);
  align-items: center;
  justify-content: space-between;
}

.candidate__decided p {
  margin: 0;
}
</style>
