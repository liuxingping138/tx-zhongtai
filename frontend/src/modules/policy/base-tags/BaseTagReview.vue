<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getBaseTag, getBaseTagContent, listBaseTags, updateBaseTag, type BaseTagItem } from '@/api/policy'
import AuditLogButton from '@/components/AuditLogButton.vue'
import { useDetailColumns } from '@/composables/useDetailColumns'
import { useAuthStore } from '@/stores/auth'
import PolicyReviewPage from '../shared/PolicyReviewPage.vue'
import { useReviewRecord } from '../shared/useReviewRecord'
import { EDITOR_GROUPS, FILTER_KEYS, TABLE_COLUMNS, packBaseTagPatch } from './fields'
import RetagDialog from './RetagDialog.vue'

const RESOURCE = 'policy.base_tags'
const FACTS = ['province_name', '是否政策', 'policy_types', '是否信息化政策', 'issued_at', 'need_interpret']
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))
const { columns } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)

const review = useReviewRecord<BaseTagItem>({
  routeName: 'policy-base-tag-review',
  listName: 'policy-base-tags',
  filterKeys: FILTER_KEYS,
  groups: EDITOR_GROUPS,
  get: getBaseTag,
  list: listBaseTags,
  update: (row, form) => updateBaseTag(row.id, packBaseTagPatch(form, row.version)),
  canEdit: () => canWrite.value,
})

// 重新打标：和列表页勾选后的同一个对话框，对象是当前这条。点开时记下是哪条，翻条也不会弄错；
// 放回待办并自动触发后台执行后，本页轮询状态，打完自动刷新字段并弹出完成提示。
const retagOpen = ref(false)
const retagIds = ref<string[]>([])
const retagRow = ref<BaseTagItem | null>(null)
const retagging = ref(false)
function openRetag(row: BaseTagItem) {
  retagIds.value = [row.id]
  retagRow.value = row
  retagOpen.value = true
}

let pollTimer: ReturnType<typeof setInterval> | undefined
let pollRemaining = 0
let pollInFlight = false
function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = undefined
  }
  pollRemaining = 0
  pollInFlight = false
  retagging.value = false
}

function notifyOutcome(aiStatus: string) {
  if (aiStatus.includes('失败')) {
    ElMessage.error(`重新打标未成功：${aiStatus}（详见备注）`)
    return
  }
  const suffix = aiStatus ? `（当前状态：${aiStatus}）` : ''
  ElMessage.success(`重新打标已完成，已刷新最新结果${suffix}`)
}

async function onRetagDone() {
  stopPoll()
  await review.load()
  const baseline = review.record.value
  if (!baseline) return
  const baseId = baseline.id
  const baseVersion = baseline.version
  const baseStatus = baseline.ai_status
  retagging.value = true
  pollRemaining = 30
  pollTimer = setInterval(() => {
    pollRemaining -= 1
    if (pollRemaining <= 0) {
      stopPoll()
      return
    }
    void checkFresh(baseId, baseVersion, baseStatus)
  }, 3000)
}

async function checkFresh(baseId: string, baseVersion: number, baseStatus: string) {
  if (review.editing.value || pollInFlight) return
  if (review.record.value?.id !== baseId) {
    stopPoll()
    return
  }
  pollInFlight = true
  try {
    const fresh = await getBaseTag(baseId)
    if (review.record.value?.id !== baseId) {
      stopPoll()
      return
    }
    if (fresh.version !== baseVersion || fresh.ai_status !== baseStatus) {
      stopPoll()
      await review.load()
      notifyOutcome(fresh.ai_status)
    }
  } catch {
    /* 轮询网络波动忽略 */
  } finally {
    pollInFlight = false
  }
}

onBeforeUnmount(stopPoll)

// 打标状态：失败的标红，还在排队的标黄，做完的标绿；手工录入的没有状态。
const status = computed(() => {
  const value = review.record.value?.ai_status
  if (!value) return undefined
  if (value.includes('失败')) return { text: value, type: 'danger' as const }
  return { text: value, type: value === '已完成' ? 'success' as const : 'warning' as const }
})
</script>

<template>
  <div class="base-tag-review-view">
    <PolicyReviewPage
      :review="review"
      :columns="columns"
      :groups="EDITOR_GROUPS"
      title-key="policy_name"
      :facts="FACTS"
      list-label="政策基础标签表"
      :can-write="canWrite"
      :status="status"
      :load-content="getBaseTagContent"
    >
      <template #actions="{ row, editing, ready }">
        <AuditLogButton :module="RESOURCE" />
        <el-button
          v-if="canWrite && row.ai_status"
          :loading="retagging"
          :disabled="editing || !ready"
          @click="openRetag(row)"
        >
          {{ retagging ? '正在重新打标…' : '重新打标' }}
        </el-button>
      </template>
    </PolicyReviewPage>
    <RetagDialog
      v-model="retagOpen"
      :ids="retagIds"
      :row="retagRow"
      target="这条政策"
      @done="onRetagDone"
    />
  </div>
</template>

<style scoped>
.base-tag-review-view {
  min-height: 100%;
}
</style>
