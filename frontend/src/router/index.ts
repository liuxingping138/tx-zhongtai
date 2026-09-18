import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/change-password',
    name: 'change-password',
    component: () => import('@/views/ChangePasswordView.vue'),
    meta: { restricted: true, title: '修改密码' },
  },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('@/views/HomeView.vue'),
        meta: { title: '首页' },
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/ProfileView.vue'),
        meta: { title: '个人设置' },
      },
      {
        path: 'system/users',
        name: 'system-users',
        component: () => import('@/modules/system/users/UserList.vue'),
        meta: { title: '用户管理', resource: 'system.users' },
      },
      {
        path: 'system/roles',
        name: 'system-roles',
        component: () => import('@/modules/system/roles/RoleList.vue'),
        meta: { title: '角色管理', resource: 'system.roles' },
      },
      {
        path: 'system/permissions',
        name: 'system-permissions',
        component: () => import('@/modules/system/permissions/PermissionConfig.vue'),
        meta: { title: '权限分配', resource: 'system.permissions' },
      },
      {
        path: 'system/roles/:roleId/grants',
        name: 'system-role-grants',
        component: () => import('@/modules/system/permissions/PermissionConfig.vue'),
        meta: { title: '角色授权', resource: 'system.permissions' },
      },
      {
        path: 'system/audit',
        name: 'system-audit',
        component: () => import('@/modules/system/audit/AuditList.vue'),
        meta: { title: '操作日志', resource: 'system.audit' },
      },
      {
        path: 'codebook/policy-types',
        name: 'codebook-policy-types',
        component: () => import('@/modules/codebook/policy-types/PolicyTypeList.vue'),
        meta: { title: '政策类型码表', resource: 'codebook.policy_types' },
      },
      {
        path: 'codebook/scenarios',
        name: 'codebook-scenarios',
        component: () => import('@/modules/codebook/scenarios/ScenarioList.vue'),
        meta: { title: '场景码表', resource: 'codebook.scenarios' },
      },
      {
        path: 'codebook/area-codes',
        name: 'codebook-area-codes',
        component: () => import('@/modules/codebook/area-codes/AreaCodeList.vue'),
        meta: { title: '省市区编码表', resource: 'codebook.area_codes' },
      },
      {
        path: 'policy/sources',
        name: 'policy-sources',
        component: () => import('@/modules/policy/sources/SourceList.vue'),
        meta: { title: '信源管理', resource: 'policy.sources' },
      },
      {
        path: 'policy/base-tags',
        name: 'policy-base-tags',
        component: () => import('@/modules/policy/base-tags/BaseTagList.vue'),
        meta: { title: '政策基础标签表', resource: 'policy.base_tags' },
      },
      {
        path: 'policy/interpretations',
        name: 'policy-interpretations',
        component: () => import('@/modules/policy/interpretations/InterpretationList.vue'),
        meta: { title: '政策解读列表', resource: 'policy.interpretations' },
      },
      {
        path: 'forbidden',
        name: 'forbidden',
        component: () => import('@/views/ForbiddenView.vue'),
        meta: { title: '无权访问' },
      },
      {
        path: 'unavailable',
        name: 'unavailable',
        component: () => import('@/views/UnavailableView.vue'),
        meta: { title: '服务不可用' },
      },
      {
        path: 'no-modules',
        name: 'no-modules',
        component: () => import('@/views/NoModulesView.vue'),
        meta: { title: '暂无可用模块' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFound.vue'),
    meta: { title: '页面不存在' },
  },
]

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

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    restricted?: boolean
    title?: string
    resource?: string
  }
}

export default router
