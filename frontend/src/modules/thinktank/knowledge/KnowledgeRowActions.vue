<script setup lang="ts">
import { ArrowDown, Delete, Download, Edit, Star, StarFilled, Tickets } from '@element-plus/icons-vue'
import { RouterLink, useRouter, type RouteLocationRaw } from 'vue-router'

import type { KnowledgeItem } from '@/api/thinktank'

const props = defineProps<{
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

const router = useRouter()

const handlers: Record<string, () => void> = {
  edit: () => void router.push(props.editTo),
  download: () => emit('download'),
  favorite: () => emit('favorite'),
  logs: () => emit('logs'),
  delete: () => emit('delete'),
}

function onCommand(command: string) {
  handlers[command]?.()
}
</script>

<template>
  <div class="row-actions">
    <RouterLink
      class="row-action"
      :to="detailTo"
    >
      预览
    </RouterLink>
    <el-dropdown
      trigger="click"
      placement="bottom-end"
      @command="onCommand"
    >
      <button
        type="button"
        class="row-action"
        :aria-label="`更多操作：${row.file_name}`"
      >
        更多
        <el-icon :size="12">
          <ArrowDown />
        </el-icon>
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-if="row.can_edit"
            command="edit"
            :icon="Edit"
          >
            编辑标签
          </el-dropdown-item>
          <el-dropdown-item
            v-if="row.can_export"
            command="download"
            :icon="Download"
            :disabled="downloading"
          >
            {{ downloading ? '下载中…' : '下载源文件' }}
          </el-dropdown-item>
          <el-dropdown-item
            command="favorite"
            :icon="row.is_favorited ? StarFilled : Star"
            :disabled="busy"
          >
            {{ row.is_favorited ? '取消收藏' : '收藏资料' }}
          </el-dropdown-item>
          <el-dropdown-item
            command="logs"
            :icon="Tickets"
          >
            操作日志
          </el-dropdown-item>
          <el-dropdown-item
            v-if="row.can_edit"
            command="delete"
            :icon="Delete"
            divided
            class="knowledge-drop-danger"
          >
            删除
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<style scoped>
:global(.knowledge-drop-danger) { color: var(--zt-danger-text) !important; }
</style>
