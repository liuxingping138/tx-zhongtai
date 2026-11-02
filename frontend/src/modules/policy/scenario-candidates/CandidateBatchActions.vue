<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import type { ScenarioPath } from '@/api/codebook'
import { errorMessage } from '@/api/errors'
import { batchMergeCandidates, batchRejectCandidates, type BatchResult, type CandidateItem } from '@/api/scenarioCandidates'
import BatchChoiceDialog from '@/components/BatchChoiceDialog.vue'
import ScenarioPicker from '@/components/ScenarioPicker.vue'
import { REJECT_REASONS, pathText, scenarioNames } from './candidates'

/** 列表上勾选几个一起驳回、一起合并到同一个已有场景（只在当前页勾选）。被人改过、已经决定过的跳过并写明原因。 */
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
    if (out.skipped.length) {
      const lines = out.skipped.map(item => `「${item.name}」${item.reason}`).join('\n')
      await ElMessageBox.alert(`已合并 ${out.done} 个。以下没有合并：\n${lines}`, '合并结果', { type: 'warning', customClass: 'confirm-lines' })
    } else {
      ElMessage.success(`已合并 ${out.done} 个到「${pathText(scenarioNames(picked))}」`)
    }
    emit('done')
  } catch (error) {
    ElMessage.error(errorMessage(error, '没有合并成，请重试'))
  } finally {
    merging.value = false
  }
}
</script>

<template>
  <el-button
    :disabled="!checked.length"
    @click="rejectOpen = true"
  >
    批量驳回{{ checked.length ? `（${checked.length}）` : '' }}
  </el-button>
  <el-button
    :disabled="!checked.length || !canWriteCodebook"
    :title="canWriteCodebook ? '' : '合并要写行业场景码表，需要码表的管理权限'"
    @click="openMerge"
  >
    合并到同一个已有场景{{ checked.length ? `（${checked.length}）` : '' }}
  </el-button>
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
.batch-merge {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-3);
}

.batch-merge p {
  margin: 0;
}

.batch-merge ul {
  margin: 0;
  padding-left: 18px;
  color: var(--zt-ink-700);
  font-size: 13px;
  line-height: 20px;
}
</style>
