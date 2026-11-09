<script setup lang="ts">
import { computed } from 'vue'

import { getSource, listSources, updateSource, type SourceItem } from '@/api/policy'
import AuditLogButton from '@/components/AuditLogButton.vue'
import { useDetailColumns } from '@/composables/useDetailColumns'
import { useAuthStore } from '@/stores/auth'
import PolicyReviewPage from '../shared/PolicyReviewPage.vue'
import { useReviewRecord } from '../shared/useReviewRecord'
import { EDITOR_GROUPS, FILTER_KEYS, TABLE_COLUMNS } from './fields'

const RESOURCE = 'policy.sources'
const FACTS = ['province_name', 'site_type', 'online_date', 'crawl_priority']
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))
const { columns } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)

const review = useReviewRecord<SourceItem>({
  routeName: 'policy-source-review',
  listName: 'policy-sources',
  filterKeys: FILTER_KEYS,
  groups: EDITOR_GROUPS,
  get: getSource,
  list: listSources,
  update: (row, form) => updateSource(row.id, { ...form, version: row.version }),
  canEdit: () => canWrite.value,
})

const status = computed(() => {
  const value = review.record.value?.crawler_status
  if (!value) return undefined
  if (value === '异常') return { text: value, type: 'danger' as const }
  if (value === '已爬') return { text: value, type: 'success' as const }
  return { text: value, type: 'info' as const }
})
</script>

<template>
  <PolicyReviewPage
    :review="review"
    :columns="columns"
    :groups="EDITOR_GROUPS"
    title-key="site_name"
    :facts="FACTS"
    list-label="信源管理"
    :can-write="canWrite"
    :status="status"
  >
    <template #actions>
      <AuditLogButton :module="RESOURCE" />
    </template>
  </PolicyReviewPage>
</template>
