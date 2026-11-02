<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { ScenarioPath } from '@/api/codebook'
import { errorMessage } from '@/api/errors'
import {
  adoptCandidate,
  mergeCandidate,
  rejectCandidate,
  type CandidateContext,
  type CandidateDetail,
  type CandidateItem,
} from '@/api/scenarioCandidates'
import ScenarioPicker from '@/components/ScenarioPicker.vue'
import { KIND_NEW, REJECT_REASONS, pathText, scenarioNames, type DecisionMode } from './candidates'

/** 采纳、合并、驳回的确认框：写清楚确定后会发生什么，再提交。 */
const props = defineProps<{
  mode: DecisionMode | null
  candidate: CandidateDetail
  context: CandidateContext | null
  /** 从「相似的已有场景」点「合并到这里」进来时预选的目标 */
  presetTarget?: string[] | null
}>()
const emit = defineEmits<{ close: []; done: [row: CandidateItem] }>()

const TITLES: Record<DecisionMode, string> = { adopt: '采纳为新场景', merge: '合并到已有场景', reject: '驳回这个新增场景' }
const name = ref('')
const target = ref<string[] | null>(null)
const picked = ref<ScenarioPath | null>(null)
/** 在「相似的已有场景」里点选的那一条（路径文字） */
const chosen = ref('')
const reason = ref(REJECT_REASONS[0] ?? '')
const note = ref('')
const submitting = ref(false)
const error = ref('')

watch(() => props.mode, (mode) => {
  if (!mode) return
  name.value = props.candidate.name
  // 只预选从「合并到这里」或系统建议带进来的目标，不替人默认选一个相似度一般的
  target.value = props.presetTarget ?? null
  chosen.value = target.value ? pathText(target.value) : ''
  picked.value = null
  reason.value = REJECT_REASONS[0] ?? ''
  note.value = ''
  error.value = ''
})
watch(picked, (path) => {
  if (!path) return
  target.value = scenarioNames(path)
  chosen.value = ''
})
watch(chosen, (text) => {
  const found = props.context?.similar.find(item => pathText(item.path) === text)
  if (found) {
    target.value = found.path
    picked.value = null
  }
})

const rows = computed(() => props.candidate.row_count.toLocaleString())
const isNew = computed(() => props.candidate.kind === KIND_NEW)
const where = computed(() => props.candidate.parent || (isNew.value ? '（新的一级场景）' : pathText([props.candidate.scenario_l1, props.candidate.scenario_l2, props.candidate.scenario_l3])))
const targetText = computed(() => (target.value ? pathText(target.value) : ''))
const ready = computed(() => {
  if (props.mode === 'merge') return Boolean(target.value?.[0])
  if (props.mode === 'adopt') return !isNew.value || Boolean(name.value.trim())
  return Boolean(reason.value)
})

async function submit() {
  if (!props.mode || !ready.value || submitting.value) return
  submitting.value = true
  error.value = ''
  const { id, version } = props.candidate
  try {
    let row: CandidateItem
    if (props.mode === 'adopt') row = await adoptCandidate(id, { version, name: isNew.value ? name.value.trim() : '' })
    else if (props.mode === 'merge') row = await mergeCandidate(id, { version, target: target.value ?? [] })
    else row = await rejectCandidate(id, { version, reason: reason.value, note: note.value.trim() })
    emit('done', row)
  } catch (failure) {
    error.value = errorMessage(failure, '没有成功，请重试')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="Boolean(mode)"
    :title="mode ? TITLES[mode] : ''"
    width="min(560px, 94vw)"
    @close="emit('close')"
  >
    <div class="decision">
      <template v-if="mode === 'adopt'">
        <el-form-item
          v-if="isNew"
          label="场景名称"
          label-position="top"
        >
          <el-input
            v-model="name"
            maxlength="255"
          />
          <p class="decision__hint">
            可以改成更通用的说法；AI 原来的说法照样记着，以后再出现也归到这里
          </p>
        </el-form-item>
        <p><span class="decision__label">挂在</span>{{ where }}</p>
        <p v-if="candidate.children.length">
          <span class="decision__label">下级新场景</span>{{ candidate.children.map(child => child.path).join('、') }}（一起采纳）
        </p>
        <p><span class="decision__label">涉及行业</span>{{ candidate.industries.map(item => `${item.path}（${item.rows} 行）`).join('；') }}</p>
      </template>

      <template v-else-if="mode === 'merge'">
        <p class="decision__label">
          合并到
        </p>
        <el-radio-group
          v-if="context?.similar.length"
          v-model="chosen"
          class="decision__choices"
        >
          <el-radio
            v-for="item in context.similar"
            :key="pathText(item.path)"
            :value="pathText(item.path)"
          >
            {{ pathText(item.path) }}<span class="decision__hint">　{{ item.industry }} · 相似度{{ item.level }}</span>
          </el-radio>
        </el-radio-group>
        <ScenarioPicker v-model="picked" />
        <p
          v-if="targetText"
          class="decision__picked"
        >
          已选：{{ targetText }}
        </p>
      </template>

      <template v-else-if="mode === 'reject'">
        <p class="decision__label">
          原因
        </p>
        <el-radio-group
          v-model="reason"
          class="decision__choices decision__choices--row"
        >
          <el-radio-button
            v-for="item in REJECT_REASONS"
            :key="item"
            :value="item"
          >
            {{ item }}
          </el-radio-button>
        </el-radio-group>
        <el-input
          v-model="note"
          type="textarea"
          :rows="2"
          maxlength="2000"
          placeholder="补充说明（选填），写给以后看的人"
        />
      </template>

      <section
        class="decision__what"
        aria-label="确定后会"
      >
        <h3>确定后会</h3>
        <ul v-if="mode === 'adopt'">
          <li>写进行业场景码表，按现有规则顺延编号，标「AI 新增」</li>
          <li>{{ rows }} 行解读回填编码；以后 AI 再写这个说法直接回填，不再进待审</li>
        </ul>
        <ul v-else-if="mode === 'merge'">
          <li>{{ rows }} 行解读改用{{ targetText ? `「${targetText}」` : '目标场景' }}，回填它的编码；码表不新增编号</li>
          <li>「{{ candidate.name }}」记成它的别名，以后 AI 再写自动归过去</li>
          <li>目标场景还没挂在这些行的行业下时，码表加一行行业关联，场景编号沿用</li>
          <li>同一条政策本来就有这个场景、机会类型也相同的行，标「重复」，不删</li>
        </ul>
        <ul v-else>
          <li>{{ rows }} 行解读都留着，场景状态标「已驳回」</li>
          <li>以后 AI 再写这个说法自动驳回，不再进待审；可以在「已驳回」里改判</li>
          <li>其中有几条其实该归到别的场景：先在来源政策里逐条「改场景」，再驳回剩下的</li>
        </ul>
      </section>
      <el-alert
        v-if="error"
        type="error"
        :title="error"
        :closable="false"
        show-icon
      />
    </div>
    <template #footer>
      <el-button @click="emit('close')">
        取消
      </el-button>
      <el-button
        :type="mode === 'reject' ? 'danger' : 'primary'"
        :loading="submitting"
        :disabled="!ready"
        @click="submit"
      >
        {{ mode === 'adopt' ? '确定采纳' : mode === 'merge' ? '确定合并' : '驳回' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.decision {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-3);
  line-height: 22px;
}

.decision p {
  margin: 0;
}

.decision__label {
  display: inline-block;
  min-width: 84px;
  color: var(--zt-ink-500);
  font-size: 13px;
}

.decision__hint {
  margin: 4px 0 0;
  color: var(--zt-ink-500);
  font-size: 12px;
}

.decision__choices {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--zt-space-1);
}

.decision__choices--row {
  flex-direction: row;
  flex-wrap: wrap;
}

.decision__picked {
  color: var(--zt-ink-700);
  font-size: 13px;
}

.decision__what {
  padding: var(--zt-space-3) var(--zt-space-4);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-surface-subtle);
}

.decision__what h3 {
  margin: 0 0 6px;
  color: var(--zt-ink-700);
  font-size: 13px;
}

.decision__what ul {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
}
</style>
