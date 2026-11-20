import { describe, expect, it } from 'vitest'
import { lockScroll } from './scrollLock'

describe('lockScroll', () => {
  it('全屏时锁住页面滚动，退出时还原成原来的值，重复还原无副作用', () => {
    const body = { style: { overflow: 'auto' } }
    const unlock = lockScroll(body)
    expect(body.style.overflow).toBe('hidden')

    unlock()
    expect(body.style.overflow).toBe('auto')

    body.style.overflow = 'scroll'
    unlock()
    expect(body.style.overflow).toBe('scroll')
  })
})
