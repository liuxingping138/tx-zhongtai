// @vitest-environment happy-dom
import { h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import FilterBar from './FilterBar.vue'

describe('FilterBar ResizeObserver 防振荡', () => {
  let resizeCallback: (() => void) | null = null
  let rafQueue: FrameRequestCallback[] = []
  const OriginalResizeObserver = globalThis.ResizeObserver

  beforeEach(() => {
    resizeCallback = null
    rafQueue = []
    class MockResizeObserver implements ResizeObserver {
      constructor(cb: ResizeObserverCallback) {
        resizeCallback = () => cb([], this)
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    globalThis.ResizeObserver = MockResizeObserver
  })

  afterEach(() => {
    globalThis.ResizeObserver = OriginalResizeObserver
    vi.restoreAllMocks()
  })

  function mountBar() {
    return mount(FilterBar, {
      props: { query: { keyword: '' }, applied: { keyword: '' } },
      slots: {
        default: () => [
          h('div', { class: 'field-a' }, [h('input')]),
          h('div', { class: 'field-b' }, [h('input')]),
        ],
      },
      global: {
        stubs: {
          ElForm: { template: '<form><slot /></form>' },
          ElButton: { template: '<button><slot /></button>' },
          ElIcon: { template: '<i><slot /></i>' },
        },
      },
    })
  }

  it('仅高度变化（宽度不变）的 ResizeObserver 回调不会触发重测，避免折叠重入循环', () => {
    const rafSpy = vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb) => {
      rafQueue.push(cb)
      return rafQueue.length
    })
    const wrapper = mountBar()
    const fieldsEl = wrapper.find('.filter-bar__fields').element as HTMLElement
    Object.defineProperty(fieldsEl, 'clientWidth', { value: 700, configurable: true })

    // 首次宽度变化触发一次 rAF
    resizeCallback?.()
    expect(rafSpy).toHaveBeenCalledTimes(1)
    rafQueue.shift()?.(0)

    // 宽度仍为 700（如仅 maxHeight 变化）不再调度 rAF
    resizeCallback?.()
    expect(rafSpy).toHaveBeenCalledTimes(1)

    wrapper.unmount()
  })

  it('宽度改变时通过 rAF 异步重测折叠状态，卸载时清理未执行帧', async () => {
    let nextRafId = 0
    const rafSpy = vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb) => {
      rafQueue.push(cb)
      nextRafId += 1
      return nextRafId
    })
    const cancelRafSpy = vi.spyOn(globalThis, 'cancelAnimationFrame').mockImplementation(() => {})
    const wrapper = mountBar()
    const fieldsEl = wrapper.find('.filter-bar__fields').element as HTMLElement
    const [first, second] = fieldsEl.children as unknown as [HTMLElement, HTMLElement]
    let width = 900
    Object.defineProperty(fieldsEl, 'clientWidth', { get: () => width, configurable: true })
    Object.defineProperty(first, 'offsetTop', { value: 0, configurable: true })
    Object.defineProperty(first, 'offsetHeight', { value: 36, configurable: true })
    Object.defineProperty(second, 'offsetTop', { get: () => (width < 750 ? 48 : 0), configurable: true })
    Object.defineProperty(second, 'offsetHeight', { value: 36, configurable: true })

    // 初始窄宽度 -> 出现「展开」按钮
    width = 680
    resizeCallback?.()
    expect(rafSpy).toHaveBeenCalledTimes(1)
    rafQueue.shift()?.(0)
    await nextTick()
    expect(wrapper.find('.filter-bar__toggle').exists()).toBe(true)

    // 再变窄时合批 rAF，卸载时取消未执行的帧
    width = 620
    resizeCallback?.()
    resizeCallback?.()
    expect(rafSpy).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    expect(cancelRafSpy).toHaveBeenCalledWith(2)
  })
})
