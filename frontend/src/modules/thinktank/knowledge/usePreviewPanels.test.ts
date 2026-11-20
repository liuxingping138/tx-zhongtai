import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { META_COLLAPSE_KEY, PREVIEW_COLLAPSE_KEY, usePreviewPanels, type DiscardGuard } from './usePreviewPanels'

describe('usePreviewPanels', () => {
  const store = new Map<string, string>()

  beforeEach(() => {
    store.clear()
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => store.set(k, v),
    })
  })

  afterEach(() => { vi.unstubAllGlobals() })

  it('正在编辑没保存时收起标签要先确认，取消就不收起', async () => {
    const card: DiscardGuard = { confirmDiscard: vi.fn().mockResolvedValue(false) }
    const panels = usePreviewPanels(() => card)

    expect(await panels.setMetaCollapsed(true)).toBe(false)
    expect(card.confirmDiscard).toHaveBeenCalledOnce()
    expect(panels.metaCollapsed.value).toBe(false)
    expect(store.has(META_COLLAPSE_KEY)).toBe(false)
  })

  it('确认放弃后收起标签，并展开文档预览；展开标签不用确认', async () => {
    const card: DiscardGuard = { confirmDiscard: vi.fn().mockResolvedValue(true) }
    const panels = usePreviewPanels(() => card)
    panels.setPreviewCollapsed(true)
    expect(panels.previewCollapsed.value).toBe(true)

    expect(await panels.setMetaCollapsed(true)).toBe(true)
    expect(panels.metaCollapsed.value).toBe(true)
    expect(panels.previewCollapsed.value).toBe(false)
    expect(store.get(META_COLLAPSE_KEY)).toBe('1')
    expect(store.get(PREVIEW_COLLAPSE_KEY)).toBe('0')

    expect(await panels.setMetaCollapsed(false)).toBe(true)
    expect(card.confirmDiscard).toHaveBeenCalledOnce()
    expect(panels.metaCollapsed.value).toBe(false)
  })

  it('卡片还没挂上时直接收起；收起预览会把标签展开', async () => {
    const panels = usePreviewPanels(() => null)
    expect(await panels.setMetaCollapsed(true)).toBe(true)

    panels.setPreviewCollapsed(true)
    expect(panels.metaCollapsed.value).toBe(false)
    expect(store.get(META_COLLAPSE_KEY)).toBe('0')
  })

  it('读本机记录；两栏都记成收起时只收起预览，存储不可用时都展开', () => {
    store.set(PREVIEW_COLLAPSE_KEY, '1')
    store.set(META_COLLAPSE_KEY, '1')
    const panels = usePreviewPanels(() => null)
    expect(panels.previewCollapsed.value).toBe(true)
    expect(panels.metaCollapsed.value).toBe(false)

    vi.stubGlobal('localStorage', {
      getItem: () => { throw new Error('denied') },
      setItem: () => { throw new Error('denied') },
    })
    const blocked = usePreviewPanels(() => null)
    expect(blocked.previewCollapsed.value).toBe(false)
    blocked.setPreviewCollapsed(true)
    expect(blocked.previewCollapsed.value).toBe(true)
  })
})
