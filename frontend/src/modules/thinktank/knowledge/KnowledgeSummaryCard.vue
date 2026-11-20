<script setup lang="ts">
import { Delete, Download, Star, StarFilled, Tickets } from '@element-plus/icons-vue'
import { computed } from 'vue'

import type { KnowledgeItem } from '@/api/thinktank'
import AuditLogButton from '@/components/AuditLogButton.vue'
import { formatTime } from '@/utils/time'
import { buildKnowledgeFacts, suffixTagType } from './fields'

const props = defineProps<{
  item: KnowledgeItem
}>()

const emit = defineEmits<{
  toggleFavorite: []
  download: []
  openLogs: []
  delete: []
}>()

const facts = computed(() => buildKnowledgeFacts(props.item, formatTime))
</script>

<template>
  <section class="review__summary">
    <div class="review__title-row">
      <div class="review__heading">
        <h1 class="review__title">
          {{ item.file_name }}
        </h1>
        <el-tag
          size="small"
          :type="suffixTagType(item.file_suffix)"
        >
          {{ item.file_suffix || 'FILE' }}
        </el-tag>
        <el-tag
          size="small"
          :type="item.is_defined ? 'success' : 'warning'"
          effect="plain"
        >
          {{ item.is_defined ? '已定义' : '未定义' }}
        </el-tag>
      </div>
      <div class="review__actions">
        <el-button
          size="small"
          :icon="item.is_favorited ? StarFilled : Star"
          :type="item.is_favorited ? 'warning' : 'default'"
          plain
          @click="emit('toggleFavorite')"
        >
          {{ item.is_favorited ? '已收藏' : '收藏' }}
        </el-button>
        <el-button
          v-if="item.can_export"
          size="small"
          :icon="Download"
          @click="emit('download')"
        >
          下载源文件
        </el-button>
        <el-button
          size="small"
          :icon="Tickets"
          @click="emit('openLogs')"
        >
          日志
        </el-button>
        <AuditLogButton module="thinktank.knowledge" />
        <el-button
          v-if="item.can_edit"
          size="small"
          type="danger"
          plain
          :icon="Delete"
          @click="emit('delete')"
        >
          删除
        </el-button>
      </div>
    </div>
    <dl class="review__facts">
      <div
        v-for="fact in facts"
        :key="fact.label"
        class="review__fact"
      >
        <dt>{{ fact.label }}</dt>
        <dd>{{ fact.value }}</dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
.review__summary { padding: 12px 20px; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: 10px; display: flex; flex-direction: column; gap: 12px; }
.review__title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.review__heading { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; }
.review__title { margin: 0; font-size: 17px; font-weight: 600; color: var(--zt-ink-900); line-height: 1.4; overflow-wrap: anywhere; }
.review__actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.review__facts { margin: 0; padding-top: 8px; border-top: 1px solid var(--zt-border); display: flex; flex-wrap: wrap; gap: 8px 24px; }
.review__fact { display: flex; align-items: baseline; gap: 8px; font-size: 13px; line-height: 1.5; }
.review__fact dt { color: var(--zt-ink-500); }
.review__fact dd { margin: 0; color: var(--zt-ink-900); }
</style>
