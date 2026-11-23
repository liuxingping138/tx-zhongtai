<script setup lang="ts">
import type { PDFPageProxy, RenderTask } from 'pdfjs-dist'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { outputScale, type PageSize } from './pdfLayout'
import { isCancelled } from './pdfjs'

// 一页：在可见范围（含缓冲）内才取数、画到画布上；移出范围就清空画布、释放这页的绘制数据，只留占位尺寸。
const props = defineProps<{
  pageNumber: number
  scale: number
  size: PageSize
  active: boolean
  generation: number
  getPage: (pageNumber: number) => Promise<PDFPageProxy> | null
}>()

const emit = defineEmits<{
  measured: [pageNumber: number, size: PageSize]
  failed: [err: unknown]
}>()

const canvas = ref<HTMLCanvasElement>()
const state = ref<'blank' | 'rendering' | 'done' | 'error'>('blank')
const box = computed(() => ({
  width: `${Math.floor(props.size.width * props.scale)}px`,
  height: `${Math.floor(props.size.height * props.scale)}px`,
}))
let renderTask: RenderTask | null = null
let page: PDFPageProxy | null = null
let seq = 0

function stopRender() {
  renderTask?.cancel()
  renderTask = null
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
  if (mine === seq) state.value = 'done'
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

/** 释放画布像素（把宽高置 0 才真正交还显存）和这页的绘制数据。 */
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
.pdf-page__canvas { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; }
.pdf-page__canvas.is-ready { opacity: 1; }
.pdf-page__hint { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--zt-ink-400); font-size: 13px; pointer-events: none; }
</style>
