<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import type { ScenarioPath } from '@/api/codebook'
import { errorMessage } from '@/api/errors'
import { batchAdoptCandidates, batchMergeCandidates, batchRejectCandidates, type BatchResult, type CandidateItem } from '@/api/scenarioCandidates'
import BatchChoiceDialog from '@/components/BatchChoiceDialog.vue'
import ScenarioPicker from '@/components/ScenarioPicker.vue'
import { REJECT_REASONS, levelTag, pathText, scenarioNames, whereText } from './candidates'

/** 列表上勾选几个一起采纳、一起驳回、一起合并到同一个已有场景（只在当前页勾选）。被人改过、已经决定过的跳过并写明原因。 */
const props = defineProps<{ checked: CandidateItem[]; canWriteCodebook: boolean }>()
const emit = defineEmits<{ done: [] }>()

const items = computed(() => props.checked.map(row => ({ id: row.id, version: row.version })))
const rows = computed(() => props.checked.reduce((sum, row) => sum + row.row_count, 0))
const REASON_HINTS: Record<string, string> = {
  不是信息化场景: '政策说的不是信息化建设的事，不该进行业场景码表。',
  '太细，属于已有场景的一部分': '是某个已有场景里的一项具体工作，不单独成一个场景。',
  说法不对: '名称、层级写得不对，码表里不该有这样的场景。',
  其他: '其他原因。',
}
const choices = REJECT_REASONS.map(reason => ({ value: reason, label: reason, hint: REASON_HINTS[reason] ?? '' }))

function result(out: BatchResult, verb: string) {
  return {
    message: `已${verb} ${out.done} 个`,
    skipped: out.skipped.map(item => ({ reason: `「${item.name}」${item.reason}`, count: 1 })),
  }
}

const rejectOpen = ref(false)
async function reject(reason: string) {
  return result(await batchRejectCandidates({ items: items.value, reason }), '驳回')
}

/** 批量采纳要写码表：确认框里把每个要写进去的场景都列出来，看清了再提交 */
const adoptOpen = ref(false)
const adopting = ref(false)
async function finish(out: BatchResult, verb: string, success: string) {
  if (out.skipped.length) {
    const lines = out.skipped.map(item => `「${item.name}」${item.reason}`).join('\n')
    await ElMessageBox.alert(`已${verb} ${out.done} 个。以下没有${verb}：\n${lines}`, `${verb}结果`, { type: 'warning', customClass: 'confirm-lines' })
  } else {
    ElMessage.success(success)
  }
  emit('done')
}
async function adopt() {
  if (adopting.value) return
  adopting.value = true
  try {
    const out = await batchAdoptCandidates({ items: items.value })
    adoptOpen.value = false
    await finish(out, '采纳', `已采纳 ${out.done} 个，写进了行业场景码表`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '没有采纳成，请重试'))
  } finally {
    adopting.value = false
  }
}

const mergeOpen = ref(false)
const target = ref<ScenarioPath | null>(null)
const merging = ref(false)
function openMerge() {
  target.value = null
  mergeOpen.value = true
}
async function merge() {
  const picked = target.value
  if (!picked || merging.value) return
  merging.value = true
  try {
    const out = await batchMergeCandidates({ items: items.value, target: scenarioNames(picked) })
    mergeOpen.value = false
    await finish(out, '合并', `已合并 ${out.done} 个到「${pathText(scenarioNames(picked))}」`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '没有合并成，请重试'))
  } finally {
    merging.value = false
  }
}
</script>

<template>
  <!-- 勾选了才出现：平时工具栏只有页签和操作记录，不摆一排灰按钮 -->
  <span
    v-if="checked.length"
    class="batch__picked"
    role="group"
    :aria-label="`已选 ${checked.length} 个，批量处理`"
  >
    <span class="batch__count">已选 {{ checked.length }} 个：</span>
    <el-button
      :disabled="!canWriteCodebook"
      :title="canWriteCodebook ? '' : '采纳要写行业场景码表，需要码表的管理权限'"
      @click="adoptOpen = true"
    >
      批量采纳
    </el-button>
    <el-button
      :disabled="!canWriteCodebook"
      :title="canWriteCodebook ? '' : '合并要写行业场景码表，需要码表的管理权限'"
      @click="openMerge"
    >
      合并到同一个已有场景
    </el-button>
    <el-button @click="rejectOpen = true">
      批量驳回
    </el-button>
  </span>
  <BatchChoiceDialog
    v-model="rejectOpen"
    title="批量驳回"
    :count="checked.length"
    prompt="驳回原因："
    :choices="choices"
    :submit="reject"
    @done="emit('done')"
  />
  <el-dialog
    v-model="adoptOpen"
    title="批量采纳为新场景"
    width="min(600px, 94vw)"
  >
    <div class="batch-merge">
      <p>这 {{ checked.length }} 个场景写进行业场景码表（{{ rows.toLocaleString() }} 行解读回填编码）：</p>
      <ol class="batch-adopt__names">
        <li
          v-for="row in checked"
          :key="row.id"
        >
          <strong>{{ row.name }}</strong><span>{{ levelTag(row) }} · {{ whereText(row) }}</span>
        </li>
      </ol>
      <ul>
        <li>各用 AI 写的名称；要改名的，取消后在那一行点「改名」</li>
        <li>码表里各新增一行，按现有规则顺延编号，标「AI 新增」；以后 AI 再写这些说法直接回填</li>
        <li>被人改过、已经决定过的跳过，写明原因</li>
      </ul>
    </div>
    <template #footer>
      <el-button @click="adoptOpen = false">
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="adopting"
        @click="adopt"
      >
        采纳这 {{ checked.length }} 个
      </el-button>
    </template>
  </el-dialog>
  <el-dialog
    v-model="mergeOpen"
    title="合并到同一个已有场景"
    width="min(560px, 94vw)"
  >
    <div class="batch-merge">
      <p>已勾选 {{ checked.length }} 个场景（{{ rows.toLocaleString() }} 行解读），都合并到：</p>
      <ScenarioPicker v-model="target" />
      <ul>
        <li>这些解读行改用选中的场景，回填它的编码；码表不新增编号</li>
        <li>这几个说法都记成它的别名，以后 AI 再写自动归过去</li>
        <li>被人改过、已经决定过的跳过，写明原因</li>
      </ul>
    </div>
    <template #footer>
      <el-button @click="mergeOpen = false">
        取消
      </el-button>
      <el-button
        type="primary"
        :disabled="!target"
        :loading="merging"
        @click="merge"
      >
        确定合并
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.batch__picked {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--zt-space-2);
  align-items: center;
}

.batch__picked .el-button + .el-button {
  margin-left: 0;
}

.batch__count {
  color: var(--zt-ink-700);
  font-size: 13px;
}

.batch-merge {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-3);
}

.batch-merge p {
  margin: 0;
}

.batch-adopt__names {
  max-height: 240px;
  margin: 0;
  padding: var(--zt-space-2) var(--zt-space-3) var(--zt-space-2) 32px;
  overflow-y: auto;
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-surface-subtle);
  line-height: 24px;
}

.batch-adopt__names span {
  margin-left: var(--zt-space-2);
  color: var(--zt-ink-500);
  font-size: 13px;
}

.batch-merge ul {
  margin: 0;
  padding-left: 18px;
  color: var(--zt-ink-700);
  font-size: 13px;
  line-height: 20px;
}
</style>
