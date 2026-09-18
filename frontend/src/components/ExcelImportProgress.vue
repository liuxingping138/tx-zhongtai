<script setup lang="ts">
import { computed } from 'vue'

import { importUi } from '@/api/excelImport'

const title = computed(() => (importUi.stage === 'parse' ? '正在解析入库' : '正在上传文件'))
const hint = computed(() =>
  importUi.stage === 'parse'
    ? '文件已上传，正在写入数据库，请勿关闭或刷新页面'
    : '正在把 Excel 传到服务器',
)
const percentText = computed(() =>
  importUi.stage === 'parse' ? '处理中' : `${importUi.percent}%`,
)
</script>

<template>
  <teleport to="body">
    <div
      v-if="importUi.visible"
      class="import-mask"
      role="status"
      aria-live="polite"
    >
      <div class="import-card">
        <p class="import-card__title">
          {{ title }}
        </p>
        <p class="import-card__file">
          {{ importUi.fileName }}
        </p>
        <el-progress
          :percentage="importUi.stage === 'parse' ? 100 : importUi.percent"
          :indeterminate="importUi.stage === 'parse'"
          :stroke-width="14"
          striped
          striped-flow
        />
        <p class="import-card__meta">
          {{ hint }} · {{ percentText }}
        </p>
      </div>
    </div>
  </teleport>
</template>

<style scoped>
.import-mask {
  position: fixed;
  inset: 0;
  z-index: 4000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(29, 36, 51, 0.45);
}

.import-card {
  width: min(440px, calc(100vw - 32px));
  padding: 24px 28px 20px;
  border-radius: 10px;
  background: var(--zt-panel);
  box-shadow: var(--zt-shadow);
}

.import-card__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.import-card__file {
  margin: 8px 0 18px;
  color: var(--zt-ink-500);
  font-size: 13px;
  word-break: break-all;
}

.import-card__meta {
  margin: 12px 0 0;
  color: var(--zt-ink-500);
  font-size: 13px;
  line-height: 1.5;
}
</style>
