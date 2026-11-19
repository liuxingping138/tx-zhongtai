import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import '@/styles/theme.css'

import { setForbiddenHandler, setUnauthorizedHandler } from '@/api/http'
import { onRemoteLogout } from '@/api/session'
import { initDensity } from '@/composables/useTableDensity'
import { initTheme } from '@/composables/useTheme'
import { registerPermissionDirective } from '@/permissions/directive'
import { useAuthStore } from '@/stores/auth'

initTheme()
initDensity()

import App from './App.vue'
import router from './router'

// eslint-disable-next-line @typescript-eslint/no-unsafe-argument -- typescript-eslint 读不出 .vue 根组件的类型，App 由 vue-tsc 检查
const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })
registerPermissionDirective(app)

const auth = useAuthStore()
setUnauthorizedHandler(() => {
  auth.clearSession()
  if (router.currentRoute.value.name !== 'login') {
    // 和路由守卫一样带上 redirect：重新登录后回到刚才的页面，不是首页。
    void router.replace({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
  }
})
onRemoteLogout(() => {
  auth.signedIn = false
  auth.clearIdentity()
  if (router.currentRoute.value.name !== 'login') {
    // 和路由守卫一样带上 redirect：重新登录后回到刚才的页面，不是首页。
    void router.replace({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
  }
})
let forbiddenReload: Promise<void> | null = null
setForbiddenHandler(() => {
  if (!auth.isAuthenticated || auth.mustChangePassword || forbiddenReload) return
  forbiddenReload = auth
    .loadProfile()
    .then(() => {
      const resource = router.currentRoute.value.meta.resource
      if (resource && !auth.canRead(resource)) {
        void router.replace({ name: 'home' })
      }
    })
    .catch(() => undefined)
    .finally(() => {
      forbiddenReload = null
    })
})

app.mount('#app')
