<script setup lang="ts">
import { ArrowLeft, ArrowRight, Download, ZoomIn, ZoomOut } from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowReactive, watch } from 'vue'

import { afterRefreshFailure } from '@/api/http'
import { getAccessToken, refreshSession } from '@/api/session'
import ParagraphSkeleton from '@/components/ParagraphSkeleton.vue'
import PdfPageCanvas from './PdfPageCanvas.vue'
import {
  clampPage,
  clampScale,
  fitWidthScale,
  mostVisiblePage,
  pagesToRender,
  stepZoom,
  zoomLabel,
  type PageSize,
} from './pdfLayout'
import { loadPdfJs } from './pdfjs'
import { usePdfStream } from './usePdfStream'

// 按 Range 分段读的 PDF 阅读器：PDF.js 先取第一页用到的几段就出图，只渲染看得到的页（上下各多 2 页），
// 其余页按第一页（或已量过的）尺寸留占位、画布释放。不用浏览器内嵌的 PDF 插件，全屏时也能按宽度重新铺满。
const props = defineProps<{
  url: string
  loadingText?: string
  canDownload?: boolean
  downloading?: boolean
}>()

const emit = defineEmits<{ unavailable: []; download: [] }>()

const pdf = usePdfStream({
  load: loadPdfJs,
  getToken: getAccessToken,
  refresh: () => refreshSession().catch((err: unknown) => { throw afterRefreshFailure(err) }),
})
const { status, errorText, numPages, baseSize, generation } = pdf

const scroller = ref<HTMLElement>()
const containerWidth = ref(0)
const fitWidth = ref(true)
const manualScale = ref(1)
const currentPage = ref(1)
const pageInput = ref('1')
const visible = ref<number[]>([])
const sizes = shallowReactive(new Map<number, PageSize>())
const ratios = new Map<number, number>()
let intersection: IntersectionObserver | null = null
let resize: ResizeObserver | null = null

const scale = computed(() => (fitWidth.value ? fitWidthScale(containerWidth.value, baseSize.value.width) : manualScale.value))
const rendered = computed(() => pagesToRender(visible.value, numPages.value))
const pages = computed(() => Array.from({ length: numPages.value }, (_, i) => i + 1))

function pageSize(pageNumber: number): PageSize {
  return sizes.get(pageNumber) ?? baseSize.value
}

function onMeasured(pageNumber: number, size: PageSize) {
  const known = sizes.get(pageNumber)
  if (!known || known.width !== size.width || known.height !== size.height) sizes.set(pageNumber, size)
}

function onIntersect(entries: IntersectionObserverEntry[]) {
  for (const entry of entries) {
    const pageNumber = Number((entry.target as HTMLElement).dataset.page)
    if (entry.isIntersecting) ratios.set(pageNumber, entry.intersectionRatio)
    else ratios.delete(pageNumber)
  }
  visible.value = [...ratios.keys()]
  currentPage.value = mostVisiblePage(ratios, currentPage.value)
}

function observePages() {
  intersection?.disconnect()
  ratios.clear()
  visible.value = []
  const root = scroller.value
  if (!root || typeof IntersectionObserver === 'undefined') return
  intersection = new IntersectionObserver(onIntersect, { root, threshold: [0, 0.25, 0.5, 0.75, 1] })
  root.querySelectorAll('[data-page]').forEach(el => intersection?.observe(el))
}

function scrollToPage(pageNumber: number) {
  const target = scroller.value?.querySelector<HTMLElement>(`[data-page="${pageNumber}"]`)
  if (!scroller.value || !target) return
  scroller.value.scrollTop = target.offsetTop - 12
  currentPage.value = pageNumber
}

function goTo(pageNumber: number) {
  scrollToPage(clampPage(pageNumber, numPages.value, currentPage.value))
}

function commitPageInput() {
  goTo(Number(pageInput.value))
  pageInput.value = String(currentPage.value)
}

function zoom(direction: 1 | -1) {
  manualScale.value = clampScale(stepZoom(scale.value, direction))
  fitWidth.value = false
}

function actualSize() {
  manualScale.value = 1
  fitWidth.value = false
}

async function onPageFailed(err: unknown) {
  await pdf.onPageError(err)
}

function reset() {
  sizes.clear()
  currentPage.value = 1
  pageInput.value = '1'
}

watch(currentPage, (page) => { pageInput.value = String(page) })
// 缩放、全屏切换（容器变宽变窄）后回到原来那页，不让人翻回去找。
watch(scale, () => {
  const keep = currentPage.value
  void nextTick(() => scrollToPage(keep))
})
// 文档（重新）打开后挂上可见性观察；令牌过期重开时页面列表会重新挂载，回到原来那页。
watch(generation, () => {
  const keep = currentPage.value
  void nextTick(() => {
    if (keep > 1) scrollToPage(keep)
    observePages()
  })
})
watch(status, (value) => { if (value === 'invalid') emit('unavailable') })
watch(() => props.url, (url) => {
  reset()
  void pdf.open(url)
}, { immediate: true })

onMounted(() => {
  if (!scroller.value || typeof ResizeObserver === 'undefined') return
  resize = new ResizeObserver(() => { containerWidth.value = scroller.value?.clientWidth ?? 0 })
  resize.observe(scroller.value)
})
onBeforeUnmount(() => {
  intersection?.disconnect()
  resize?.disconnect()
  void pdf.close()
})
</script>

<template>
  <div class="pdf-viewer">
    <div
      v-if="status === 'ready'"
      class="pdf-viewer__bar"
    >
      <div class="pdf-viewer__group">
        <button
          type="button"
          class="pdf-viewer__btn"
          title="上一页"
          :disabled="currentPage <= 1"
          @click="goTo(currentPage - 1)"
        >
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <span class="pdf-viewer__pager">
          第
          <input
            v-model="pageInput"
            class="pdf-viewer__page-input"
            inputmode="numeric"
            aria-label="跳到第几页"
            @keydown.enter="commitPageInput"
            @blur="commitPageInput"
          >
          / {{ numPages }} 页
        </span>
        <button
          type="button"
          class="pdf-viewer__btn"
          title="下一页"
          :disabled="currentPage >= numPages"
          @click="goTo(currentPage + 1)"
        >
          <el-icon><ArrowRight /></el-icon>
        </button>
      </div>
      <div class="pdf-viewer__group">
        <button
          type="button"
          class="pdf-viewer__btn"
          title="缩小"
          @click="zoom(-1)"
        >
          <el-icon><ZoomOut /></el-icon>
        </button>
        <span class="pdf-viewer__zoom">{{ zoomLabel(scale) }}</span>
        <button
          type="button"
          class="pdf-viewer__btn"
          title="放大"
          @click="zoom(1)"
        >
          <el-icon><ZoomIn /></el-icon>
        </button>
        <button
          type="button"
          class="pdf-viewer__btn pdf-viewer__btn--text"
          :class="{ 'is-active': fitWidth }"
          @click="fitWidth = true"
        >
          适合宽度
        </button>
        <button
          type="button"
          class="pdf-viewer__btn pdf-viewer__btn--text"
          :class="{ 'is-active': !fitWidth && scale === 1 }"
          @click="actualSize"
        >
          100%
        </button>
      </div>
    </div>

    <div
      ref="scroller"
      class="pdf-viewer__scroll"
    >
      <div
        v-if="status === 'loading'"
        class="pdf-viewer__status"
      >
        <p
          class="pdf-viewer__status-text"
          role="status"
        >
          {{ loadingText || '正在加载文档预览…' }}
        </p>
        <ParagraphSkeleton :lines="10" />
      </div>
      <div
        v-else-if="status === 'error'"
        class="pdf-viewer__status"
      >
        <el-alert
          :title="errorText"
          type="error"
          :closable="false"
          show-icon
        />
        <div class="pdf-viewer__actions">
          <el-button
            size="small"
            @click="pdf.retry()"
          >
            重试
          </el-button>
          <el-button
            v-if="canDownload"
            size="small"
            :icon="Download"
            :loading="downloading"
            @click="emit('download')"
          >
            下载源文件
          </el-button>
        </div>
      </div>
      <div
        v-else-if="status === 'ready'"
        class="pdf-viewer__pages"
      >
        <PdfPageCanvas
          v-for="n in pages"
          :key="n"
          :page-number="n"
          :scale="scale"
          :size="pageSize(n)"
          :active="rendered.has(n)"
          :generation="generation"
          :get-page="pdf.getPage"
          @measured="onMeasured"
          @failed="onPageFailed"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.pdf-viewer { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.pdf-viewer__bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 12px; border-bottom: 1px solid var(--zt-border); background: var(--zt-panel); flex-wrap: wrap; }
.pdf-viewer__group { display: flex; align-items: center; gap: 4px; }
.pdf-viewer__btn { display: inline-flex; align-items: center; justify-content: center; min-width: 28px; height: 28px; padding: 0 6px; border: none; border-radius: 6px; background: transparent; color: var(--zt-ink-700); font-size: 12px; cursor: pointer; }
.pdf-viewer__btn:hover:not(:disabled) { background: var(--zt-row-hover); color: var(--zt-blue-600); }
.pdf-viewer__btn:disabled { color: var(--zt-ink-400); cursor: not-allowed; }
.pdf-viewer__btn.is-active { color: var(--zt-blue-600); font-weight: 600; }
.pdf-viewer__pager, .pdf-viewer__zoom { font-size: 12px; color: var(--zt-ink-700); white-space: nowrap; }
.pdf-viewer__zoom { min-width: 44px; text-align: center; }
.pdf-viewer__page-input { width: 44px; height: 24px; margin: 0 2px; padding: 0 4px; border: 1px solid var(--zt-border); border-radius: 4px; background: var(--zt-panel); color: var(--zt-ink-900); font-size: 12px; text-align: center; }
.pdf-viewer__page-input:focus { outline: none; border-color: var(--zt-blue-600); box-shadow: var(--zt-focus-ring); }
.pdf-viewer__scroll { position: relative; flex: 1; min-height: 560px; overflow: auto; scrollbar-gutter: stable; background: var(--zt-surface-subtle); }
.pdf-viewer__pages { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 12px 16px; width: max-content; min-width: 100%; box-sizing: border-box; }
.pdf-viewer__status { display: flex; flex-direction: column; gap: 12px; padding: 16px 20px; }
.pdf-viewer__status-text { margin: 0; color: var(--zt-ink-500); font-size: 13px; }
.pdf-viewer__actions { display: flex; gap: 8px; }
</style>
