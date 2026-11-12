<script setup lang="ts">
withDefaults(defineProps<{ loading?: boolean; filtered?: boolean }>(), { loading: false, filtered: false })
defineEmits<{ reset: [] }>()
</script>
<template>
  <div
    v-if="loading"
    class="table-skeleton-wrap"
    role="status"
    aria-label="数据加载中"
  >
    <div
      v-for="i in 5"
      :key="i"
      class="table-skeleton-row"
    >
      <div class="skeleton-shimmer skeleton-col--short" />
      <div class="skeleton-shimmer skeleton-col--main" />
      <div class="skeleton-shimmer skeleton-col--mid" />
      <div class="skeleton-shimmer skeleton-col--short" />
      <div class="skeleton-shimmer skeleton-col--actions" />
    </div>
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
.table-skeleton-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-3);
  padding: var(--zt-space-4) var(--zt-space-3);
  width: 100%;
}
.table-skeleton-row {
  display: flex;
  align-items: center;
  gap: var(--zt-space-4);
  height: 38px;
  border-bottom: 1px solid var(--zt-divider);
}
.skeleton-shimmer {
  height: 16px;
  border-radius: 4px;
  background: var(--zt-surface-subtle);
  position: relative;
  overflow: hidden;
}
.skeleton-shimmer::after {
  content: '';
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(90deg, transparent, var(--zt-panel), transparent);
  animation: shimmer 1.5s infinite;
}
@keyframes shimmer {
  100% {
    transform: translateX(100%);
  }
}
.skeleton-col--short { flex: 0 0 80px; }
.skeleton-col--main { flex: 1 1 200px; }
.skeleton-col--mid { flex: 0 0 140px; }
.skeleton-col--actions { flex: 0 0 100px; margin-left: auto; }
.list-empty__hint { margin: 0 0 var(--zt-space-3); color: var(--zt-ink-500); font-size: 12px; line-height: 1.7; }
</style>
