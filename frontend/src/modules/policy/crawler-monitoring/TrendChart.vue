<script setup lang="ts">
import { computed } from 'vue'

/**
 * 日采集量折线。内联 SVG 手绘，不引图表库：全站只有这一处折线，
 * 为它引入 echarts 会把主包再撑大一截，而这里的需求只是一条线加坐标。
 */
const props = defineProps<{
  points: { date: string; rows: number }[]
  height?: number
}>()

const VIEW_W = 960
const viewH = computed(() => props.height ?? 220)
const PAD = { top: 16, right: 12, bottom: 28, left: 52 }

const maxRows = computed(() => Math.max(1, ...props.points.map((p) => p.rows)))

const plot = computed(() => ({
  w: VIEW_W - PAD.left - PAD.right,
  h: viewH.value - PAD.top - PAD.bottom,
}))

function x(index: number): number {
  const count = props.points.length
  if (count <= 1) return PAD.left
  return PAD.left + (index / (count - 1)) * plot.value.w
}

function y(rows: number): number {
  return PAD.top + plot.value.h - (rows / maxRows.value) * plot.value.h
}

const linePath = computed(() =>
  props.points.map((point, index) => `${index === 0 ? 'M' : 'L'}${x(index)},${y(point.rows)}`).join(' '),
)

const areaPath = computed(() => {
  if (props.points.length === 0) return ''
  const bottom = PAD.top + plot.value.h
  return `${linePath.value} L${x(props.points.length - 1)},${bottom} L${PAD.left},${bottom} Z`
})

/** Y 轴只画 0 / 中位 / 峰值三条，避免密集网格线压住数据。 */
const yTicks = computed(() => [0, Math.round(maxRows.value / 2), maxRows.value])

/** X 轴最多 6 个日期标签，点多了就抽稀，否则中文日期会叠在一起。 */
const xTicks = computed(() => {
  const count = props.points.length
  if (count === 0) return []
  const step = Math.max(1, Math.ceil(count / 6))
  return props.points
    .map((point, index) => ({ index, label: point.date.slice(5), rows: point.rows }))
    .filter((item) => item.index % step === 0 || item.index === count - 1)
})

const lowest = computed(() => {
  if (props.points.length === 0) return null
  return props.points.reduce((min, point) => (point.rows < min.rows ? point : min))
})
</script>

<template>
  <div class="trend-chart">
    <svg
      :viewBox="`0 0 ${VIEW_W} ${viewH}`"
      preserveAspectRatio="none"
      role="img"
      :aria-label="`近 ${points.length} 天日采集量趋势，峰值 ${maxRows} 条`"
    >
      <g class="grid">
        <line
          v-for="tick in yTicks"
          :key="`g-${tick}`"
          :x1="PAD.left"
          :x2="VIEW_W - PAD.right"
          :y1="y(tick)"
          :y2="y(tick)"
        />
      </g>
      <path
        v-if="areaPath"
        class="area"
        :d="areaPath"
      />
      <path
        v-if="linePath"
        class="line"
        :d="linePath"
      />
      <circle
        v-for="(point, index) in points"
        :key="point.date"
        class="dot"
        :class="{ 'dot-low': lowest && point.date === lowest.date && points.length > 2 }"
        :cx="x(index)"
        :cy="y(point.rows)"
        r="2.5"
      >
        <title>{{ point.date }}：{{ point.rows.toLocaleString() }} 条</title>
      </circle>
      <g class="axis-y">
        <text
          v-for="tick in yTicks"
          :key="`t-${tick}`"
          :x="PAD.left - 8"
          :y="y(tick) + 4"
          text-anchor="end"
        >{{ tick.toLocaleString() }}</text>
      </g>
      <g class="axis-x">
        <text
          v-for="tick in xTicks"
          :key="`x-${tick.index}`"
          :x="x(tick.index)"
          :y="viewH - 8"
          text-anchor="middle"
        >{{ tick.label }}</text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.trend-chart svg {
  width: 100%;
  height: v-bind('`${viewH}px`');
  display: block;
}

.grid line {
  stroke: var(--zt-border);
  stroke-width: 1;
}

.area {
  fill: var(--zt-blue-600);
  opacity: 0.08;
}

.line {
  fill: none;
  stroke: var(--zt-blue-600);
  stroke-width: 2;
  stroke-linejoin: round;
}

.dot {
  fill: var(--zt-blue-600);
  opacity: 0.55;
}

.dot-low {
  fill: #c45656;
  opacity: 1;
}

.axis-y text,
.axis-x text {
  fill: var(--zt-ink-500);
  font-size: 12px;
}
</style>
