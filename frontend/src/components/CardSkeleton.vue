<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 渲染卡片数量，默认 1 张 */
    count?: number
    /** 网格列数，不传则自适应 */
    columns?: number
    /** 卡片风格：kpi 指标卡（含大数字与进度占位）或 simple 普通卡片 */
    variant?: 'kpi' | 'simple'
    /** 最小高度，默认 104px 对齐系统指标卡 */
    minHeight?: string
  }>(),
  {
    count: 1,
    columns: undefined,
    variant: 'kpi',
    minHeight: '104px',
  },
)

const cardList = computed(() => Array.from({ length: props.count }, (_, i) => i))
</script>

<template>
  <div
    v-if="count > 1"
    class="card-skeleton-grid"
    :style="{ gridTemplateColumns: columns ? `repeat(${columns}, minmax(0, 1fr))` : undefined }"
    role="status"
    aria-label="卡片数据正在加载"
  >
    <div
      v-for="i in cardList"
      :key="i"
      class="card-skeleton"
      :class="{ 'card-skeleton--simple': variant === 'simple' }"
      :style="{ minHeight }"
    >
      <div class="card-skeleton__head">
        <span
          class="skeleton-shimmer card-skeleton__title"
          :style="{ width: i % 2 === 0 ? '72px' : '88px' }"
        />
        <span class="skeleton-shimmer card-skeleton__pill" />
      </div>
      <div class="card-skeleton__body">
        <span
          class="skeleton-shimmer card-skeleton__value"
          :style="{ width: i % 2 === 0 ? '110px' : '136px' }"
        />
      </div>
      <div class="card-skeleton__foot">
        <span
          v-if="variant === 'kpi'"
          class="skeleton-shimmer card-skeleton__progress"
        />
        <span
          v-else
          class="skeleton-shimmer card-skeleton__sub"
          :style="{ width: i % 2 === 0 ? '65%' : '80%' }"
        />
      </div>
    </div>
  </div>

  <div
    v-else
    class="card-skeleton"
    :class="{ 'card-skeleton--simple': variant === 'simple' }"
    :style="{ minHeight }"
    role="status"
    aria-label="卡片数据正在加载"
  >
    <div class="card-skeleton__head">
      <span class="skeleton-shimmer card-skeleton__title" />
      <span class="skeleton-shimmer card-skeleton__pill" />
    </div>
    <div class="card-skeleton__body">
      <span class="skeleton-shimmer card-skeleton__value" />
    </div>
    <div class="card-skeleton__foot">
      <span
        v-if="variant === 'kpi'"
        class="skeleton-shimmer card-skeleton__progress"
      />
      <span
        v-else
        class="skeleton-shimmer card-skeleton__sub"
      />
    </div>
  </div>
</template>

<style scoped>
.card-skeleton-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  width: 100%;
}

.card-skeleton {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 16px;
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: 12px;
  box-shadow: var(--zt-shadow);
  box-sizing: border-box;
  user-select: none;
}

.card-skeleton__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-skeleton__title {
  width: 80px;
  height: 14px;
  border-radius: 4px;
}

.card-skeleton__pill {
  width: 44px;
  height: 18px;
  border-radius: 6px;
}

.card-skeleton__body {
  display: flex;
  align-items: center;
  padding: 4px 0;
}

.card-skeleton__value {
  width: 120px;
  height: 26px;
  border-radius: 4px;
}

.card-skeleton__foot {
  display: flex;
  align-items: center;
  width: 100%;
}

.card-skeleton__progress {
  width: 100%;
  height: 6px;
  border-radius: 999px;
}

.card-skeleton__sub {
  width: 75%;
  height: 12px;
  border-radius: 3px;
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
