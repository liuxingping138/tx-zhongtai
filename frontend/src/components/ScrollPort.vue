<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'

const view = ref<HTMLElement>()
const state = reactive({
  needX: false,
  needY: false,
  xThumb: 40,
  yThumb: 40,
  xOffset: 0,
  yOffset: 0,
})

const TRACK = 14

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function measure() {
  const el = view.value
  if (!el) return
  const maxX = el.scrollWidth - el.clientWidth
  const maxY = el.scrollHeight - el.clientHeight
  state.needX = maxX > 1
  state.needY = maxY > 1
  const trackX = Math.max(0, el.clientWidth - (state.needY ? TRACK : 0))
  const trackY = Math.max(0, el.clientHeight - (state.needX ? TRACK : 0))
  state.xThumb = maxX > 1 ? Math.max(32, Math.round((el.clientWidth / el.scrollWidth) * trackX)) : trackX
  state.yThumb = maxY > 1 ? Math.max(32, Math.round((el.clientHeight / el.scrollHeight) * trackY)) : trackY
  state.xOffset = maxX > 0 ? (el.scrollLeft / maxX) * (trackX - state.xThumb) : 0
  state.yOffset = maxY > 0 ? (el.scrollTop / maxY) * (trackY - state.yThumb) : 0
}

function onWheel(event: WheelEvent) {
  const el = view.value
  if (!el) return
  const maxX = el.scrollWidth - el.clientWidth
  const maxY = el.scrollHeight - el.clientHeight
  const nextX = clamp(el.scrollLeft + event.deltaX, 0, Math.max(0, maxX))
  const nextY = clamp(el.scrollTop + event.deltaY, 0, Math.max(0, maxY))
  const moved = nextX !== el.scrollLeft || nextY !== el.scrollTop
  if (!moved) return
  el.scrollLeft = nextX
  el.scrollTop = nextY
  event.preventDefault()
  event.stopPropagation()
}

function bindDrag(axis: 'x' | 'y', event: PointerEvent) {
  const el = view.value
  if (!el) return
  event.preventDefault()
  const start = axis === 'x' ? event.clientX : event.clientY
  const startScroll = axis === 'x' ? el.scrollLeft : el.scrollTop
  const max = axis === 'x' ? el.scrollWidth - el.clientWidth : el.scrollHeight - el.clientHeight
  const track = axis === 'x'
    ? el.clientWidth - (state.needY ? TRACK : 0) - state.xThumb
    : el.clientHeight - (state.needX ? TRACK : 0) - state.yThumb
  const move = (next: PointerEvent) => {
    const delta = (axis === 'x' ? next.clientX : next.clientY) - start
    const value = startScroll + (track > 0 ? (delta / track) * max : 0)
    if (axis === 'x') el.scrollLeft = clamp(value, 0, Math.max(0, max))
    else el.scrollTop = clamp(value, 0, Math.max(0, max))
  }
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

let resizeObserver: ResizeObserver | undefined
let mutationObserver: MutationObserver | undefined
onMounted(() => {
  const el = view.value
  if (!el) return
  el.addEventListener('wheel', onWheel, { capture: true, passive: false })
  resizeObserver = new ResizeObserver(measure)
  resizeObserver.observe(el)
  mutationObserver = new MutationObserver(measure)
  mutationObserver.observe(el, { childList: true, subtree: true, attributes: true })
  requestAnimationFrame(measure)
})
onBeforeUnmount(() => {
  view.value?.removeEventListener('wheel', onWheel, true)
  resizeObserver?.disconnect()
  mutationObserver?.disconnect()
})
</script>
<template>
  <div
    class="scroll-port"
    :class="{ 'has-x': state.needX, 'has-y': state.needY }"
  >
    <div
      ref="view"
      class="scroll-port__view"
      @scroll="measure"
    >
      <slot />
    </div>
    <div
      v-show="state.needY"
      class="scroll-port__track is-y"
      aria-hidden="true"
      @pointerdown="bindDrag('y', $event)"
    >
      <i
        class="scroll-port__thumb"
        :style="{ height: `${state.yThumb}px`, transform: `translateY(${state.yOffset}px)` }"
      />
    </div>
    <div
      v-show="state.needX"
      class="scroll-port__track is-x"
      aria-hidden="true"
      @pointerdown="bindDrag('x', $event)"
    >
      <i
        class="scroll-port__thumb"
        :style="{ width: `${state.xThumb}px`, transform: `translateX(${state.xOffset}px)` }"
      />
    </div>
  </div>
</template>
<style scoped>
.scroll-port { position: relative; display: flex; flex-direction: column; flex: 1 1 0; min-width: 0; min-height: 0; height: 0; }
.scroll-port__view { flex: 1 1 0; min-height: 0; overflow: auto; overscroll-behavior: contain; scrollbar-width: none; }
.scroll-port__view::-webkit-scrollbar { width: 0; height: 0; display: none; }
.scroll-port__track { position: absolute; z-index: 6; background: var(--zt-scroll-track); }
.scroll-port__track.is-y { top: 0; right: 0; bottom: 0; width: 14px; }
.scroll-port.has-x .scroll-port__track.is-y { bottom: 14px; }
.scroll-port__track.is-x { left: 0; right: 0; bottom: 0; height: 14px; }
.scroll-port.has-y .scroll-port__track.is-x { right: 14px; }
.scroll-port__thumb { display: block; border-radius: 7px; background: var(--zt-scroll-thumb); }
.scroll-port__track.is-y .scroll-port__thumb { width: 10px; margin: 2px; }
.scroll-port__track.is-x .scroll-port__thumb { height: 10px; margin: 2px; }
.scroll-port__track { cursor: pointer; }
</style>
