<script setup lang="ts">
import { cacheHitText, formatYuan } from './aiText'
import type { StreamStats } from './useAnswerStream'

defineProps<{ stats: StreamStats; cost: { inference: number; search: number } }>()
</script>

<template>
  <dl
    v-if="stats.model"
    class="stats-bar"
    aria-label="本次提问用量"
  >
    <div><dt>模型</dt><dd>{{ stats.model.name }}</dd></div>
    <div><dt>深度思考</dt><dd>{{ stats.thinking ? '开' : '关' }}</dd></div>
    <div><dt>输入</dt><dd>{{ stats.usage.input.toLocaleString() }} token</dd></div>
    <div v-if="stats.usage.cached > 0">
      <dt>缓存命中</dt><dd>{{ stats.usage.cached.toLocaleString() }} token（{{ cacheHitText(stats.usage.input, stats.usage.cached) }}）</dd>
    </div>
    <div><dt>输出</dt><dd>{{ stats.usage.output.toLocaleString() }} token</dd></div>
    <div v-if="stats.model.web_search">
      <dt>联网</dt><dd>{{ stats.usage.search }} 次</dd>
    </div>
    <div><dt>费用</dt><dd>{{ formatYuan(cost.inference + cost.search) }}</dd></div>
  </dl>
</template>

<style scoped>
.stats-bar { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 0; padding: 10px 18px; border-top: 1px solid var(--zt-border); font-size: 12px; color: var(--zt-ink-500); }
.stats-bar div { display: flex; gap: 6px; }
.stats-bar dd { margin: 0; color: var(--zt-ink-900); font-variant-numeric: tabular-nums; }
</style>
