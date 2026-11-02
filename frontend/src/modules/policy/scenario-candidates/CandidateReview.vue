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
import { useAuthStore } from '@/stores/auth'
import { useReviewRecord } from '../shared/useReviewRecord'
import CandidateHeader from './CandidateHeader.vue'
import CandidateMatches from './CandidateMatches.vue'
import CandidateMore from './CandidateMore.vue'
import CandidateRowsDrawer from './CandidateRowsDrawer.vue'
import DecisionBar from './DecisionBar.vue'
import DecisionDialog from './DecisionDialog.vue'
import { FILTER_KEYS, PENDING, RESOURCE, decisionText, suggest, type DecisionMode } from './candidates'
import { useAfterDecision } from './useAfterDecision'
import { useCandidatePeers } from './useCandidatePeers'

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
const { peers, absorbing, absorb } = useCandidatePeers(candidate, () => review.load())
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
        ‹ 返回列表
      </el-button>
      <span
        v-if="review.position.value !== null && review.total.value !== null"
        class="candidate__position"
      >第 {{ review.position.value + 1 }} / {{ review.total.value.toLocaleString() }} 个</span>
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
      <div
        v-loading="review.loading.value"
        class="candidate__body"
      >
        <CandidateHeader
          :candidate="candidate"
          :context="context"
          :rows="rows"
          @open-rows="drawer = true"
        />
        <CandidateMatches
          :candidate="candidate"
          :context="context"
          :context-error="contextError"
          :can-merge="canWriteCodebook"
          :peers="peers"
          :can-absorb="canDecide && candidate.status === PENDING"
          :absorbing="absorbing"
          @merge="path => open('merge', path)"
          @absorb="absorb"
        />
        <DecisionBar
          v-if="candidate.status === PENDING && canDecide"
          :candidate="candidate"
          :suggestion="suggestion"
          :can-write-codebook="canWriteCodebook"
          @open="mode => open(mode)"
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
        <CandidateMore
          :candidate="candidate"
          :context="context"
        />
      </div>

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

.candidate__body {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-4);
}

.candidate__decided {
  padding: var(--zt-space-4) var(--zt-space-6);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
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
