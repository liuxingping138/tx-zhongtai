<script setup lang="ts">
import { Download, StarFilled, View } from '@element-plus/icons-vue'
import { RouterLink } from 'vue-router'

import type { ThinktankFavoriteEntry } from '@/api/thinktank'
import { formatTime } from '@/utils/time'
import { suffixTagType } from '../shared/options'
import { favoriteRowKey, libraryTagType } from './favorites'

defineProps<{
  items: ThinktankFavoriteEntry[]
  loading: boolean
  downloadingKeys: Set<string>
  unfavoritingKeys: Set<string>
}>()

const emit = defineEmits<{
  download: [row: ThinktankFavoriteEntry]
  unfavorite: [row: ThinktankFavoriteEntry]
}>()
</script>

<template>
  <el-table
    :data="items"
    :row-key="favoriteRowKey"
    style="width: 100%"
    class="data-table favorites-table"
    :class="{ 'is-refreshing': loading }"
  >
    <el-table-column
      label="标题"
      min-width="280"
    >
      <template #default="{ row }">
        <span class="fav-title-wrap">
          <el-icon
            class="fav-star"
            title="已收藏"
            aria-label="已收藏"
          >
            <StarFilled />
          </el-icon>
          <RouterLink
            class="fav-title"
            :to="row.preview_path"
            :title="row.title"
          >
            {{ row.title }}
          </RouterLink>
        </span>
      </template>
    </el-table-column>

    <el-table-column
      label="来源库"
      width="104"
    >
      <template #default="{ row }">
        <el-tag
          size="small"
          :type="libraryTagType(row.library)"
          disable-transitions
        >
          {{ row.library_label }}
        </el-tag>
      </template>
    </el-table-column>

    <el-table-column
      label="类别"
      width="136"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        {{ row.category_label || '—' }}
      </template>
    </el-table-column>

    <el-table-column
      label="行业"
      min-width="140"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        {{ row.industry_label || '—' }}
      </template>
    </el-table-column>

    <el-table-column
      label="区域"
      width="110"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        {{ row.region_label || '—' }}
      </template>
    </el-table-column>

    <el-table-column
      label="格式 / 大小"
      width="152"
    >
      <template #default="{ row }">
        <span class="fav-format">
          <el-tag
            size="small"
            :type="suffixTagType(row.file_suffix)"
            disable-transitions
          >
            {{ row.file_suffix || 'FILE' }}
          </el-tag>
          <span class="fav-size">{{ row.file_size_display || '—' }}</span>
        </span>
      </template>
    </el-table-column>

    <el-table-column
      label="收藏时间"
      width="178"
    >
      <template #default="{ row }">
        {{ formatTime(row.favorited_at) || '—' }}
      </template>
    </el-table-column>

    <el-table-column
      label="操作"
      width="228"
      class-name="table-action"
    >
      <template #default="{ row }">
        <div class="row-actions">
          <RouterLink
            class="row-action row-action--primary"
            :to="row.preview_path"
          >
            <el-icon
              :size="13"
              aria-hidden="true"
            >
              <View />
            </el-icon>
            <span>预览</span>
          </RouterLink>
          <button
            v-if="row.can_export"
            type="button"
            class="row-action"
            :disabled="downloadingKeys.has(favoriteRowKey(row))"
            @click="emit('download', row)"
          >
            <el-icon
              :size="13"
              aria-hidden="true"
            >
              <Download />
            </el-icon>
            <span>{{ downloadingKeys.has(favoriteRowKey(row)) ? '下载中…' : '下载' }}</span>
          </button>
          <button
            type="button"
            class="row-action row-action--danger"
            :disabled="unfavoritingKeys.has(favoriteRowKey(row))"
            @click="emit('unfavorite', row)"
          >
            取消收藏
          </button>
        </div>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.fav-title-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  min-width: 0;
}
.fav-star { color: var(--zt-warning); font-size: 14px; flex-shrink: 0; }
.fav-title {
  color: var(--zt-ink-900);
  font-weight: 500;
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fav-title:hover { color: var(--zt-blue-600); text-decoration: underline; }
.fav-format { display: inline-flex; align-items: center; gap: 8px; }
.fav-size { color: var(--zt-ink-500); font-size: 12px; font-variant-numeric: tabular-nums; }
.favorites-table.is-refreshing { opacity: 0.65; pointer-events: none; transition: opacity 0.2s ease; }
</style>
