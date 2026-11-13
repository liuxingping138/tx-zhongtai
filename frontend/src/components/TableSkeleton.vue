<script setup lang="ts">
import { computed } from 'vue'
import { getSkeletonBarWidth } from './tableSkeleton'

const props = withDefaults(
  defineProps<{
    /** 渲染骨架行数，默认 10 行 */
    rows?: number
    /** 模拟列数，默认 6 列 */
    columns?: number
    /** 是否包含操作列骨架 */
    hasActions?: boolean
    /** 是否包含首列勾选框骨架 */
    hasSelection?: boolean
  }>(),
  {
    rows: 10,
    columns: 6,
    hasActions: true,
    hasSelection: false,
  },
)

const rowList = computed(() => Array.from({ length: props.rows }, (_, i) => i))
const colList = computed(() => Array.from({ length: props.columns }, (_, i) => i))
</script>

<template>
  <div
    class="table-skeleton"
    role="status"
    aria-label="数据正在加载"
  >
    <!-- 模拟表头 -->
    <div class="table-skeleton__header">
      <div
        v-if="hasSelection"
        class="table-skeleton__th table-skeleton__th--selection"
      >
        <span class="skeleton-shimmer skeleton-box--checkbox" />
      </div>
      <div
        v-for="col in colList"
        :key="col"
        class="table-skeleton__th"
      >
        <span
          class="skeleton-shimmer skeleton-bar skeleton-bar--th"
          :style="{ width: col === 0 ? '60px' : '75px' }"
        />
      </div>
      <div
        v-if="hasActions"
        class="table-skeleton__th table-skeleton__th--action"
      >
        <span
          class="skeleton-shimmer skeleton-bar skeleton-bar--th"
          style="width: 50px"
        />
      </div>
    </div>

    <!-- 模拟数据行 -->
    <div class="table-skeleton__body">
      <div
        v-for="r in rowList"
        :key="r"
        class="table-skeleton__row"
      >
        <div
          v-if="hasSelection"
          class="table-skeleton__td table-skeleton__td--selection"
        >
          <span class="skeleton-shimmer skeleton-box--checkbox" />
        </div>
        <div
          v-for="c in colList"
          :key="c"
          class="table-skeleton__td"
        >
          <span
            class="skeleton-shimmer skeleton-bar"
            :style="{ width: getSkeletonBarWidth(r, c) }"
          />
        </div>
        <div
          v-if="hasActions"
          class="table-skeleton__td table-skeleton__td--action"
        >
          <span class="skeleton-shimmer skeleton-bar skeleton-bar--action" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.table-skeleton {
  width: 100%;
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
  overflow: hidden;
  user-select: none;
}

.table-skeleton__header {
  display: flex;
  align-items: center;
  height: 40px;
  background: var(--zt-table-head);
  border-bottom: 1px solid var(--zt-border);
  padding: 0 16px;
}

.table-skeleton__row {
  display: flex;
  align-items: center;
  height: 48px;
  background: var(--zt-panel);
  border-bottom: 1px solid var(--zt-divider);
  padding: 0 16px;
  transition: height 0.16s ease;
}

.table-skeleton__row:nth-child(even) {
  background: var(--zt-soft);
}

:global(html.zt-compact) .table-skeleton__row {
  height: 36px;
}

.table-skeleton__row:last-child {
  border-bottom: none;
}

.table-skeleton__th,
.table-skeleton__td {
  flex: 1 1 0;
  display: flex;
  align-items: center;
  padding: 0 8px;
  min-width: 0;
}

/* 首列主要信息占位稍宽，建立符合 Google M3 的视觉层级 */
.table-skeleton__th:nth-child(2),
.table-skeleton__td:nth-child(2) {
  flex: 1.8 1 0;
}

.table-skeleton__th:first-child,
.table-skeleton__td:first-child {
  padding-left: 0;
}

.table-skeleton__th--selection,
.table-skeleton__td--selection {
  flex: 0 0 44px;
  justify-content: center;
  padding: 0;
}

.table-skeleton__th--action,
.table-skeleton__td--action {
  flex: 0 0 96px;
  justify-content: flex-end;
  padding-right: 0;
}

/* Google Material 3 柔和 Shimmer 流光动效 */
.skeleton-shimmer {
  display: inline-block;
  background: linear-gradient(
    90deg,
    var(--zt-soft) 25%,
    var(--zt-divider) 37%,
    var(--zt-soft) 63%
  );
  background-size: 400% 100%;
  animation: shimmer-flow 1.6s cubic-bezier(0.4, 0, 0.2, 1) infinite;
  border-radius: 4px;
}

.skeleton-box--checkbox {
  width: 16px;
  height: 16px;
  border-radius: 3px;
}

.skeleton-bar {
  height: 14px;
  border-radius: 4px;
}

.skeleton-bar--th {
  height: 12px;
  border-radius: 3px;
}

.skeleton-bar--action {
  width: 52px;
  height: 24px;
  border-radius: 12px;
}

@keyframes shimmer-flow {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}

/* Google M3 无障碍支持：系统开启减弱动效时禁用流光 */
@media (prefers-reduced-motion: reduce) {
  .skeleton-shimmer {
    animation: none !important;
    background: var(--zt-divider) !important;
  }
}
</style>
