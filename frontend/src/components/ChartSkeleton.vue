<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 图表区域高度，默认 300px 对齐 ECharts 容器 */
    height?: string
    /** 是否展示图例槽位 */
    showLegend?: boolean
    /** 是否展示模拟柱状/折线峰谷柱，默认 7 根 */
    bars?: number
  }>(),
  {
    height: '300px',
    showLegend: true,
    bars: 7,
  },
)

const barList = computed(() => Array.from({ length: props.bars }, (_, i) => i))
// 模拟柱状图的高低错落
const barHeights = ['45%', '68%', '35%', '82%', '55%', '90%', '62%', '40%', '75%']
function getBarHeight(idx: number): string {
  return barHeights[idx % barHeights.length] ?? '50%'
}
</script>

<template>
  <div
    class="chart-skeleton"
    :style="{ height }"
    role="status"
    aria-label="图表正在加载"
  >
    <!-- 图例占位 -->
    <div
      v-if="showLegend"
      class="chart-skeleton__legend"
    >
      <div class="chart-skeleton__legend-item">
        <span class="skeleton-shimmer skeleton-dot" />
        <span
          class="skeleton-shimmer skeleton-bar skeleton-bar--legend"
          style="width: 50px"
        />
      </div>
      <div class="chart-skeleton__legend-item">
        <span class="skeleton-shimmer skeleton-dot" />
        <span
          class="skeleton-shimmer skeleton-bar skeleton-bar--legend"
          style="width: 65px"
        />
      </div>
    </div>

    <!-- 图表坐标系与数据骨架模拟 -->
    <div class="chart-skeleton__canvas">
      <!-- 水平网格线 -->
      <div class="chart-skeleton__grid-line" />
      <div class="chart-skeleton__grid-line" />
      <div class="chart-skeleton__grid-line" />

      <!-- 数据柱条模拟 -->
      <div class="chart-skeleton__bars">
        <div
          v-for="b in barList"
          :key="b"
          class="chart-skeleton__bar-col"
        >
          <span
            class="skeleton-shimmer skeleton-bar-fill"
            :style="{ height: getBarHeight(b) }"
          />
          <span class="skeleton-shimmer skeleton-axis-label" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chart-skeleton {
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 16px;
  background: var(--zt-panel);
  border-radius: var(--zt-radius, 8px);
  box-sizing: border-box;
  user-select: none;
}

.chart-skeleton__legend {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  height: 24px;
  margin-bottom: 8px;
}

.chart-skeleton__legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.skeleton-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.skeleton-bar--legend {
  height: 10px;
  border-radius: 2px;
}

.chart-skeleton__canvas {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border-left: 1px solid var(--zt-soft);
  border-bottom: 1px solid var(--zt-soft);
  padding: 8px 12px 0 12px;
}

.chart-skeleton__grid-line {
  width: 100%;
  height: 1px;
  background: var(--zt-soft);
  opacity: 0.6;
}

.chart-skeleton__bars {
  position: absolute;
  top: 0;
  left: 12px;
  right: 12px;
  bottom: 0;
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  gap: 12px;
  padding-bottom: 24px;
}

.chart-skeleton__bar-col {
  flex: 1;
  max-width: 36px;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  position: relative;
}

.skeleton-bar-fill {
  width: 100%;
  border-radius: 4px 4px 0 0;
  min-height: 12px;
}

.skeleton-axis-label {
  position: absolute;
  bottom: -20px;
  width: 28px;
  height: 10px;
  border-radius: 2px;
}

/* Google M3 流光动效 */
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
