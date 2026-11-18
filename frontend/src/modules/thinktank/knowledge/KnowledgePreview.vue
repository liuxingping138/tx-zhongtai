<script setup lang="ts">
import { ArrowLeft, Download, Star, StarFilled, Tickets } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { downloadBlob } from '@/api/download'
import { errorMessage } from '@/api/errors'
import { fetchFilterOptions } from '@/api/filterOptions'
import {
  downloadKnowledgeBlob,
  favoriteKnowledge,
  fetchKnowledgeContentBlob,
  previewKnowledge,
  unfavoriteKnowledge,
  type KnowledgeItem,
} from '@/api/thinktank'
import { useAuthStore } from '@/stores/auth'
import KnowledgeLogsDrawer from './KnowledgeLogsDrawer.vue'
import KnowledgeMetaCard from './KnowledgeMetaCard.vue'
import { parseContentDispositionFilename, suffixTagType } from './fields'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const fileId = computed(() => String(route.params.id || ''))
const loading = ref(true)
const item = ref<KnowledgeItem | null>(null)
const previewMode = ref<'pdf' | 'text' | 'summary'>('summary')
const previewText = ref('')
const pdfUrl = ref('')
const provinces = ref<string[]>([])
const logsOpen = ref(false)

const watermarkText = computed(() => auth.user?.display_name || auth.user?.username || '智库预览')

async function loadContent(mode: 'pdf' | 'text' | 'summary', hasBinary: boolean) {
  if (pdfUrl.value) {
    URL.revokeObjectURL(pdfUrl.value)
    pdfUrl.value = ''
  }
  if (!hasBinary || (mode !== 'pdf' && mode !== 'text')) return
  try {
    const resp = await fetchKnowledgeContentBlob(fileId.value)
    if (mode === 'pdf') {
      pdfUrl.value = URL.createObjectURL(resp.data)
    } else {
      previewText.value = await resp.data.text()
    }
  } catch {
    previewMode.value = 'summary'
  }
}

async function loadPage() {
  loading.value = true
  try {
    const [res, opts] = await Promise.all([
      previewKnowledge(fileId.value),
      fetchFilterOptions('/thinktank/knowledge').catch(() => null),
    ])
    item.value = res.item
    previewMode.value = res.preview.mode
    previewText.value = res.preview.content_text
    if (opts?.options?.prov_name?.items) provinces.value = opts.options.prov_name.items
    await loadContent(res.preview.mode, res.preview.has_binary)
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载文件预览失败'))
  } finally {
    loading.value = false
  }
}

async function onToggleFavorite() {
  if (!item.value) return
  try {
    const res = item.value.is_favorited
      ? await unfavoriteKnowledge(item.value.id)
      : await favoriteKnowledge(item.value.id)
    item.value.is_favorited = res.is_favorited
    ElMessage.success(res.is_favorited ? '收藏成功' : '已取消收藏')
  } catch (error) {
    ElMessage.error(errorMessage(error, '收藏操作失败'))
  }
}

async function onDownload() {
  if (!item.value) return
  try {
    const resp = await downloadKnowledgeBlob(item.value.id)
    const filename = parseContentDispositionFilename(resp.headers?.['content-disposition'], item.value.file_name)
    downloadBlob(resp.data, filename)
    ElMessage.success('下载已开始')
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败'))
  }
}

onBeforeUnmount(() => {
  if (pdfUrl.value) URL.revokeObjectURL(pdfUrl.value)
})

onMounted(() => {
  void loadPage()
})
</script>

<template>
  <div
    v-loading="loading"
    class="preview-page"
  >
    <header class="preview-header">
      <div class="preview-title-group">
        <el-button
          text
          :icon="ArrowLeft"
          @click="router.back()"
        >
          返回
        </el-button>
        <el-tag
          v-if="item"
          size="small"
          :type="suffixTagType(item.file_suffix)"
        >
          {{ item.file_suffix || 'FILE' }}
        </el-tag>
        <h2 class="preview-filename">
          {{ item?.file_name || '文件预览' }}
        </h2>
        <span
          v-if="item"
          class="preview-size"
        >({{ item.file_size_display }})</span>
      </div>
      <div
        v-if="item"
        class="preview-actions"
      >
        <el-button
          :icon="item.is_favorited ? StarFilled : Star"
          @click="onToggleFavorite"
        >
          {{ item.is_favorited ? '取消收藏' : '收藏' }}
        </el-button>
        <el-button
          v-if="item.can_export"
          :icon="Download"
          @click="onDownload"
        >
          下载
        </el-button>
        <el-button
          :icon="Tickets"
          @click="logsOpen = true"
        >
          日志
        </el-button>
      </div>
    </header>

    <div
      v-if="item"
      class="preview-body"
    >
      <KnowledgeMetaCard
        :item="item"
        :provinces="provinces"
        @updated="item = $event"
      />
      <div class="viewer-card">
        <div
          class="viewer-watermark"
          aria-hidden="true"
        >
          {{ watermarkText }}
        </div>
        <iframe
          v-if="previewMode === 'pdf' && pdfUrl"
          :src="pdfUrl"
          class="viewer-frame"
          title="文档在线预览"
        />
        <pre
          v-else
          class="viewer-text"
        >{{ previewText }}</pre>
        <div
          v-if="previewMode === 'summary' && item.can_export"
          class="viewer-hint"
        >
          当前文件格式（{{ item.file_suffix }}）暂不支持网页直出渲染，可点击右上角「下载」查看原文件。
        </div>
      </div>
    </div>

    <KnowledgeLogsDrawer
      v-model="logsOpen"
      :file-id="fileId"
      :file-name="item?.file_name || ''"
    />
  </div>
</template>

<style scoped>
.preview-page { display: flex; flex-direction: column; gap: 16px; height: calc(100vh - 96px); }
.preview-header {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 12px 16px; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: 8px;
}
.preview-title-group { display: flex; align-items: center; gap: 10px; min-width: 0; }
.preview-filename { margin: 0; font-size: 16px; font-weight: 600; color: var(--zt-ink-900); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.preview-size { font-size: 12px; color: var(--zt-ink-400); flex-shrink: 0; }
.preview-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.preview-body { display: grid; grid-template-columns: 360px 1fr; gap: 16px; flex: 1; min-height: 0; }
.viewer-card {
  position: relative; background: var(--zt-panel); border: 1px solid var(--zt-border);
  border-radius: 8px; overflow: hidden; display: flex; flex-direction: column;
}
.viewer-watermark {
  position: absolute; top: 16px; right: 20px; pointer-events: none; z-index: 2;
  font-size: 13px; color: var(--zt-ink-400); opacity: 0.45; user-select: none;
}
.viewer-frame { width: 100%; height: 100%; border: 0; flex: 1; }
.viewer-text { margin: 0; padding: 24px; white-space: pre-wrap; font-family: inherit; color: var(--zt-ink-900); line-height: 1.7; overflow: auto; flex: 1; }
.viewer-hint { padding: 10px 24px; font-size: 12px; color: var(--zt-ink-500); background: var(--zt-surface-subtle); border-top: 1px solid var(--zt-divider); }
@media (max-width: 960px) {
  .preview-page { height: auto; }
  .preview-body { grid-template-columns: 1fr; }
  .viewer-frame { min-height: 480px; }
}
</style>
