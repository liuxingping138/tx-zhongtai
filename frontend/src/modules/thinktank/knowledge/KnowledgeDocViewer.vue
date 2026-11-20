<script setup lang="ts">
import { Close, Download, FullScreen } from '@element-plus/icons-vue'
import { onBeforeUnmount, onMounted, ref } from 'vue'

import ParagraphSkeleton from '@/components/ParagraphSkeleton.vue'

defineProps<{
  collapsed: boolean
  metaCollapsed: boolean
  loading: boolean
  mode: 'pdf' | 'text' | 'summary'
  pdfUrl: string
  text: string
  fileName: string
  fileSuffix: string
  canExport: boolean
  watermark: string
}>()

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
  'update:metaCollapsed': [value: boolean]
  download: []
}>()

const fullscreen = ref(false)

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && fullscreen.value) {
    fullscreen.value = false
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <aside
    v-if="!collapsed"
    class="review__panel review__content"
    :class="{ 'is-fullscreen': fullscreen }"
  >
    <div class="review__content-bar">
      <div class="review__content-meta">
        <span class="review__content-title">{{ fullscreen ? fileName : '文档在线预览' }}</span>
        <el-tag
          size="small"
          type="info"
          effect="plain"
        >
          水印：{{ watermark }}
        </el-tag>
      </div>
      <div class="review__content-tools">
        <button
          v-if="!fullscreen"
          type="button"
          class="review__tool-btn"
          @click="emit('update:metaCollapsed', !metaCollapsed)"
        >
          {{ metaCollapsed ? '展开标签' : '收起标签' }}
        </button>
        <button
          v-if="fullscreen && canExport"
          type="button"
          class="review__tool-btn"
          @click="emit('download')"
        >
          <el-icon><Download /></el-icon>
          <span>下载</span>
        </button>
        <button
          type="button"
          class="review__tool-btn review__tool-btn--primary"
          @click="fullscreen = !fullscreen"
        >
          <el-icon>
            <Close v-if="fullscreen" />
            <FullScreen v-else />
          </el-icon>
          <span>{{ fullscreen ? '退出全屏' : '全屏预览' }}</span>
        </button>
        <button
          v-if="!fullscreen"
          type="button"
          class="review__tool-btn"
          @click="emit('update:collapsed', true)"
        >
          收起 →
        </button>
      </div>
    </div>
    <div class="review__content-body">
      <ParagraphSkeleton
        v-if="loading"
        :lines="10"
      />
      <iframe
        v-else-if="mode === 'pdf' && pdfUrl"
        :src="pdfUrl"
        class="viewer-frame"
        title="文档在线预览"
      />
      <div
        v-else
        class="viewer-text-wrap"
      >
        <div
          v-if="mode === 'summary' && canExport"
          class="viewer-hint"
        >
          当前文件格式（{{ fileSuffix }}）暂不支持网页直出渲染，可点击上方「下载源文件」查看完整原版文档。
        </div>
        <pre class="viewer-text">{{ text }}</pre>
      </div>
    </div>
  </aside>

  <button
    v-else
    type="button"
    class="review__content-rail"
    @click="emit('update:collapsed', false)"
  >
    <span>← 文档预览</span>
  </button>
</template>

<style scoped>
.review__panel { min-height: 0; display: flex; flex-direction: column; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: 10px; overflow: hidden; }
.review__content.is-fullscreen { position: fixed; inset: 0; z-index: 2000; border: 0; border-radius: 0; }
.review__content-bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 16px; border-bottom: 1px solid var(--zt-border); background: var(--zt-soft); flex-wrap: wrap; }
.review__content-meta { display: flex; align-items: center; gap: 8px; min-width: 0; }
.review__content-title { font-size: 13px; font-weight: 600; color: var(--zt-ink-700); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.review__content-tools { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.review__tool-btn { display: inline-flex; align-items: center; gap: 4px; height: 28px; padding: 0 8px; border: none; border-radius: 6px; background: transparent; color: var(--zt-ink-700); font-size: 12px; cursor: pointer; }
.review__tool-btn:hover { background: var(--zt-border); color: var(--zt-ink-900); }
.review__tool-btn--primary { color: var(--zt-blue-600); font-weight: 500; }
.review__tool-btn--primary:hover { background: var(--zt-row-hover); color: var(--zt-blue-600); }
.review__content-body { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; }
.review__content-rail { border: 1px solid var(--zt-border); border-radius: 10px; background: var(--zt-panel); color: var(--zt-ink-700); font-size: 13px; cursor: pointer; writing-mode: vertical-rl; display: flex; align-items: center; justify-content: center; letter-spacing: 2px; }
.review__content-rail:hover { color: var(--zt-blue-600); border-color: var(--zt-blue-600); }
.viewer-frame { width: 100%; height: 100%; min-height: 560px; border: 0; flex: 1; }
.viewer-text-wrap { display: flex; flex-direction: column; gap: 12px; padding: 16px 20px; flex: 1; }
.viewer-hint { padding: 8px 12px; border-radius: 8px; background: var(--zt-row-hover); color: var(--zt-blue-600); font-size: 12px; }
.viewer-text { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 14px; line-height: 1.75; color: var(--zt-ink-900); }
</style>
