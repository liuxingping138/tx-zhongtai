<script setup lang="ts">
import { computed, ref } from 'vue'

import { getBaseTag, getBaseTagContent, listBaseTags, updateBaseTag, type BaseTagItem } from '@/api/policy'
import AuditLogButton from '@/components/AuditLogButton.vue'
import { useDetailColumns } from '@/composables/useDetailColumns'
import { useAuthStore } from '@/stores/auth'
import PolicyReviewPage from '../shared/PolicyReviewPage.vue'
import { useReviewRecord } from '../shared/useReviewRecord'
import { EDITOR_GROUPS, FILTER_KEYS, TABLE_COLUMNS } from './fields'
import RetagDialog from './RetagDialog.vue'

const RESOURCE = 'policy.base_tags'
const FACTS = ['province_name', 'policy_types', 'issued_at', 'need_interpret']
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
  update: (row, form) => updateBaseTag(row.id, { ...form, version: row.version }),
  canEdit: () => canWrite.value,
})

// 重新打标：和列表页勾选后的同一个对话框，对象是当前这条。点开时记下是哪条，翻条也不会弄错；
// 放回待办后重新取这一条，「打标状态」马上变成排队中。只有 AI 打标的行有打标状态，手工录入的不显示。
const retagOpen = ref(false)
const retagIds = ref<string[]>([])
function openRetag(row: BaseTagItem) {
  retagIds.value = [row.id]
  retagOpen.value = true
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
    target="这条政策"
    @done="review.load"
  />
</template>
