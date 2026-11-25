<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import { echarts, type ChartOption } from './echarts'

const props = withDefaults(defineProps<{
  option: ChartOption
  /** 图形的中文文字说明，读屏软件读这一段；数值本身在提示框和下方表格里也能读到。 */
  label: string
  height?: string
  /** 外部悬停联动高亮指定系列名（如明细表悬停高亮上方柱状图对应系列）。 */
  highlightedSeries?: string | null
  /** 外部悬停联动触发指定类目下标的提示框（如按日期明细表悬停定位上方趋势图当日）。 */
  activeDataIndex?: number | null
}>(), { height: '280px', highlightedSeries: null, activeDataIndex: null })

const emit = defineEmits<{ select: [params: { name: string; seriesName?: string; dataIndex: number }] }>()

const container = ref<HTMLDivElement>()
const chart = shallowRef<echarts.ECharts>()
let observer: ResizeObserver | undefined

onMounted(() => {
  if (!container.value) return
  chart.value = echarts.init(container.value)
  chart.value.setOption(props.option)
  chart.value.on('click', params => emit('select', {
    name: params.name,
    seriesName: params.seriesName,
    dataIndex: params.dataIndex,
  }))
  observer = new ResizeObserver(() => chart.value?.resize())
  observer.observe(container.value)
})

watch(() => props.option, option => chart.value?.setOption(option, { notMerge: true }))

watch(() => props.highlightedSeries, (next, prev) => {
  if (!chart.value) return
  if (prev) chart.value.dispatchAction({ type: 'downplay', seriesName: prev })
  if (next) chart.value.dispatchAction({ type: 'highlight', seriesName: next })
})

watch(() => props.activeDataIndex, next => {
  if (!chart.value) return
  if (typeof next === 'number' && next >= 0) {
    chart.value.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: next })
  } else {
    chart.value.dispatchAction({ type: 'hideTip' })
  }
})

onBeforeUnmount(() => {
  observer?.disconnect()
  chart.value?.dispose()
})
</script>

<template>
  <div
    ref="container"
    class="base-chart"
    role="img"
    :aria-label="label"
    :style="{ height }"
  />
</template>

<style scoped>
.base-chart { width: 100%; min-width: 0; }
</style>
