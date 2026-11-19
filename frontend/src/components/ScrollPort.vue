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

const TRACK = 10

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

const SCROLL_VALUES = new Set(['auto', 'scroll'])

function canScrollAxis(scrollSize: number, clientSize: number, scrollPos: number, delta: number, overflow: string): boolean {
  if (!delta || !SCROLL_VALUES.has(overflow)) return false
  if (delta < 0) return scrollPos > 0
  return scrollPos + clientSize < scrollSize - 1
}

function hasInnerScrollable(target: EventTarget | null, root: HTMLElement, deltaX: number, deltaY: number): boolean {
  let node: Element | null = target instanceof Element ? target : null
  while (node && node !== root) {
    const style = getComputedStyle(node)
    const canY = canScrollAxis(node.scrollHeight, node.clientHeight, node.scrollTop, deltaY, style.overflowY)
    const canX = canScrollAxis(node.scrollWidth, node.clientWidth, node.scrollLeft, deltaX, style.overflowX)
    if (canY || canX) return true
    node = node.parentElement
  }
  return false
}

function onWheel(event: WheelEvent) {
  const el = view.value
  if (!el || hasInnerScrollable(event.target, el, event.deltaX, event.deltaY)) return
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
let observedChild: Element | null = null
let rafId: number | null = null

function scheduleMeasure() {
  if (rafId !== null) return
  rafId = requestAnimationFrame(() => {
    rafId = null
    measure()
  })
}

function syncObservedChild(el: HTMLElement) {
  const next = el.firstElementChild
  if (next === observedChild) return
  if (observedChild) resizeObserver?.unobserve(observedChild)
  observedChild = next
  if (next) resizeObserver?.observe(next)
}

onMounted(() => {
  const el = view.value
  if (!el) return
  el.addEventListener('wheel', onWheel, { capture: true, passive: false })
  resizeObserver = new ResizeObserver(scheduleMeasure)
  resizeObserver.observe(el)
  syncObservedChild(el)
  mutationObserver = new MutationObserver(() => {
    syncObservedChild(el)
    scheduleMeasure()
  })
  mutationObserver.observe(el, { childList: true, subtree: false })
  scheduleMeasure()
})
onBeforeUnmount(() => {
  view.value?.removeEventListener('wheel', onWheel, true)
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
  resizeObserver?.disconnect()
  mutationObserver?.disconnect()
  observedChild = null
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
.scroll-port__track {
  position: absolute; z-index: 6; background: var(--zt-scroll-track);
  cursor: pointer; transition: background-color 0.15s ease;
}
.scroll-port__track.is-y { top: 0; right: 0; bottom: 0; width: 10px; border-left: 1px solid var(--zt-divider); }
.scroll-port.has-x .scroll-port__track.is-y { bottom: 10px; }
.scroll-port__track.is-x { left: 0; right: 0; bottom: 0; height: 10px; border-top: 1px solid var(--zt-divider); }
.scroll-port.has-y .scroll-port__track.is-x { right: 10px; }
.scroll-port__thumb {
  display: block; border-radius: 5px; background: var(--zt-scroll-thumb);
  transition: background-color 0.15s ease;
}
.scroll-port__track:hover .scroll-port__thumb { background: var(--zt-scroll-hover); }
.scroll-port__track:active .scroll-port__thumb { background: var(--zt-scroll-active); }
.scroll-port__track.is-y .scroll-port__thumb { width: 6px; margin: 2px auto; }
.scroll-port__track.is-x .scroll-port__thumb { height: 6px; margin: 2px 0; }
</style>
