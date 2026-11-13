<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 渲染段落行数，默认 4 行 */
    lines?: number
  }>(),
  {
    lines: 4,
  },
)

const lineList = computed(() => Array.from({ length: props.lines }, (_, i) => i))
const widths = ['95%', '90%', '98%', '82%', '88%', '70%', '60%']
function getLineWidth(index: number): string {
  return widths[index % widths.length] ?? '80%'
}
</script>

<template>
  <div
    class="paragraph-skeleton"
    role="status"
    aria-label="段落文本正在加载"
  >
    <span
      v-for="(line, idx) in lineList"
      :key="line"
      class="skeleton-shimmer skeleton-line"
      :style="{ width: getLineWidth(idx) }"
    />
  </div>
</template>

<style scoped>
.paragraph-skeleton {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  padding: 8px 0;
  user-select: none;
}

.skeleton-line {
  height: 14px;
  border-radius: 4px;
}

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
}

@keyframes shimmer-flow {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton-shimmer {
    animation: none !important;
    background: var(--zt-divider) !important;
  }
}
</style>
