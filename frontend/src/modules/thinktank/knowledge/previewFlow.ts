/**
 * 打开一条记录：资料信息一到就交给页面渲染，原文只发起、不等。
 *
 * 原文是整份 PDF 或 Office 转码（可能要几秒到一分钟），等它的话整页一直是骨架屏；
 * 右栏有自己的加载态。返回的 Promise 在资料信息渲染后就结束，页面据此收起骨架屏。
 * 等资料信息期间换了记录（`isCurrent` 为假）就什么都不做。
 */
export async function openRecord<T>(opts: {
  fetchMeta: () => Promise<T>
  isCurrent: () => boolean
  onMeta: (meta: T) => void
  startContent: (meta: T) => Promise<unknown>
}): Promise<boolean> {
  const meta = await opts.fetchMeta()
  if (!opts.isCurrent()) return false
  opts.onMeta(meta)
  void opts.startContent(meta)
  return true
}
