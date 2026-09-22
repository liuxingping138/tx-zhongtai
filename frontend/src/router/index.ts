import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { routes } from './routes'

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
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

  if (to.name === 'home' && !auth.mustChangePassword && auth.resources.length === 0) {
    return { name: 'no-modules' }
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
