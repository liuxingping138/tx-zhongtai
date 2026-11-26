<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getBaseTag, getBaseTagContent, listBaseTags, updateBaseTag, type BaseTagItem } from '@/api/policy'
import AuditLogButton from '@/components/AuditLogButton.vue'
import { useDetailColumns } from '@/composables/useDetailColumns'
import { useAuthStore } from '@/stores/auth'
import PolicyReviewPage from '../shared/PolicyReviewPage.vue'
import { useReviewRecord } from '../shared/useReviewRecord'
import { useReviewRetagPoll } from '../shared/useReviewRetagPoll'
import { EDITOR_GROUPS, FILTER_KEYS, TABLE_COLUMNS, packBaseTagPatch } from './fields'
import type { RetagSubmitOutcome } from './retag'
import RetagDialog from './RetagDialog.vue'

const RESOURCE = 'policy.base_tags'
const FACTS = ['province_name', '是否政策', 'policy_types', 'issued_at', 'need_interpret']
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
function openRetag(row: BaseTagItem) {
  retagIds.value = [row.id]
  retagRow.value = row
  retagOpen.value = true
}

function notifyOutcome(aiStatus: string) {
  if (aiStatus.includes('失败')) {
    ElMessage.error(`重新打标未成功：${aiStatus}（详见备注）`)
    return
  }
  const suffix = aiStatus ? `（当前状态：${aiStatus}）` : ''
  ElMessage.success(`重新打标已完成，已刷新最新结果${suffix}`)
}

const { retagging, start: startRetagPoll } = useReviewRetagPoll<BaseTagItem>({
  record: () => review.record.value,
  editing: () => review.editing.value,
  fetchRecord: getBaseTag,
  reload: () => review.load(),
  reloadBeforeStart: true,
  hasChanged: (fresh, base) => fresh.version !== base.version || fresh.ai_status !== base.ai_status,
  onUpdated: (fresh) => notifyOutcome(fresh.ai_status),
})

async function onRetagDone(result: RetagSubmitOutcome) {
  if (result.queued > 0 && result.triggered) {
    await startRetagPoll()
  } else if (result.queued > 0) {
    await review.load()
  }
}

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
