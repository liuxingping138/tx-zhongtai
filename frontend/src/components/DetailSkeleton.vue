<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 是否展示顶部 Hero 个人/主体卡片（含头像槽、标题、副标和操作按钮） */
    showHero?: boolean
    /** 属性卡片分区数量，默认 1 个 */
    sections?: number
    /** 每个分区展示的键值对属性数量，默认 6 个 */
    fieldsPerSection?: number
    /** 是否展示文章/公告正文预览段落骨架 */
    showArticle?: boolean
    /** 正文段落行数，默认 6 行 */
    articleLines?: number
  }>(),
  {
    showHero: false,
    sections: 1,
    fieldsPerSection: 6,
    showArticle: false,
    articleLines: 6,
  },
)

const sectionList = computed(() => Array.from({ length: props.sections }, (_, i) => i))
const fieldList = computed(() => Array.from({ length: props.fieldsPerSection }, (_, i) => i))
const articleLineList = computed(() => Array.from({ length: props.articleLines }, (_, i) => i))

// 为段落行生成参差不齐但美观的百分比宽度，模拟真实排版
const linePercentages = ['92%', '96%', '85%', '90%', '78%', '60%', '94%', '70%']
function getLineWidth(index: number): string {
  return linePercentages[index % linePercentages.length] ?? '85%'
}
</script>

<template>
  <div
    class="detail-skeleton"
    role="status"
    aria-label="详情内容正在加载"
  >
    <!-- 顶部 Hero 区域骨架（适配用户、角色、项目大标题等） -->
    <div
      v-if="showHero"
      class="detail-skeleton__hero"
    >
      <div class="detail-skeleton__hero-avatar">
        <span class="skeleton-shimmer skeleton-circle" />
      </div>
      <div class="detail-skeleton__hero-main">
        <div class="detail-skeleton__hero-title">
          <span class="skeleton-shimmer skeleton-bar skeleton-bar--lg" />
          <span class="skeleton-shimmer skeleton-pill" />
        </div>
        <div class="detail-skeleton__hero-sub">
          <span
            class="skeleton-shimmer skeleton-bar skeleton-bar--sm"
            style="width: 140px"
          />
          <span
            class="skeleton-shimmer skeleton-bar skeleton-bar--sm"
            style="width: 100px"
          />
        </div>
      </div>
      <div class="detail-skeleton__hero-actions">
        <span class="skeleton-shimmer skeleton-pill skeleton-pill--action" />
      </div>
    </div>

    <!-- 键值对属性分组卡片 -->
    <div
      v-for="s in sectionList"
      :key="s"
      class="detail-skeleton__section"
    >
      <div class="detail-skeleton__section-head">
        <span
          class="skeleton-shimmer skeleton-bar skeleton-bar--head"
          :style="{ width: s % 2 === 0 ? '90px' : '120px' }"
        />
      </div>
      <div class="detail-skeleton__grid">
        <div
          v-for="f in fieldList"
          :key="f"
          class="detail-skeleton__field"
        >
          <span
            class="skeleton-shimmer skeleton-bar skeleton-bar--label"
            :style="{ width: f % 2 === 0 ? '60px' : '72px' }"
          />
          <span
            class="skeleton-shimmer skeleton-bar skeleton-bar--value"
            :style="{ width: f % 3 === 0 ? '140px' : f % 3 === 1 ? '180px' : '100px' }"
          />
        </div>
      </div>
    </div>

    <!-- 正文 / 公告文章段落骨架 -->
    <div
      v-if="showArticle"
      class="detail-skeleton__article"
    >
      <div class="detail-skeleton__section-head">
        <span
          class="skeleton-shimmer skeleton-bar skeleton-bar--head"
          style="width: 80px"
        />
      </div>
      <div class="detail-skeleton__lines">
        <span
          v-for="(line, idx) in articleLineList"
          :key="line"
          class="skeleton-shimmer skeleton-bar skeleton-bar--line"
          :style="{ width: getLineWidth(idx) }"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-skeleton {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  user-select: none;
}

.detail-skeleton__hero {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius, 12px);
  box-shadow: var(--zt-shadow);
}

.detail-skeleton__hero-avatar {
  flex-shrink: 0;
}

.skeleton-circle {
  width: 52px;
  height: 52px;
  border-radius: 50%;
}

.detail-skeleton__hero-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.detail-skeleton__hero-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.detail-skeleton__hero-sub {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-skeleton__hero-actions {
  flex-shrink: 0;
}

.detail-skeleton__section,
.detail-skeleton__article {
  padding: 18px 22px;
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius, 12px);
  box-shadow: var(--zt-shadow);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-skeleton__section-head {
  display: flex;
  align-items: center;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--zt-soft);
}

.detail-skeleton__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px 24px;
}

.detail-skeleton__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-skeleton__lines {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0;
}

/* 尺寸规范与 Shimmer */
.skeleton-bar {
  border-radius: 4px;
}

.skeleton-bar--lg {
  width: 180px;
  height: 22px;
}

.skeleton-bar--head {
  height: 16px;
}

.skeleton-bar--sm {
  height: 12px;
}

.skeleton-bar--label {
  height: 12px;
}

.skeleton-bar--value {
  height: 16px;
}

.skeleton-bar--line {
  height: 14px;
}

.skeleton-pill {
  width: 48px;
  height: 20px;
  border-radius: 6px;
}

.skeleton-pill--action {
  width: 80px;
  height: 32px;
  border-radius: 6px;
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
