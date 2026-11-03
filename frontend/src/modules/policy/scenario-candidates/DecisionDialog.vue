<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { ScenarioPath } from '@/api/codebook'
import { errorMessage } from '@/api/errors'
import {
  adoptCandidate,
  candidateRenameImpact,
  mergeCandidate,
  rejectCandidate,
  type CandidateContext,
  type CandidateDetail,
  type CandidateItem,
} from '@/api/scenarioCandidates'
import ScenarioPicker from '@/components/ScenarioPicker.vue'
import { KIND_NEW, REJECT_REASONS, levelName, pathText, scenarioNames, similarLabel, type DecisionMode } from './candidates'

/** 采纳、改名再采纳、合并、驳回的确认框：写清楚确定后会发生什么，再提交。 */
const props = defineProps<{
  mode: DecisionMode | null
  candidate: CandidateDetail
  context: CandidateContext | null
  /** 点「合并到这里」、或这一行显示着 AI 认为是同一个 / 名称很像的场景时，预选的目标 */
  presetTarget?: string[] | null
}>()
const emit = defineEmits<{ close: []; done: [row: CandidateItem] }>()

const TITLES: Record<DecisionMode, string> = { adopt: '采纳为新场景', rename: '改个名再采纳', merge: '合并到已有场景', reject: '驳回这个新增场景' }
const name = ref('')
const target = ref<string[] | null>(null)
const picked = ref<ScenarioPath | null>(null)
/** 在「相似的已有场景」里点选的那一条（路径文字） */
const chosen = ref('')
const reason = ref(REJECT_REASONS[0] ?? '')
/** 合并：从页面上点「合并到这里」带进来的目标直接显示，「换一个」才展开选择 */
const changing = ref(false)
const note = ref('')
const submitting = ref(false)
/** 合并后叫什么：沿用原名称，或原场景改用这个新说法（编码不变，码表和解读里用它的行一起改名） */
const rename = ref(false)
const impact = ref<{ codebook_rows: number; interpretation_rows: number } | null>(null)
const canRename = computed(() => Boolean(target.value?.length) && target.value?.[target.value.length - 1] !== props.candidate.name)
watch([rename, target], async ([on, path]) => {
  impact.value = null
  if (!on || !path?.length || props.mode !== 'merge') return
  try {
    impact.value = await candidateRenameImpact(props.candidate.id, path)
  } catch {
    impact.value = null
  }
})
const error = ref('')

watch(() => props.mode, (mode) => {
  if (!mode) return
  name.value = props.candidate.name
  // 只预选从「合并到这里」或系统建议带进来的目标，不替人默认选一个相似度一般的
  target.value = props.presetTarget ?? null
  chosen.value = target.value ? pathText(target.value) : ''
  changing.value = !target.value
  rename.value = false
  picked.value = null
  reason.value = REJECT_REASONS[0] ?? ''
  note.value = ''
  error.value = ''
}, { immediate: true })
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

const isNew = computed(() => props.candidate.kind === KIND_NEW)
const targetText = computed(() => (target.value ? pathText(target.value) : ''))
const ready = computed(() => {
  if (props.mode === 'merge') return Boolean(target.value?.[0])
  if (props.mode === 'rename') return Boolean(name.value.trim()) && name.value.trim() !== props.candidate.name
  if (props.mode === 'adopt') return true
  return Boolean(reason.value)
})

/** 「确定后会」：几行大白话，写清码表和解读各会怎样。 */
const effects = computed(() => {
  const c = props.candidate
  const rows = c.row_count.toLocaleString()
  if (props.mode === 'merge') {
    return [
      `${rows} 行解读改用${targetText.value ? `「${targetText.value}」` : '选中的场景'}，回填它的编码；码表不新增编号`,
      `以后 AI 再写「${c.name}」，自动归到这里`,
      '同一条政策本来就有这个场景（机会类型也相同）的那行标「重复」，不删',
    ]
  }
  if (props.mode === 'reject') {
    return [
      `${rows} 行解读都留着，场景状态标「已驳回」`,
      '以后 AI 再写这个说法自动驳回；可以在「已驳回」里改判',
    ]
  }
  const renaming = props.mode === 'rename'
  const lines = isNew.value
    ? [
        `挂在 ${[c.main_industry, c.parent].filter(Boolean).join(' › ')} 下，作为新的${levelName(c.new_level)}场景`,
        '码表里新增一行，按现有规则顺延编号，标「AI 新增」',
      ]
    : [`挂到 ${c.industry}`, '码表加一行行业关联，场景编号沿用']
  if (c.children.length) lines.push(`AI 写的下级 ${c.children.map(child => child.path).join('、')} 一起采纳`)
  lines.push(`提出它的 ${rows} 行解读${renaming ? '改成这个名字并' : ''}回填编码`)
  lines.push(renaming ? `以后 AI 再写「${c.name}」，自动归到这里` : '以后 AI 再写这个说法直接回填，不再进待审')
  return lines
})

function send(mode: DecisionMode): Promise<CandidateItem> {
  const { id, version } = props.candidate
  if (mode === 'merge') return mergeCandidate(id, { version, target: target.value ?? [], rename: rename.value && canRename.value })
  if (mode === 'reject') return rejectCandidate(id, { version, reason: reason.value, note: note.value.trim() })
  return adoptCandidate(id, { version, name: mode === 'rename' ? name.value.trim() : '' })
}

async function submit() {
  if (!props.mode || !ready.value || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    emit('done', await send(props.mode))
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
      <el-form-item
        v-if="mode === 'rename'"
        :label="`场景名称（AI 写的是「${candidate.name}」）`"
        label-position="top"
      >
        <el-input
          v-model="name"
          maxlength="255"
        />
      </el-form-item>

      <template v-else-if="mode === 'merge'">
        <p
          v-if="!changing"
          class="decision__target"
        >
          <span class="decision__label">合并到</span><strong>{{ targetText }}</strong>
          <el-button
            link
            type="primary"
            @click="changing = true"
          >
            换一个
          </el-button>
        </p>
        <template v-else>
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
              {{ pathText(item.path) }}<span class="decision__hint">　{{ item.industry }} · {{ similarLabel(item.level) }}</span>
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
        <template v-if="canRename">
          <p class="decision__label">
            合并后叫什么
          </p>
          <el-radio-group
            v-model="rename"
            class="decision__choices"
          >
            <el-radio :value="false">
              沿用原名称「{{ target?.[target.length - 1] }}」
            </el-radio>
            <el-radio :value="true">
              原场景改用新名称「{{ candidate.name }}」
            </el-radio>
          </el-radio-group>
          <p
            v-if="rename"
            class="decision__hint"
          >
            编码不变；{{ impact ? `码表 ${impact.codebook_rows.toLocaleString()} 行、政策解读 ${impact.interpretation_rows.toLocaleString()} 行的名称一起改` : '正在数会改多少行…' }}
          </p>
        </template>
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

      <ul
        class="decision__what"
        aria-label="确定后会"
      >
        <li
          v-for="line in effects"
          :key="line"
        >
          {{ line }}
        </li>
      </ul>
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
        {{ mode === 'merge' ? '确定合并' : mode === 'reject' ? '驳回' : '采纳并写进码表' }}
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
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: var(--zt-space-3) var(--zt-space-4);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-surface-subtle);
  color: var(--zt-ink-700);
  font-size: 13px;
  list-style: none;
}

.decision__target {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-2);
  align-items: baseline;
}
</style>
