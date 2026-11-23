// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'

import KnowledgeDocViewer from './KnowledgeDocViewer.vue'

// PDF 阅读器换成只带查找开关的替身：这里只验全屏时的按键先后。
const searchOpen = ref(false)
const PdfStreamViewerStub = defineComponent({
  name: 'PdfStreamViewer',
  setup(_, { expose }) {
    expose({
      openSearch: () => { searchOpen.value = true },
      closeSearch: () => {
        const was = searchOpen.value
        searchOpen.value = false
        return was
      },
    })
    return () => h('div', { class: 'pdf-stub' })
  },
})

function mountViewer() {
  return mount(KnowledgeDocViewer, {
    props: {
      collapsed: false,
      metaCollapsed: false,
      loading: false,
      mode: 'pdf',
      pdfUrl: '/content',
      text: '',
      fileName: '方案.pdf',
      fileSuffix: 'PDF',
      canExport: true,
      watermark: '测试',
    },
    global: { stubs: { PdfStreamViewer: PdfStreamViewerStub, 'el-icon': true, 'el-tag': true }, renderStubDefaultSlot: true },
    attachTo: document.body,
  })
}

function press(key: string, init: KeyboardEventInit = {}) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init })
  window.dispatchEvent(event)
  return event
}

describe('KnowledgeDocViewer 全屏按键', () => {
  afterEach(() => {
    searchOpen.value = false
    document.body.innerHTML = ''
  })

  it('全屏时 Ctrl+F 打开查找；Esc 先关查找，再按才退出全屏', async () => {
    const wrapper = mountViewer()
    await wrapper.find('.review__tool-btn--primary').trigger('click')
    expect(document.querySelector('.review__content.is-fullscreen')).not.toBeNull()

    expect(press('f', { ctrlKey: true }).defaultPrevented).toBe(true)
    expect(searchOpen.value).toBe(true)

    press('Escape')
    await nextTick()
    expect(searchOpen.value).toBe(false)
    expect(document.querySelector('.review__content.is-fullscreen')).not.toBeNull()

    press('Escape')
    await nextTick()
    expect(document.querySelector('.review__content.is-fullscreen')).toBeNull()
    wrapper.unmount()
  })

  it('不在全屏时不拦按键，交给阅读器自己处理', () => {
    const wrapper = mountViewer()
    const spy = vi.fn()
    window.addEventListener('keydown', spy)
    expect(press('f', { metaKey: true }).defaultPrevented).toBe(false)
    expect(searchOpen.value).toBe(false)
    expect(spy).toHaveBeenCalled()
    window.removeEventListener('keydown', spy)
    wrapper.unmount()
  })
})
