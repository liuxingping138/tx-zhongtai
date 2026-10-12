<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import { echarts, type ChartOption } from './echarts'

const props = withDefaults(defineProps<{
  option: ChartOption
  /** 图形的中文文字说明，读屏软件读这一段；数值本身在提示框和下方表格里也能读到。 */
  label: string
  height?: string
}>(), { height: '280px' })

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
