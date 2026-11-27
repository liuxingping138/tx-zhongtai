<script setup lang="ts">
import { Delete, Download, Star, StarFilled } from '@element-plus/icons-vue'

defineProps<{
  unfavoritedCount: number
  favoritedCount: number
  downloadableCount: number
  deletableCount: number
  canDelete: boolean
  busy: boolean
}>()

const emit = defineEmits<{
  favorite: []
  unfavorite: []
  download: []
  delete: []
}>()
</script>

<template>
  <el-button
    v-if="unfavoritedCount"
    :icon="Star"
    :loading="busy"
    @click="emit('favorite')"
  >
    批量收藏（{{ unfavoritedCount }}）
  </el-button>
  <el-button
    v-if="favoritedCount"
    :icon="StarFilled"
    :loading="busy"
    @click="emit('unfavorite')"
  >
    批量取消收藏（{{ favoritedCount }}）
  </el-button>
  <el-button
    v-if="downloadableCount"
    :icon="Download"
    :loading="busy"
    @click="emit('download')"
  >
    批量下载（{{ downloadableCount }}）
  </el-button>
  <el-button
    v-if="canDelete && deletableCount"
    type="danger"
    plain
    :icon="Delete"
    :loading="busy"
    @click="emit('delete')"
  >
    批量删除（{{ deletableCount }}）
  </el-button>
</template>
