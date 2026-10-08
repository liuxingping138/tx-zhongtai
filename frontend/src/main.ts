import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import '@/styles/theme.css'

import { setForbiddenHandler, setUnauthorizedHandler } from '@/api/http'
import { onRemoteLogout } from '@/api/session'
import { registerPermissionDirective } from '@/permissions/directive'
import { useAuthStore } from '@/stores/auth'

import App from './App.vue'
import router from './router'

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
    void router.replace({ name: 'login' })
  }
})
onRemoteLogout(() => {
  auth.signedIn = false
  auth.clearIdentity()
  if (router.currentRoute.value.name !== 'login') {
    void router.replace({ name: 'login' })
  }
})
setForbiddenHandler(() => {
  if (auth.isAuthenticated && !auth.mustChangePassword) {
    void auth.loadProfile()
  }
})

app.mount('#app')
