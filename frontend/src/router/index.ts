import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { routes } from './routes'
import { useWorkspace } from '@/layouts/workspace'

const router = createRouter({
  history: createWebHistory(),
  routes,
})

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
  }

  if (to.meta.public) {
    if (auth.isAuthenticated && auth.mustChangePassword) {
      return { name: 'change-password' }
    }
    if (auth.isAuthenticated) {
      return { name: 'home' }
    }
    return true
  }

  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (auth.mustChangePassword && to.name !== 'change-password') {
    return { name: 'change-password' }
  }

  if (!auth.mustChangePassword && to.name === 'change-password') {
    return { name: 'home' }
  }

  const resource = to.meta.resource
  if (typeof resource === 'string' && !auth.canRead(resource)) {
    return { name: 'forbidden' }
  }

  if (to.name === 'home') {
    const { groups } = useWorkspace()
    return { path: groups.value[0]?.entries[0]?.path || '/no-modules', query: to.query, replace: true }
  }

  return true
})

router.afterEach((to) => { document.title = `${to.meta.title || '页面'} · 业务数据运营平台` })

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    restricted?: boolean
    title?: string
    resource?: string
  }
}

export default router
