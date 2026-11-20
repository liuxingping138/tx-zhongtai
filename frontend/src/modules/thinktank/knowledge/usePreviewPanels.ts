import { ref } from 'vue'

export const PREVIEW_COLLAPSE_KEY = 'thinktank.knowledge.previewCollapsed'
export const META_COLLAPSE_KEY = 'thinktank.knowledge.metaCollapsed'

/** 标签卡片：收起前要问一句「正在编辑的改动不要了吗」。 */
export interface DiscardGuard {
  confirmDiscard: () => Promise<boolean>
}

function readFlag(key: string): boolean {
  try { return localStorage.getItem(key) === '1' } catch { return false }
}

function writeFlag(key: string, val: boolean) {
  try { localStorage.setItem(key, val ? '1' : '0') } catch { /* 禁用存储时忽略 */ }
}

/**
 * 预览页左右两栏（标签卡片、文档预览）的收起状态，记在本机。两栏不能同时收起：收起一栏时另一栏自动展开。
 * 收起标签会卸掉标签卡片，正在编辑没保存的先确认，否则改动悄悄丢掉，翻页时也没人再拦。
 */
export function usePreviewPanels(guard: () => DiscardGuard | null | undefined) {
  const previewCollapsed = ref(readFlag(PREVIEW_COLLAPSE_KEY))
  const metaCollapsed = ref(readFlag(META_COLLAPSE_KEY) && !previewCollapsed.value)

  function setPreviewCollapsed(val: boolean) {
    previewCollapsed.value = val
    if (val) { metaCollapsed.value = false; writeFlag(META_COLLAPSE_KEY, false) }
    writeFlag(PREVIEW_COLLAPSE_KEY, val)
  }

  async function setMetaCollapsed(val: boolean): Promise<boolean> {
    const card = guard()
    if (val && card && !(await card.confirmDiscard())) return false
    metaCollapsed.value = val
    if (val) { previewCollapsed.value = false; writeFlag(PREVIEW_COLLAPSE_KEY, false) }
    writeFlag(META_COLLAPSE_KEY, val)
    return true
  }

  return { previewCollapsed, metaCollapsed, setPreviewCollapsed, setMetaCollapsed }
}
