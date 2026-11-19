<script setup lang="ts">
import { ArrowLeft, ArrowRight, Delete, Download, Star, StarFilled, Tickets } from '@element-plus/icons-vue'
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
import AuditLogButton from '@/components/AuditLogButton.vue'
import DetailSkeleton from '@/components/DetailSkeleton.vue'
import { listQuery, parseReviewQuery, reviewQuery, windowAt } from '@/modules/policy/shared/reviewQuery'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import KnowledgeDocViewer from './KnowledgeDocViewer.vue'
import KnowledgeLogsDrawer from './KnowledgeLogsDrawer.vue'
import KnowledgeMetaCard from './KnowledgeMetaCard.vue'
import { buildKnowledgeFacts, FILTER_KEYS, parseContentDispositionFilename, suffixTagType } from './fields'

const COLLAPSE_KEY = 'thinktank.knowledge.previewCollapsed'
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const fileId = computed(() => String(route.params.id || ''))
const loading = ref(true)
const error = ref('')
const contentLoading = ref(false)
const item = ref<KnowledgeItem | null>(null)
const previewMode = ref<'pdf' | 'text' | 'summary'>('summary')
const previewText = ref('')
const pdfUrl = ref('')
const provinces = ref<string[]>([])
const accessScope = ref<KnowledgeAccessSummary | null>(null)
const logsOpen = ref(false)
const metaCardRef = ref<{ confirmDiscard: () => Promise<boolean>; startEdit: () => void } | null>(null)
const previewCollapsed = ref((() => {
  try { return localStorage.getItem(COLLAPSE_KEY) === '1' } catch { return false }
})())
const total = ref(0)
const prevId = ref<string | null>(null)
const nextId = ref<string | null>(null)
let pageSeq = 0
let neighborSeq = 0

function revokePdfUrl() {
  if (pdfUrl.value) { URL.revokeObjectURL(pdfUrl.value); pdfUrl.value = '' }
}

const parsed = computed(() => parseReviewQuery(route.query, FILTER_KEYS))
const position = computed(() => parsed.value.position)
const listRoute = computed<RouteLocationRaw>(() => ({ name: 'thinktank-knowledge', query: listQuery(parsed.value) }))

function buildNeighborRoute(id: string | null, pos: number): RouteLocationRaw | null {
  if (!id || pos < 0) return null
  return { name: 'thinktank-knowledge-preview', params: { id }, query: reviewQuery(parsed.value.filters, pos, parsed.value.pageSize) }
}

const prevTarget = computed(() => (position.value !== null ? buildNeighborRoute(prevId.value, position.value - 1) : null))
const nextTarget = computed(() => (position.value !== null ? buildNeighborRoute(nextId.value, position.value + 1) : null))
const watermarkText = computed(() => auth.user?.display_name || auth.user?.username || '智库预览')
const facts = computed(() => (item.value ? buildKnowledgeFacts(item.value, formatTime) : []))

function setCollapsed(val: boolean) {
  previewCollapsed.value = val
  try { localStorage.setItem(COLLAPSE_KEY, val ? '1' : '0') } catch { /* 禁用存储时忽略 */ }
}

async function applyBlobPreview(mode: 'pdf' | 'text', resp: { data: Blob; headers?: Record<string, unknown> }, seq: number) {
  const ct = String((resp.headers?.['content-type'] as string | undefined) || resp.data.type || '').toLowerCase()
  if (mode === 'pdf' && ct.includes('pdf')) {
    if (seq !== pageSeq) return
    revokePdfUrl()
    pdfUrl.value = URL.createObjectURL(resp.data)
    return
  }
  const text = await resp.data.text()
  if (seq !== pageSeq) return
  previewMode.value = mode === 'pdf' ? 'summary' : mode
  previewText.value = text
}

async function loadContent(targetId: string, mode: 'pdf' | 'text' | 'summary', hasBinary: boolean, seq: number) {
  revokePdfUrl()
  if (!hasBinary || mode === 'summary') return
  contentLoading.value = true
  try {
    const resp = await fetchKnowledgeContentBlob(targetId)
    if (seq === pageSeq) await applyBlobPreview(mode, resp, seq)
  } catch (err) {
    if (seq === pageSeq) {
      previewMode.value = 'summary'
      ElMessage.warning(errorMessage(err, '加载原文预览失败，已回退摘要视图'))
    }
  } finally {
    if (seq === pageSeq) contentLoading.value = false
  }
}

async function loadNeighbors() {
  const seq = ++neighborSeq
  prevId.value = null
  nextId.value = null
  if (position.value === null) return
  try {
    const win = windowAt(position.value)
    const res = await listKnowledge({ ...parsed.value.filters, page: win.page, page_size: win.size })
    if (seq !== neighborSeq) return
    total.value = res.total
    prevId.value = win.offset > 0 ? (res.items[win.offset - 1]?.id ?? null) : null
    nextId.value = res.items[win.offset + 1]?.id ?? null
  } catch { /* 邻居加载失败不影响当前详情 */ }
}

function consumeEditQuery() {
  if (route.query.edit !== '1') return
  const nextQuery = { ...route.query }
  delete nextQuery.edit
  void router.replace({ query: nextQuery })
  if (item.value?.can_edit) void nextTick(() => metaCardRef.value?.startEdit())
}

function applyLoadedPage(
  res: Awaited<ReturnType<typeof previewKnowledge>>,
  opts: Awaited<ReturnType<typeof fetchFilterOptions>> | null,
  scope: KnowledgeAccessSummary | null,
) {
  item.value = res.item
  previewMode.value = res.preview.mode
  previewText.value = res.preview.content_text
  if (opts?.options?.prov_name?.items) provinces.value = opts.options.prov_name.items
  if (scope) accessScope.value = scope
  consumeEditQuery()
  void loadNeighbors()
}

async function loadPage() {
  const targetId = fileId.value
  if (!targetId) return
  const seq = ++pageSeq
  revokePdfUrl()
  loading.value = true
  error.value = ''
  try {
    const [res, opts, scope] = await Promise.all([
      previewKnowledge(targetId),
      fetchFilterOptions('/thinktank/knowledge').catch(() => null),
      getKnowledgeAccess().catch(() => null),
    ])
    if (seq !== pageSeq || targetId !== fileId.value) return
    applyLoadedPage(res, opts, scope)
    await loadContent(targetId, res.preview.mode, res.preview.has_binary, seq)
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
  if (!current || current.id !== fileId.value) return
  try {
    const resp = await downloadKnowledgeBlob(current.id)
    downloadBlob(resp.data, parseContentDispositionFilename(resp.headers?.['content-disposition'], current.file_name))
    ElMessage.success('下载已开始')
  } catch (err) { ElMessage.error(errorMessage(err, '下载失败')) }
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
onBeforeUnmount(() => { pageSeq += 1; neighborSeq += 1; revokePdfUrl() })
onMounted(() => { void loadPage() })
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
      <section class="review__summary">
        <div class="review__title-row">
          <div class="review__heading">
            <h1 class="review__title">
              {{ item.file_name }}
            </h1>
            <el-tag
              size="small"
              :type="suffixTagType(item.file_suffix)"
            >
              {{ item.file_suffix || 'FILE' }}
            </el-tag>
            <el-tag
              size="small"
              :type="item.is_defined ? 'success' : 'warning'"
              effect="plain"
            >
              {{ item.is_defined ? '已定义' : '未定义' }}
            </el-tag>
          </div>
          <div class="review__actions">
            <el-button
              size="small"
              :icon="item.is_favorited ? StarFilled : Star"
              :type="item.is_favorited ? 'warning' : 'default'"
              plain
              @click="onToggleFavorite"
            >
              {{ item.is_favorited ? '已收藏' : '收藏' }}
            </el-button>
            <el-button
              v-if="item.can_export"
              size="small"
              :icon="Download"
              @click="onDownload"
            >
              下载源文件
            </el-button>
            <el-button
              size="small"
              :icon="Tickets"
              @click="logsOpen = true"
            >
              日志
            </el-button>
            <AuditLogButton module="thinktank.knowledge" />
            <el-button
              v-if="item.can_edit"
              size="small"
              type="danger"
              plain
              :icon="Delete"
              @click="onDelete"
            >
              删除
            </el-button>
          </div>
        </div>
        <dl class="review__facts">
          <div
            v-for="fact in facts"
            :key="fact.label"
            class="review__fact"
          >
            <dt>{{ fact.label }}</dt>
            <dd>{{ fact.value }}</dd>
          </div>
        </dl>
      </section>

      <div
        class="review__body"
        :class="{ 'is-content-collapsed': previewCollapsed }"
      >
        <KnowledgeMetaCard
          ref="metaCardRef"
          :item="item"
          :provinces="provinces"
          :editable-file-types="accessScope?.editable_file_types"
          :editable-industries="accessScope?.editable_industries"
          @updated="item = $event"
        />

        <KnowledgeDocViewer
          :collapsed="previewCollapsed"
          :loading="contentLoading"
          :mode="previewMode"
          :pdf-url="pdfUrl"
          :text="previewText"
          :file-suffix="item.file_suffix"
          :can-export="item.can_export"
          :watermark="watermarkText"
          @update:collapsed="setCollapsed"
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
.review { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; }
.review__bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.review__back { display: inline-flex; align-items: center; gap: 8px; padding: 4px 12px; border: 1px solid var(--zt-border); border-radius: 8px; background: var(--zt-panel); color: var(--zt-ink-700); font-size: 13px; cursor: pointer; }
.review__back:hover { color: var(--zt-blue-600); border-color: var(--zt-blue-600); }
.review__pager { display: flex; align-items: center; gap: 8px; }
.review__progress { margin-right: 4px; color: var(--zt-ink-500); font-size: 13px; }
.review__error { display: flex; align-items: center; gap: 12px; }
.review__summary { padding: 16px 20px; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: 10px; display: flex; flex-direction: column; gap: 12px; }
.review__title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.review__heading { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; }
.review__title { margin: 0; font-size: 17px; font-weight: 600; color: var(--zt-ink-900); line-height: 1.4; overflow-wrap: anywhere; }
.review__actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.review__facts { margin: 0; padding-top: 12px; border-top: 1px solid var(--zt-border); display: flex; flex-wrap: wrap; gap: 8px 24px; }
.review__fact { display: flex; align-items: baseline; gap: 8px; font-size: 13px; line-height: 1.5; }
.review__fact dt { color: var(--zt-ink-500); }
.review__fact dd { margin: 0; color: var(--zt-ink-900); }
.review__body { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 12px; }
.review__body.is-content-collapsed { grid-template-columns: minmax(0, 1fr) 40px; }
@media (max-width: 1024px) {
  .review__body, .review__body.is-content-collapsed { grid-template-columns: 1fr; }
}
</style>
