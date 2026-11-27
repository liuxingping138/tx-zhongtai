import { createRouter, createWebHistory, type RouteLocationNormalized, type RouteLocationRaw } from 'vue-router'

import type { ThinktankDictSlug } from '@/api/codebook'
import { useAuthStore } from '@/stores/auth'
import { clearReloadMark, isChunkLoadError, reloadForNewVersion } from './chunkReload'
import { routes } from './routes'
import { useWorkspace } from '@/layouts/workspace'

const router = createRouter({
  history: createWebHistory(),
  routes,
})

type Auth = ReturnType<typeof useAuthStore>

/** 登录页等公开页：已登录就不再停留。 */
function publicRouteTarget(auth: Auth): RouteLocationRaw | true {
  if (!auth.isAuthenticated) return true
  return { name: auth.mustChangePassword ? 'change-password' : 'home' }
}

/** 必须改密码时只能停在改密码页；不需要改时不让进改密码页。 */
function passwordTarget(auth: Auth, to: RouteLocationNormalized): RouteLocationRaw | undefined {
  const onChangePage = to.name === 'change-password'
  if (auth.mustChangePassword && !onChangePage) return { name: 'change-password' }
  if (!auth.mustChangePassword && onChangePage) return { name: 'home' }
  return undefined
}

/** 首页没有内容，跳到当前账号能看到的第一个模块。 */
function homeTarget(to: RouteLocationNormalized): RouteLocationRaw {
  const { groups } = useWorkspace()
  return { path: groups.value[0]?.entries[0]?.path || '/no-modules', query: to.query, replace: true }
}

/** 启动时服务暂时不可用：停在提示页、可以重试，不当成没登录踢回登录页。 */
function unavailableTarget(to: RouteLocationNormalized): RouteLocationRaw | true {
  return to.name === 'service-unavailable' ? true : { name: 'service-unavailable', query: { redirect: to.fullPath } }
}

router.beforeEach(async (to) => {
  // 兼容旧预览书签，正式页面不再需要开关；保留业务筛选和锚点。
  if ('design-preview' in to.query) {
    const query = { ...to.query }
    delete query['design-preview']
    return { path: to.path, query, hash: to.hash, replace: true }
  }
  const auth = useAuthStore()
  if (!auth.bootstrapped) {
    await auth.bootstrap()
    if (auth.unavailable) return unavailableTarget(to)
  }

  if (to.meta.public) return publicRouteTarget(auth)
  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  const passwordRedirect = passwordTarget(auth, to)
  if (passwordRedirect) return passwordRedirect

  const resource = to.meta.resource
  if (typeof resource === 'string' && !auth.canRead(resource)) {
    return { name: 'forbidden' }
  }
  return to.name === 'home' ? homeTarget(to) : true
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '页面'} · 业务数据运营平台`
  // 路由守卫的单测在 node 里跑，没有 sessionStorage。
  if (typeof sessionStorage !== 'undefined') clearReloadMark(sessionStorage)
})

router.onError((error, to) => {
  if (isChunkLoadError(error)) reloadForNewVersion(to.fullPath, sessionStorage, url => window.location.assign(url))
})

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    restricted?: boolean
    title?: string
    resource?: string
    menuPath?: string
    dictSlug?: ThinktankDictSlug
  }
}

export default router
