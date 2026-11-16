<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
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
const QUEUED_STATUSES = new Set(['等待重新判断类型', '待解读', '待补市场机会'])
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
// 放回待办并自动触发后台执行后，本页轮询状态，打完自动刷新字段和打标状态。
const retagOpen = ref(false)
const retagIds = ref<string[]>([])
const retagRow = ref<BaseTagItem | null>(null)
function openRetag(row: BaseTagItem) {
  retagIds.value = [row.id]
  retagRow.value = row
  retagOpen.value = true
}

let pollTimer: ReturnType<typeof setTimeout> | undefined
function stopPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = undefined
  }
}

function pollQueuedStatus() {
  stopPoll()
  const current = review.record.value
  if (!current || !QUEUED_STATUSES.has(current.ai_status) || review.editing.value) return
  pollTimer = setTimeout(() => {
    void (async () => {
      const active = review.record.value
      if (!active || active.id !== current.id || review.editing.value) return
      try {
        const fresh = await getBaseTag(active.id)
        if (fresh.version !== active.version || fresh.ai_status !== active.ai_status) {
          await review.load()
          if (!QUEUED_STATUSES.has(fresh.ai_status)) {
            ElMessage.success('重新打标已完成，已刷新最新结果')
            return
          }
        }
      } catch {
        /* 轮询网络波动忽略，下次继续 */
      }
      pollQueuedStatus()
    })()
  }, 3000)
}

watch(() => [review.record.value?.id, review.record.value?.ai_status, review.editing.value] as const, () => {
  pollQueuedStatus()
})
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
          :disabled="editing || !ready"
          @click="openRetag(row)"
        >
          重新打标
        </el-button>
      </template>
    </PolicyReviewPage>
    <RetagDialog
      v-model="retagOpen"
      :ids="retagIds"
      :row="retagRow"
      target="这条政策"
      @done="review.load"
    />
  </div>
</template>

<style scoped>
.base-tag-review-view {
  min-height: 100%;
}
</style>
