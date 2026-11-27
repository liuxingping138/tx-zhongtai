<script setup lang="ts">
import { formatGrantLevel, isThinktankDownloadCode } from '@/permissions/catalog'
import type { DiffEntry } from '@/permissions/thinktankScopes'

defineProps<{
  changes: DiffEntry[]
  names: Record<string, string>
  saving: boolean
}>()

const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ save: [] }>()

function onConfirm() {
  visible.value = false
  emit('save')
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="`待保存的 ${changes.length} 项权限修改`"
    width="560px"
    append-to-body
  >
    <div class="diff-list">
      <div
        v-for="item in changes"
        :key="item.code"
        class="diff-item"
      >
        <span>{{ item.label ?? names[item.code] ?? item.code }}</span>
        <span class="diff-item__flow">
          <el-tag
            size="small"
            type="info"
            effect="plain"
          >{{ formatGrantLevel(item.code, item.from) }}</el-tag>
          <span>→</span>
          <el-tag
            size="small"
            :type="item.to === 'NONE' ? 'info' : isThinktankDownloadCode(item.code) ? 'success' : 'primary'"
            effect="plain"
          >{{ formatGrantLevel(item.code, item.to) }}</el-tag>
        </span>
      </div>
    </div>
    <template #footer>
      <el-button @click="visible = false">
        继续调整
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        @click="onConfirm"
      >
        去保存
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.diff-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 56vh;
  overflow-y: auto;
  padding-right: 4px;
}

.diff-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--zt-surface-subtle);
  border: 1px solid var(--zt-border);
  font-size: 13px;
  color: var(--zt-ink-900);
}

.diff-item__flow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  font-size: 12px;
  color: var(--zt-ink-500);
}
</style>
