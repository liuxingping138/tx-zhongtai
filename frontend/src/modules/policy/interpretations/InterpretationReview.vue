<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  getInterpretation,
  getInterpretationContent,
  listInterpretations,
  setInterpretationsDataStatus,
  updateInterpretation,
  type InterpretationItem,
} from '@/api/policy'
import { errorMessage } from '@/api/errors'
import AuditLogButton from '@/components/AuditLogButton.vue'
import { useDetailColumns } from '@/composables/useDetailColumns'
import { useAuthStore } from '@/stores/auth'
import PolicyReviewPage from '../shared/PolicyReviewPage.vue'
import { useReviewRecord } from '../shared/useReviewRecord'
import { EDITOR_GROUPS, FILTER_KEYS, TABLE_COLUMNS } from './fields'

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

// 核对完这条就标掉，接着打开下一条；按「待验证」筛着时，标完的这条会出列表，下一条补到同一位置。
const verifying = ref(false)
async function verify(row: InterpretationItem) {
  // 翻条后新记录还没回来时，按钮旁显示的还是上一条：不能把上一条标掉。
  if (!review.ready.value || row.id !== review.record.value?.id) return
  verifying.value = true
  try {
    await setInterpretationsDataStatus([row.id], '人工验证')
    const moved = await review.advance()
    // 新增场景标完还要同步才进码表，顺带提醒入口在哪。
    const sync = row.is_new_scenario === '是' ? '。新增场景回列表点「同步新增场景」写进码表' : ''
    ElMessage.success(`${moved ? '已标为人工验证，打开了下一条' : '已标为人工验证'}${sync}`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '没能改成人工验证，请重试'))
  } finally {
    verifying.value = false
  }
}
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
