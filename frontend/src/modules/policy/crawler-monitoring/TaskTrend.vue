<script setup lang="ts">
import { ref, watch } from 'vue'

import { getCrawlerTaskDetail } from '@/api/crawlerMonitoring'
import { errorMessage } from '@/api/errors'
import TrendChart from './TrendChart.vue'

const props = defineProps<{ siteCode: string; tag: string }>()

const loading = ref(false)
const error = ref('')
const series = ref<{ date: string; rows: number }[]>([])

async function load() {
  loading.value = true
  error.value = ''
  series.value = []
  try {
    const result = await getCrawlerTaskDetail({ site_code: props.siteCode, tag: props.tag, days: 90 })
    series.value = [...result.series].reverse()
  } catch (err) {
    error.value = errorMessage(err, '加载采集趋势失败')
  } finally {
    loading.value = false
  }
}

watch(() => [props.siteCode, props.tag], load, { immediate: true })
</script>

<template>
  <section
    v-loading="loading"
    class="task-trend"
  >
    <h3>近 90 天采集量</h3>
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      show-icon
      :title="error"
    >
      <el-button
        link
        type="primary"
        @click="load"
      >
        重试
      </el-button>
    </el-alert>
    <TrendChart
      v-else-if="series.length > 0"
      :points="series"
      :height="170"
    />
    <p
      v-else-if="!loading"
      class="empty"
    >
      该任务近 90 天没有采集到数据。
    </p>
  </section>
</template>

<style scoped>
.task-trend {
  margin-top: var(--zt-space-6);
  min-height: 120px;
}

.task-trend h3 {
  margin: 0 0 var(--zt-space-3);
  font-size: 14px;
  font-weight: 600;
  color: var(--zt-ink-900);
}

.empty {
  margin: 0;
  color: var(--zt-ink-500);
  font-size: 13px;
}
</style>
