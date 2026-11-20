<script setup lang="ts">
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteUpdate, useRoute, useRouter, type RouteLocationRaw } from 'vue-router'

import { downloadBlob } from '@/api/download'
import { errorMessage } from '@/api/errors'
import { fetchFilterOptions } from '@/api/filterOptions'
import {
  deleteKnowledge,
  downloadKnowledgeBlob,
  favoriteKnowledge,
  fetchKnowledgeContentBlob,
  getKnowledgeAccess,
  listKnowledge,
  previewKnowledge,
  unfavoriteKnowledge,
  type KnowledgeAccessSummary,
  type KnowledgeItem,
} from '@/api/thinktank'
import DetailSkeleton from '@/components/DetailSkeleton.vue'
import { listQuery, parseReviewQuery, reviewQuery } from '@/modules/policy/shared/reviewQuery'
import { useAuthStore } from '@/stores/auth'
import KnowledgeDocViewer from './KnowledgeDocViewer.vue'
import KnowledgeLogsDrawer from './KnowledgeLogsDrawer.vue'
import KnowledgeMetaCard from './KnowledgeMetaCard.vue'
import KnowledgeSummaryCard from './KnowledgeSummaryCard.vue'
import { fetchNeighbors } from './neighborWindow'
import { openRecord } from './previewFlow'
import { isOfficeFile, useKnowledgeContent } from './useKnowledgeContent'
import { usePreviewPanels } from './usePreviewPanels'
import { FILTER_KEYS, parseContentDispositionFilename } from './fields'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const fileId = computed(() => String(route.params.id || ''))
const loading = ref(true)
const error = ref('')
const downloading = ref(false)
const item = ref<KnowledgeItem | null>(null)
const provinces = ref<string[]>([])
const accessScope = ref<KnowledgeAccessSummary | null>(null)
const logsOpen = ref(false)
const metaCardRef = ref<{ confirmDiscard: () => Promise<boolean>; startEdit: () => void } | null>(null)
const { previewCollapsed, metaCollapsed, setPreviewCollapsed, setMetaCollapsed } = usePreviewPanels(() => metaCardRef.value)
const content = useKnowledgeContent(
  fetchKnowledgeContentBlob,
  err => ElMessage.warning(errorMessage(err, '加载原文预览失败，已回退摘要视图')),
)
const { loading: contentLoading, mode: previewMode, text: previewText, pdfUrl } = content
const total = ref(0)
const prevId = ref<string | null>(null)
const nextId = ref<string | null>(null)
let pageSeq = 0
let neighborSeq = 0

const parsed = computed(() => parseReviewQuery(route.query, FILTER_KEYS))
const position = computed(() => parsed.value.position)
const listRoute = computed<RouteLocationRaw>(() => ({ name: 'thinktank-knowledge', query: listQuery(parsed.value) }))

function buildNeighborRoute(id: string | null, pos: number): RouteLocationRaw | null {
  if (!id || pos < 0) return null
  return { name: 'thinktank-knowledge-preview', params: { id }, query: reviewQuery(parsed.value.filters, pos, parsed.value.pageSize) }
}

const prevTarget = computed(() => (position.value !== null ? buildNeighborRoute(prevId.value, position.value - 1) : null))
const nextTarget = computed(() => (position.value !== null ? buildNeighborRoute(nextId.value, position.value + 1) : null))
const contentLoadingText = computed(() => (item.value && isOfficeFile(item.value.file_name, item.value.file_suffix)
  ? '正在转换并加载文档预览，首次打开可能需要数秒…'
  : '正在加载文档预览…'))
const watermarkText = computed(() => auth.user?.display_name || auth.user?.username || '智库预览')

async function loadNeighbors() {
  const seq = ++neighborSeq
  prevId.value = null
  nextId.value = null
  if (position.value === null) return
  try {
    const res = await fetchNeighbors(position.value, (page, pageSize) =>
      listKnowledge({ ...parsed.value.filters, page, page_size: pageSize }))
    if (seq !== neighborSeq) return
    total.value = res.total
    prevId.value = res.prevId
    nextId.value = res.nextId
  } catch { /* 邻居加载失败不影响当前详情 */ }
}

function consumeEditQuery() {
  if (route.query.edit !== '1') return
  const nextQuery = { ...route.query }
  delete nextQuery.edit
  void router.replace({ query: nextQuery })
  if (item.value?.can_edit) {
    metaCollapsed.value = false
    void nextTick(() => metaCardRef.value?.startEdit())
  }
}

/** 省份候选和可编辑范围跟着人走、不跟记录走：进页时后台取一次，不挡首屏，只有编辑标签时用得到。 */
function loadEditOptions() {
  fetchFilterOptions('/thinktank/knowledge')
    .then((opts) => { if (opts?.options?.prov_name?.items) provinces.value = opts.options.prov_name.items })
    .catch(() => { /* 取不到时省份只能手填 */ })
  getKnowledgeAccess()
    .then((scope) => { accessScope.value = scope })
    .catch(() => { /* 取不到时编辑弹层不限候选 */ })
}

// 资料信息一到就出整页，原文（PDF 下载、Office 转码可能要几秒）在右栏自己转圈。
async function loadPage() {
  const targetId = fileId.value
  if (!targetId) return
  const seq = ++pageSeq
  content.cancel()
  loading.value = true
  error.value = ''
  try {
    await openRecord({
      fetchMeta: () => previewKnowledge(targetId),
      isCurrent: () => seq === pageSeq && targetId === fileId.value,
      onMeta: (res) => {
        item.value = res.item
        loading.value = false
        consumeEditQuery()
        void loadNeighbors()
      },
      startContent: res => content.show(targetId, res.preview.mode, res.preview.content_text, res.preview.has_binary),
    })
  } catch (err) {
    if (seq === pageSeq) error.value = errorMessage(err, '加载文件预览失败')
  } finally {
    if (seq === pageSeq) loading.value = false
  }
}

async function navigateTo(target: RouteLocationRaw) { await router.push(target) }

onBeforeRouteUpdate(async (to, from) => {
  if (to.params.id !== from.params.id && metaCardRef.value && !(await metaCardRef.value.confirmDiscard())) return false
})

async function onToggleFavorite() {
  const current = item.value
  if (!current || current.id !== fileId.value) return
  try {
    const res = current.is_favorited ? await unfavoriteKnowledge(current.id) : await favoriteKnowledge(current.id)
    if (item.value?.id === current.id) item.value.is_favorited = res.is_favorited
    ElMessage.success(res.is_favorited ? '收藏成功' : '已取消收藏')
  } catch (err) { ElMessage.error(errorMessage(err, '收藏操作失败')) }
}

async function onDownload() {
  const current = item.value
  if (!current || current.id !== fileId.value || downloading.value) return
  downloading.value = true
  const hint = ElMessage.info({ message: `正在下载「${current.file_name}」，请稍候…`, duration: 0 })
  try {
    const resp = await downloadKnowledgeBlob(current.id)
    downloadBlob(resp.data, parseContentDispositionFilename(resp.headers?.['content-disposition'], current.file_name))
    ElMessage.success('文件下载已开始')
  } catch (err) { ElMessage.error(errorMessage(err, '下载失败')) } finally {
    hint.close()
    downloading.value = false
  }
}

async function onDelete() {
  const current = item.value
  if (!current || current.id !== fileId.value) return
  try {
    await ElMessageBox.confirm(`确认删除「${current.file_name}」吗？删除后将记入操作审计。`, '删除确认', { type: 'warning' })
    if (item.value?.id !== current.id || fileId.value !== current.id) return
    await deleteKnowledge(current.id)
    ElMessage.success('删除成功')
    await router.push(listRoute.value)
  } catch (err) { if (err !== 'cancel') ElMessage.error(errorMessage(err, '删除失败')) }
}

watch(() => route.params.id, () => { void loadPage() })
onBeforeUnmount(() => { pageSeq += 1; neighborSeq += 1; content.dispose() })
onMounted(() => { loadEditOptions(); void loadPage() })
</script>

<template>
  <div class="review">
    <header class="review__bar">
      <button
        type="button"
        class="review__back"
        @click="navigateTo(listRoute)"
      >
        <el-icon><ArrowLeft /></el-icon>
        <span>返回智库知识库</span>
      </button>
      <div
        v-if="position !== null && total > 0"
        class="review__pager"
      >
        <span class="review__progress">第 {{ position + 1 }} 条，共 {{ total }} 条（当前筛选）</span>
        <el-button
          size="small"
          :icon="ArrowLeft"
          :disabled="!prevTarget"
          @click="prevTarget && navigateTo(prevTarget)"
        >
          上一条
        </el-button>
        <el-button
          size="small"
          :disabled="!nextTarget"
          @click="nextTarget && navigateTo(nextTarget)"
        >
          下一条
          <el-icon class="el-icon--right">
            <ArrowRight />
          </el-icon>
        </el-button>
      </div>
    </header>

    <DetailSkeleton v-if="loading" />

    <div
      v-else-if="error"
      class="review__error"
    >
      <el-alert
        :title="error"
        type="error"
        :closable="false"
        show-icon
      />
      <el-button
        size="small"
        @click="loadPage"
      >
        重试
      </el-button>
    </div>

    <template v-else-if="item">
      <KnowledgeSummaryCard
        :item="item"
        :downloading="downloading"
        @toggle-favorite="onToggleFavorite"
        @download="onDownload"
        @open-logs="logsOpen = true"
        @delete="onDelete"
      />

      <div
        class="review__body"
        :class="{
          'is-content-collapsed': previewCollapsed,
          'is-meta-collapsed': metaCollapsed && !previewCollapsed,
        }"
      >
        <KnowledgeMetaCard
          v-if="!metaCollapsed || previewCollapsed"
          ref="metaCardRef"
          :item="item"
          :provinces="provinces"
          :editable-file-types="accessScope?.editable_file_types"
          :editable-industries="accessScope?.editable_industries"
          @updated="item = $event"
        />

        <button
          v-else
          type="button"
          class="review__meta-rail"
          @click="setMetaCollapsed(false)"
        >
          <span>标签信息 →</span>
        </button>

        <KnowledgeDocViewer
          :collapsed="previewCollapsed"
          :meta-collapsed="metaCollapsed"
          :loading="contentLoading"
          :loading-text="contentLoadingText"
          :downloading="downloading"
          :mode="previewMode"
          :pdf-url="pdfUrl"
          :text="previewText"
          :file-name="item.file_name"
          :file-suffix="item.file_suffix"
          :can-export="item.can_export"
          :watermark="watermarkText"
          @update:collapsed="setPreviewCollapsed"
          @update:meta-collapsed="setMetaCollapsed"
          @download="onDownload"
        />
      </div>

      <KnowledgeLogsDrawer
        v-model="logsOpen"
        :file-id="fileId"
        :file-name="item.file_name"
      />
    </template>
  </div>
</template>

<style scoped>
.review { flex: 1; min-height: 640px; height: calc(100vh - 96px); display: flex; flex-direction: column; gap: 12px; }
.review__bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.review__back { display: inline-flex; align-items: center; gap: 8px; padding: 4px 12px; border: 1px solid var(--zt-border); border-radius: 8px; background: var(--zt-panel); color: var(--zt-ink-700); font-size: 13px; cursor: pointer; }
.review__back:hover { color: var(--zt-blue-600); border-color: var(--zt-blue-600); }
.review__pager { display: flex; align-items: center; gap: 8px; }
.review__progress { margin-right: 4px; color: var(--zt-ink-500); font-size: 13px; }
.review__error { display: flex; align-items: center; gap: 12px; }
.review__body { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(380px, 440px) minmax(0, 1fr); gap: 12px; }
.review__body.is-content-collapsed { grid-template-columns: minmax(0, 1fr) 40px; }
.review__body.is-meta-collapsed { grid-template-columns: 40px minmax(0, 1fr); }
.review__meta-rail { border: 1px solid var(--zt-border); border-radius: 10px; background: var(--zt-panel); color: var(--zt-ink-700); font-size: 13px; cursor: pointer; writing-mode: vertical-rl; display: flex; align-items: center; justify-content: center; letter-spacing: 2px; }
.review__meta-rail:hover { color: var(--zt-blue-600); border-color: var(--zt-blue-600); }
@media (max-width: 1024px) {
  .review { height: auto; }
  .review__body, .review__body.is-content-collapsed, .review__body.is-meta-collapsed { grid-template-columns: 1fr; }
}
</style>
