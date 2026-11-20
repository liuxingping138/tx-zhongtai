/**
 * 计算一次分页查询同时覆盖 position - 1、position、position + 1 的页码与页大小。
 * 若找不到 <= maxPageSize 的单页窗口（极罕见），返回 null 交由调用方回退为单条查询。
 */
export interface NeighborPageWindow {
  page: number
  size: number
  localIndex: number
}

export function neighborWindow(position: number, maxPageSize = 100): NeighborPageWindow | null {
  if (!Number.isSafeInteger(position) || position < 0) return null
  if (position === 0) return { page: 1, size: 2, localIndex: 0 }
  for (let size = 3; size <= maxPageSize; size += 1) {
    const rem = position % size
    if (rem >= 1 && rem <= size - 2) {
      return { page: Math.floor(position / size) + 1, size, localIndex: rem }
    }
  }
  return null
}

export interface NeighborResult {
  total: number
  prevId: string | null
  nextId: string | null
}

type FetchPage = (page: number, pageSize: number) => Promise<{ total: number; items: Array<{ id: string }> }>

async function fetchNeighborsFallback(position: number, fetchPage: FetchPage): Promise<NeighborResult> {
  const prevPromise = position > 0 ? fetchPage(position, 1) : Promise.resolve(null)
  const [prevRes, nextRes] = await Promise.all([prevPromise, fetchPage(position + 2, 1)])
  return {
    total: nextRes.total,
    prevId: prevRes?.items[0]?.id ?? null,
    nextId: nextRes.items[0]?.id ?? null,
  }
}

export async function fetchNeighbors(position: number, fetchPage: FetchPage): Promise<NeighborResult> {
  const win = neighborWindow(position)
  if (!win) return fetchNeighborsFallback(position, fetchPage)
  const res = await fetchPage(win.page, win.size)
  const prevItem = position > 0 ? res.items[win.localIndex - 1] : undefined
  const nextItem = res.items[win.localIndex + 1]
  return { total: res.total, prevId: prevItem?.id ?? null, nextId: nextItem?.id ?? null }
}
