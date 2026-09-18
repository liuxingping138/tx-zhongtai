<script setup lang="ts">
withDefaults(defineProps<{ loading?: boolean; filtered?: boolean }>(), { loading: false, filtered: false })
defineEmits<{ reset: [] }>()
</script>
<template>
  <div
    v-if="loading"
    class="list-empty"
    role="status"
  >
    正在加载数据…
  </div>
  <el-empty
    v-else
    :image-size="64"
    :description="filtered ? '没有匹配的结果' : '暂无记录'"
  >
    <p class="list-empty__hint">
      {{ filtered ? '试试调整筛选条件，或清除条件查看全部记录。' : '当前还没有可展示的记录。' }}
    </p>
    <el-button
      v-if="filtered"
      @click="$emit('reset')"
    >
      清除筛选
    </el-button>
  </el-empty>
</template>
<style scoped>
.list-empty { padding: 48px 16px; color: var(--zt-ink-500); }
.list-empty__hint { margin: 0 0 14px; color: var(--zt-ink-500); font-size: 12px; line-height: 1.7; }
</style>
