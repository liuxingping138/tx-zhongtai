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
import { FILTER_KEYS, KIND_NEW, PENDING, RESOURCE, decisionText, pathText, suggest, type DecisionMode } from './candidates'
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
const mergeTarget = computed(() => context.value?.similar[0]?.path ?? null)
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

      <section
        v-if="candidate.status === PENDING && canDecide"
        class="candidate__options"
        aria-label="怎么处理"
      >
        <article :class="['option', { 'option--suggested': suggestion === 'merge' }]">
          <span
            v-if="suggestion === 'merge'"
            class="option__badge"
          >系统建议 · 码表里有高度相似的</span>
          <h2>{{ mergeTarget ? `合并到「${mergeTarget[mergeTarget.length - 1]}」` : '合并到已有场景' }}</h2>
          <p class="option__path">
            {{ mergeTarget ? pathText(mergeTarget) : '在码表里选一个已有场景' }}
          </p>
          <ul>
            <li>{{ candidate.row_count.toLocaleString() }} 行解读改用这个场景，回填它的编码</li>
            <li>这个说法记成它的别名，以后 AI 再写自动归过去</li>
            <li>码表不新增编号</li>
          </ul>
          <el-button
            :type="suggestion === 'merge' ? 'primary' : 'default'"
            :disabled="!canWriteCodebook"
            :title="canWriteCodebook ? '' : '合并要写行业场景码表，需要码表的管理权限'"
            @click="open('merge', mergeTarget)"
          >
            {{ suggestion === 'merge' ? '按建议合并…' : '合并…' }}
          </el-button>
        </article>
        <article :class="['option', { 'option--suggested': suggestion === 'adopt' }]">
          <span
            v-if="suggestion === 'adopt'"
            class="option__badge"
          >系统建议</span>
          <h2>采纳为新场景</h2>
          <p class="option__path">
            {{ candidate.kind === KIND_NEW ? `${candidate.parent || '一级场景'}下新增「${candidate.name}」` : `挂到 ${candidate.industry}` }}
          </p>
          <ul>
            <li>写进行业场景码表，按现有规则顺延编号，标「AI 新增」</li>
            <li>{{ candidate.row_count.toLocaleString() }} 行解读回填编码</li>
            <li>以后 AI 再写这个说法直接回填，不再进待审</li>
          </ul>
          <el-button
            :type="suggestion === 'adopt' ? 'primary' : 'default'"
            :disabled="!canWriteCodebook"
            :title="canWriteCodebook ? '' : '采纳要写行业场景码表，需要码表的管理权限'"
            @click="open('adopt')"
          >
            采纳…
          </el-button>
        </article>
        <article class="option">
          <h2>驳回</h2>
          <p class="option__path">
            不是一个该进码表的场景
          </p>
          <ul>
            <li>{{ candidate.row_count.toLocaleString() }} 行解读留着，场景状态标「已驳回」</li>
            <li>以后 AI 再写这个说法自动驳回</li>
            <li>个别政策该归到别的场景：在来源政策里逐条改</li>
          </ul>
          <el-button @click="open('reject')">
            驳回…
          </el-button>
        </article>
      </section>
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

.candidate__options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--zt-space-4);
}

.option {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-2);
  padding: var(--zt-space-4) var(--zt-space-6);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
}

.option--suggested {
  border-color: var(--el-color-primary);
  box-shadow: inset 0 0 0 1px var(--el-color-primary);
}

.option__badge {
  align-self: flex-start;
  padding: 0 8px;
  border-radius: 4px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 12px;
  line-height: 22px;
}

.option h2 {
  margin: 0;
  font-size: 16px;
}

.option__path {
  margin: 0;
  color: var(--zt-ink-500);
  font-size: 13px;
}

.option ul {
  flex: 1;
  margin: 0;
  padding-left: 18px;
  color: var(--zt-ink-700);
  font-size: 13px;
  line-height: 20px;
}

.option .el-button {
  align-self: flex-start;
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
