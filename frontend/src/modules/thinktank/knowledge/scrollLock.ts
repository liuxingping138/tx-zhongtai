interface StyleTarget {
  style: { overflow: string }
}

/** 全屏预览时锁住后面页面的滚动，返回还原函数（按进入前的值还原，不覆盖别处设的值）。 */
export function lockScroll(target: StyleTarget): () => void {
  const previous = target.style.overflow
  target.style.overflow = 'hidden'
  let released = false
  return () => {
    if (released) return
    released = true
    target.style.overflow = previous
  }
}
