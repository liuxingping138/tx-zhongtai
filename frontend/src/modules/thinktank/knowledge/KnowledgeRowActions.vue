<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'

import type { KnowledgeItem } from '@/api/thinktank'
import ThinktankRowActions from '../shared/ThinktankRowActions.vue'

defineProps<{
  row: KnowledgeItem
  detailTo: RouteLocationRaw
  editTo: RouteLocationRaw
  busy: boolean
  downloading: boolean
}>()

const emit = defineEmits<{
  download: []
  favorite: []
  logs: []
  delete: []
}>()
</script>

<template>
  <ThinktankRowActions
    :title="row.file_name"
    :can-edit="row.can_edit"
    :can-export="row.can_export"
    :is-favorited="row.is_favorited"
    :detail-to="detailTo"
    :edit-to="editTo"
    :busy="busy"
    :downloading="downloading"
    item-noun="资料"
    @download="emit('download')"
    @favorite="emit('favorite')"
    @logs="emit('logs')"
    @delete="emit('delete')"
  />
</template>
