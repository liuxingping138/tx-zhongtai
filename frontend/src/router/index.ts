import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

// `meta.resource` 约定：P3/P4 阶段路由守卫据此向 IAM 校验访问权限。
// P1 阶段仅搭建路由骨架，尚未接入任何鉴权逻辑。
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('@/views/HomePlaceholder.vue'),
        meta: { resource: null },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFound.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
