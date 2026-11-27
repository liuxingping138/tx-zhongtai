<script setup lang="ts">
import { listKnowledgeLogs, type KnowledgeOpLogItem } from '@/api/thinktank'
import type { Page } from '@/api/types'
import ThinktankLogsDrawer from '../shared/ThinktankLogsDrawer.vue'

type LogsFetcher = (id: string, params?: { page?: number; page_size?: number }) => Promise<Page<KnowledgeOpLogItem>>

withDefaults(
  defineProps<{
    modelValue: boolean
    fileId: string
    fileName: string
    fetchLogs?: LogsFetcher
  }>(),
  { fetchLogs: listKnowledgeLogs },
)

defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>

<template>
  <ThinktankLogsDrawer
    :model-value="modelValue"
    :file-id="fileId"
    :file-name="fileName"
    :fetch-logs="fetchLogs"
    @update:model-value="$emit('update:modelValue', $event)"
  />
</template>
