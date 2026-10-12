// 重新部署后旧的分包文件名不存在了，开着的页面切路由就会报「Failed to fetch dynamically imported module」。
// 这时整页刷新到目标地址即可拿到新版本；用会话存储记一次，服务真挂了也不会无限刷新。
const RELOAD_KEY = 'zt:chunk-reload'
const CHUNK_ERROR = /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i

export function isChunkLoadError(error: unknown): boolean {
  return error instanceof Error && CHUNK_ERROR.test(error.message)
}

type SessionStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

/** 返回 true 表示已经发起刷新；同一目标刚刷新过仍然失败时返回 false，交给页面显示错误。 */
export function reloadForNewVersion(target: string, storage: SessionStore, assign: (url: string) => void): boolean {
  if (storage.getItem(RELOAD_KEY) === target) return false
  storage.setItem(RELOAD_KEY, target)
  assign(target)
  return true
}

/** 路由成功进入后清掉标记，下一次发布还能再自动刷新。 */
export function clearReloadMark(storage: SessionStore): void {
  storage.removeItem(RELOAD_KEY)
}
