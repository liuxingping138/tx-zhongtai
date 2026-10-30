<script setup lang="ts">
import { computed } from 'vue'

import {
  getInterpretation,
  getInterpretationContent,
  listInterpretations,
  updateInterpretation,
  type InterpretationItem,
} from '@/api/policy'
import AuditLogButton from '@/components/AuditLogButton.vue'
import { useDetailColumns } from '@/composables/useDetailColumns'
import { useAuthStore } from '@/stores/auth'
import PolicyReviewPage from '../shared/PolicyReviewPage.vue'
import { useReviewRecord } from '../shared/useReviewRecord'
import { EDITOR_GROUPS, FILTER_KEYS, TABLE_COLUMNS } from './fields'
import { useVerify } from './useVerify'

const RESOURCE = 'policy.interpretations'
const FACTS = ['industry_l1', 'opportunity_type', 'has_subsidy', 'info_level']
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))
const { columns } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)

const review = useReviewRecord<InterpretationItem>({
  routeName: 'policy-interpretation-review',
  listName: 'policy-interpretations',
  filterKeys: FILTER_KEYS,
  groups: EDITOR_GROUPS,
  get: getInterpretation,
  list: listInterpretations,
  // 政策唯一标识不在表单里，按原值提交。
  update: (row, form) => updateInterpretation(row.id, { ...form, policy_uid: row.policy_uid, version: row.version }),
  canEdit: () => canWrite.value,
})

const status = computed(() => {
  const value = review.record.value?.data_status
  if (!value) return undefined
  return { text: value, type: value === '人工验证' ? 'success' as const : 'warning' as const }
})

// 核对无误标为人工验证，接着打开下一条。
const { verifying, verify } = useVerify(review)
</script>

<template>
  <PolicyReviewPage
    :review="review"
    :columns="columns"
    :groups="EDITOR_GROUPS"
    title-key="policy_title"
    :facts="FACTS"
    list-label="政策解读列表"
    :can-write="canWrite"
    :status="status"
    :load-content="getInterpretationContent"
  >
    <template #actions="{ row, editing, ready }">
      <AuditLogButton :module="RESOURCE" />
      <el-button
        v-if="canWrite && row.data_status !== '人工验证'"
        type="primary"
        :loading="verifying"
        :disabled="editing || !ready"
        @click="verify(row)"
      >
        核对无误，标为人工验证
      </el-button>
    </template>
  </PolicyReviewPage>
</template>
