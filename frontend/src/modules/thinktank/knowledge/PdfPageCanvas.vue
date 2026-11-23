<script setup lang="ts">
import type { PDFPageProxy, RenderTask } from 'pdfjs-dist'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { outputScale, type PageSize } from './pdfLayout'
import { isCancelled } from './pdfjs'
import { usePageTextLayer } from './usePageTextLayer'

// 一页：在可见范围（含缓冲）内才取数、画到画布上；画完再盖一层透明文字（能选中复制、显示查找高亮）。
// 移出范围就清空画布、拆掉文字层、释放这页的绘制数据，只留占位尺寸。
const props = withDefaults(defineProps<{
  pageNumber: number
  scale: number
  size: PageSize
  active: boolean
  generation: number
  getPage: (pageNumber: number) => Promise<PDFPageProxy> | null
  /** 查找词（已归一化），空串表示没在查找。 */
  query?: string
  /** 本页第几处是当前匹配，-1 表示不在本页。 */
  selected?: number
}>(), { query: '', selected: -1 })

const emit = defineEmits<{
  measured: [pageNumber: number, size: PageSize]
  failed: [err: unknown]
  matchFocus: [el: HTMLElement]
}>()

const canvas = ref<HTMLCanvasElement>()
const textLayerEl = ref<HTMLElement>()
const state = ref<'blank' | 'rendering' | 'done' | 'error'>('blank')
const box = computed(() => ({
  width: `${Math.floor(props.size.width * props.scale)}px`,
  height: `${Math.floor(props.size.height * props.scale)}px`,
}))
const textLayer = usePageTextLayer({
  container: textLayerEl,
  query: () => props.query,
  selected: () => props.selected,
  onSelected: el => emit('matchFocus', el),
})
let renderTask: RenderTask | null = null
let page: PDFPageProxy | null = null
let seq = 0

function stopRender() {
  renderTask?.cancel()
  renderTask = null
  textLayer.destroy()
}

async function paint(target: PDFPageProxy, el: HTMLCanvasElement, mine: number) {
  const natural = target.getViewport({ scale: 1 })
  emit('measured', props.pageNumber, { width: natural.width, height: natural.height })
  const viewport = target.getViewport({ scale: props.scale })
  const ratio = outputScale(viewport.width, viewport.height, window.devicePixelRatio)
  el.width = Math.floor(viewport.width * ratio)
  el.height = Math.floor(viewport.height * ratio)
  renderTask = target.render({ canvas: el, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] })
  await renderTask.promise
  if (mine !== seq) return
  state.value = 'done'
  void textLayer.build(target, viewport)
}

async function draw() {
  const mine = ++seq
  stopRender()
  const pending = props.getPage(props.pageNumber)
  if (!pending || !canvas.value) return
  state.value = 'rendering'
  try {
    page = await pending
    if (mine !== seq || !canvas.value) return
    await paint(page, canvas.value, mine)
  } catch (err) {
    if (mine !== seq || isCancelled(err)) return
    state.value = 'error'
    emit('failed', err)
  }
}

/** 释放画布像素（把宽高置 0 才真正交还显存）、文字层和这页的绘制数据。 */
function release() {
  seq += 1
  stopRender()
  page?.cleanup()
  page = null
  if (canvas.value) {
    canvas.value.width = 0
    canvas.value.height = 0
  }
  state.value = 'blank'
}

function sync() {
  if (props.active) void draw()
  else release()
}

watch(() => [props.active, props.scale, props.generation], sync)
watch(() => [props.query, props.selected], () => textLayer.paint())
onMounted(sync)
onBeforeUnmount(release)
</script>

<template>
  <div
    class="pdf-page"
    :style="box"
    :data-page="pageNumber"
  >
    <canvas
      ref="canvas"
      class="pdf-page__canvas"
      :class="{ 'is-ready': state === 'done' }"
      :aria-label="`第 ${pageNumber} 页`"
    />
    <div
      ref="textLayerEl"
      class="pdf-page__text"
    />
    <span
      v-if="state !== 'done'"
      class="pdf-page__hint"
    >
      {{ state === 'error' ? `第 ${pageNumber} 页加载失败` : `第 ${pageNumber} 页` }}
    </span>
  </div>
</template>

<style scoped>
.pdf-page { position: relative; margin: 0 auto; background: var(--zt-panel); box-shadow: var(--zt-shadow-soft); flex-shrink: 0; }
.pdf-page__canvas { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; z-index: 0; }
.pdf-page__canvas.is-ready { opacity: 1; }
.pdf-page__hint { position: absolute; inset: 0; z-index: 2; display: flex; align-items: center; justify-content: center; color: var(--zt-ink-400); font-size: 13px; pointer-events: none; }

/* 文字层：与 PDF.js 自带 pdf_viewer.css 的 .textLayer 同一套规则（只取选字和高亮要用的），颜色取主题变量。 */
.pdf-page__text {
  --user-unit: 1;
  --total-scale-factor: calc(var(--scale-factor, 1) * var(--user-unit));
  --scale-round-x: 1px;
  --scale-round-y: 1px;
  --min-font-size: 1;
  --text-scale-factor: calc(var(--total-scale-factor) * var(--min-font-size));
  --min-font-size-inv: calc(1 / var(--min-font-size));

  position: absolute;
  inset: 0;
  z-index: 1;
  overflow: clip;
  line-height: 1;
  text-align: initial;
  letter-spacing: normal;
  word-spacing: normal;
  text-size-adjust: none;
  forced-color-adjust: none;
  transform-origin: 0 0;
  caret-color: transparent;
}
.pdf-page__text :deep(span),
.pdf-page__text :deep(br) {
  position: absolute;
  color: transparent;
  white-space: pre;
  cursor: text;
  transform-origin: 0% 0%;
  user-select: text;
}
.pdf-page__text > :deep(:not(.markedContent)),
.pdf-page__text :deep(.markedContent span:not(.markedContent)) {
  --font-height: 0;
  --scale-x: 1;
  --rotate: 0deg;

  z-index: 1;
  font-size: calc(var(--text-scale-factor) * var(--font-height));
  transform: rotate(var(--rotate)) scaleX(var(--scale-x)) scale(var(--min-font-size-inv));
}
.pdf-page__text :deep(.markedContent) { display: contents; }
.pdf-page__text :deep(span[role="img"]) { user-select: none; cursor: default; }
.pdf-page__text :deep(::selection) { background: var(--zt-pdf-selection); color: transparent; }
.pdf-page__text :deep(br::selection) { background: transparent; }
/* 查找高亮：包在文字块里面的行内 span，不改块本身的位置。 */
.pdf-page__text :deep(span.pdf-hl) {
  position: static;
  margin: -1px;
  padding: 1px;
  border-radius: 3px;
  background: var(--zt-pdf-match);
  transform: none;
}
.pdf-page__text :deep(span.pdf-hl.is-selected) { background: var(--zt-pdf-match-active); }
</style>
