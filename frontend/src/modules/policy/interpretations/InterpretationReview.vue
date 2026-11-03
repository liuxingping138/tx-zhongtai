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
import ScenarioInlineCard from '../scenario-candidates/ScenarioInlineCard.vue'

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

// 这一行的场景还在新增场景审核里待审、或要改成码表里的：「行业与场景」页签上点个小圆点，停在别的分组也知道
const SCENARIO_GROUP = '行业与场景'
const SCENARIO_MARKS: Record<string, string> = {
  待审: '这一行的场景还在新增场景审核里待审',
  行业不在码表: '这一行的行业不在码表里，要改成码表里的',
  场景不完整: '这一行的场景不完整，要改成码表里的',
}
const tabMarks = computed((): Record<string, string> => {
  const mark = SCENARIO_MARKS[review.record.value?.scenario_state ?? '']
  return mark ? { [SCENARIO_GROUP]: mark } : {}
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
    :tab-marks="tabMarks"
  >
    <template #section-extra="{ section, row }">
      <ScenarioInlineCard
        v-if="section === SCENARIO_GROUP"
        :row="row"
        @changed="review.load"
      />
    </template>
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
