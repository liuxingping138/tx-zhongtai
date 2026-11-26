<script setup lang="ts">
import { Delete, Download, Edit, MoreFilled, Star, StarFilled, Tickets, View } from '@element-plus/icons-vue'
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
      class="row-action row-action--primary"
      :to="detailTo"
    >
      <el-icon
        :size="13"
        aria-hidden="true"
      >
        <View />
      </el-icon>
      <span>预览</span>
    </RouterLink>
    <el-dropdown
      trigger="click"
      placement="bottom-end"
      :show-arrow="false"
      :offset="6"
      popper-class="knowledge-action-popper"
      @command="onCommand"
    >
      <button
        type="button"
        class="row-action row-action--icon"
        title="更多操作"
        :aria-label="`更多操作：${row.file_name}`"
      >
        <el-icon
          :size="14"
          aria-hidden="true"
        >
          <MoreFilled />
        </el-icon>
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-if="row.can_edit"
            command="edit"
          >
            <span class="kmenu-icon kmenu-icon--primary">
              <el-icon :size="14"><Edit /></el-icon>
            </span>
            <span class="kmenu-label">编辑标签</span>
          </el-dropdown-item>
          <el-dropdown-item
            v-if="row.can_export"
            command="download"
            :disabled="downloading"
          >
            <span class="kmenu-icon kmenu-icon--neutral">
              <el-icon :size="14"><Download /></el-icon>
            </span>
            <span class="kmenu-label">{{ downloading ? '下载中…' : '下载源文件' }}</span>
          </el-dropdown-item>
          <el-dropdown-item
            command="favorite"
            :disabled="busy"
          >
            <span class="kmenu-icon kmenu-icon--gold">
              <el-icon :size="14">
                <StarFilled v-if="row.is_favorited" />
                <Star v-else />
              </el-icon>
            </span>
            <span class="kmenu-label">{{ row.is_favorited ? '取消收藏' : '收藏资料' }}</span>
            <span
              v-if="row.is_favorited"
              class="kmenu-badge"
            >已收藏</span>
          </el-dropdown-item>
          <el-dropdown-item command="logs">
            <span class="kmenu-icon kmenu-icon--neutral">
              <el-icon :size="14"><Tickets /></el-icon>
            </span>
            <span class="kmenu-label">操作日志</span>
          </el-dropdown-item>
          <el-dropdown-item
            v-if="row.can_edit"
            command="delete"
            divided
            class="knowledge-drop-danger"
          >
            <span class="kmenu-icon kmenu-icon--danger">
              <el-icon :size="14"><Delete /></el-icon>
            </span>
            <span class="kmenu-label">删除</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<style scoped>
:global(.knowledge-action-popper .el-dropdown-menu) { min-width: 188px; }
:global(.knowledge-action-popper .kmenu-icon) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  flex-shrink: 0;
}
:global(.knowledge-action-popper .kmenu-icon--primary) {
  background: var(--el-color-primary-light-9);
  color: var(--zt-blue-600);
}
:global(.knowledge-action-popper .kmenu-icon--neutral) {
  background: var(--zt-surface-subtle);
  color: var(--zt-ink-700);
}
:global(.knowledge-action-popper .kmenu-icon--gold) {
  background: var(--zt-warning-soft);
  color: var(--zt-warning);
}
:global(.knowledge-action-popper .kmenu-icon--danger) {
  background: var(--zt-danger-soft);
  color: var(--zt-danger);
}
:global(.knowledge-action-popper .kmenu-label) { flex: 1; line-height: 1; }
:global(.knowledge-action-popper .kmenu-badge) {
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--zt-warning-soft);
  color: var(--zt-warning-text);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.2;
}
:global(.knowledge-action-popper .knowledge-drop-danger) {
  color: var(--zt-danger-text) !important;
}
:global(.knowledge-action-popper .knowledge-drop-danger:not(.is-disabled):hover),
:global(.knowledge-action-popper .knowledge-drop-danger:not(.is-disabled):focus) {
  background: var(--zt-danger-soft) !important;
  color: var(--zt-danger-text) !important;
}
</style>
