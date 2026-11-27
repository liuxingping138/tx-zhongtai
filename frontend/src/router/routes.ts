import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/service-unavailable',
    name: 'service-unavailable',
    component: () => import('@/views/UnavailableView.vue'),
    meta: { public: true, title: '服务暂时不可用' },
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
        // 保留 home 路由名供登录、改密和旧链接使用；全局守卫负责权限落点。
        component: () => import('@/views/NoModulesView.vue'),
        meta: { title: '业务模块' },
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
        path: 'system/users/:id',
        name: 'system-user-detail',
        component: () => import('@/modules/system/users/UserDetailPage.vue'),
        meta: { title: '用户详情', resource: 'system.users', menuPath: '/system/users' },
      },
      {
        path: 'system/roles',
        name: 'system-roles',
        component: () => import('@/modules/system/roles/RoleWorkspace.vue'),
        meta: { title: '角色与权限', resource: 'system.roles' },
      },
      {
        // 和列表是同一个页面：左边列表，右边地址里这个角色的详情。
        path: 'system/roles/:roleId',
        name: 'system-role-detail',
        component: () => import('@/modules/system/roles/RoleWorkspace.vue'),
        // menuPath：侧栏高亮挂到「角色与权限」下。
        meta: { title: '角色与权限', resource: 'system.roles', menuPath: '/system/roles' },
      },
      {
        // 权限配置已并入「角色与权限」，旧书签和链接自动带着角色跳过去。
        path: 'system/permissions',
        name: 'system-permissions',
        redirect: to => typeof to.query.roleId === 'string' && to.query.roleId
          ? { name: 'system-role-detail', params: { roleId: to.query.roleId }, query: {} }
          : { name: 'system-roles', query: {} },
      },
      {
        path: 'system/roles/:roleId/grants',
        name: 'system-role-grants',
        redirect: to => ({ name: 'system-role-detail', params: { roleId: String(to.params.roleId) } }),
      },
      {
        path: 'system/scheduler',
        name: 'system-scheduler',
        component: () => import('@/modules/system/scheduler/SchedulerList.vue'),
        meta: { title: '任务调度', resource: 'system.scheduler' },
      },
      {
        path: 'system/sessions',
        name: 'system-sessions',
        component: () => import('@/modules/system/sessions/SessionList.vue'),
        meta: { title: '在线用户', resource: 'system.users' },
      },
      {
        path: 'system/login-logs',
        name: 'system-login-logs',
        component: () => import('@/modules/system/sessions/LoginLogList.vue'),
        meta: { title: '登录日志', resource: 'system.audit' },
      },
      {
        path: 'system/audit',
        name: 'system-audit',
        component: () => import('@/modules/system/audit/AuditList.vue'),
        meta: { title: '操作日志', resource: 'system.audit' },
      },
      {
        path: 'system/ip-whitelist',
        name: 'system-ip-whitelist',
        component: () => import('@/modules/system/ip-whitelist/IpWhitelistList.vue'),
        meta: { title: '访问白名单', resource: 'system.ip_whitelist' },
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
        meta: { title: '行业场景码表', resource: 'codebook.scenarios' },
      },
      {
        path: 'codebook/area-codes',
        name: 'codebook-area-codes',
        component: () => import('@/modules/codebook/area-codes/AreaCodeList.vue'),
        meta: { title: '省市区编码表', resource: 'codebook.area_codes' },
      },
      {
        path: 'codebook/thinktank/file-types',
        name: 'codebook-thinktank-file-types',
        component: () => import('@/modules/codebook/thinktank/ThinktankDictList.vue'),
        meta: { title: '文件类别码表', resource: 'codebook.thinktank_file_types', dictSlug: 'file-types' },
      },
      {
        path: 'codebook/thinktank/departments',
        name: 'codebook-thinktank-departments',
        component: () => import('@/modules/codebook/thinktank/ThinktankDictList.vue'),
        meta: { title: '客户部门归属码表', resource: 'codebook.thinktank_departments', dictSlug: 'departments' },
      },
      {
        path: 'codebook/thinktank/industries',
        name: 'codebook-thinktank-industries',
        component: () => import('@/modules/codebook/thinktank/ThinktankDictList.vue'),
        meta: { title: '行业类别码表', resource: 'codebook.thinktank_industries', dictSlug: 'industries' },
      },
      {
        path: 'codebook/thinktank/product-types',
        name: 'codebook-thinktank-product-types',
        component: () => import('@/modules/codebook/thinktank/ThinktankDictList.vue'),
        meta: { title: '产品类别码表', resource: 'codebook.thinktank_product_types', dictSlug: 'product-types' },
      },
      {
        path: 'codebook/thinktank/provinces',
        name: 'codebook-thinktank-provinces',
        component: () => import('@/modules/codebook/thinktank/ThinktankDictList.vue'),
        meta: { title: '省份码表', resource: 'codebook.thinktank_provinces', dictSlug: 'provinces' },
      },
      {
        path: 'codebook/thinktank/market-categories',
        name: 'codebook-thinktank-market-categories',
        component: () => import('@/modules/codebook/thinktank/ThinktankDictList.vue'),
        meta: { title: '市场类别码表', resource: 'codebook.thinktank_market_categories', dictSlug: 'market-categories' },
      },
      {
        path: 'policy/sources',
        name: 'policy-sources',
        component: () => import('@/modules/policy/sources/SourceList.vue'),
        meta: { title: '信源管理', resource: 'policy.sources' },
      },
      {
        path: 'policy/sources/:id',
        name: 'policy-source-review',
        component: () => import('@/modules/policy/sources/SourceReview.vue'),
        meta: { title: '信源详情', resource: 'policy.sources', menuPath: '/policy/sources' },
      },
      {
        path: 'policy/crawler-monitoring',
        name: 'policy-crawler-monitoring',
        component: () => import('@/modules/policy/crawler-monitoring/CrawlerMonitoring.vue'),
        meta: { title: '爬虫监测', resource: 'policy.crawler_monitoring' },
      },
      {
        path: 'policy/crawler-config',
        name: 'policy-crawler-config',
        component: () => import('@/modules/policy/crawler-config/CrawlerConfigReport.vue'),
        meta: { title: '爬虫配置统计', resource: 'policy.crawler_config' },
      },
      {
        path: 'policy/base-tags',
        name: 'policy-base-tags',
        component: () => import('@/modules/policy/base-tags/BaseTagList.vue'),
        meta: { title: '政策基础标签表', resource: 'policy.base_tags' },
      },
      {
        // 核对页：从列表带着筛选和位置进来，可翻上一条、下一条。
        path: 'policy/base-tags/:id',
        name: 'policy-base-tag-review',
        component: () => import('@/modules/policy/base-tags/BaseTagReview.vue'),
        meta: { title: '政策基础标签详情', resource: 'policy.base_tags', menuPath: '/policy/base-tags' },
      },
      {
        path: 'policy/interpretations',
        name: 'policy-interpretations',
        component: () => import('@/modules/policy/interpretations/InterpretationList.vue'),
        meta: { title: '政策解读列表', resource: 'policy.interpretations' },
      },
      {
        path: 'policy/interpretations/:id',
        name: 'policy-interpretation-review',
        component: () => import('@/modules/policy/interpretations/InterpretationReview.vue'),
        meta: { title: '政策解读详情', resource: 'policy.interpretations', menuPath: '/policy/interpretations' },
      },
      {
        path: 'policy/scenario-candidates',
        name: 'policy-scenario-candidates',
        component: () => import('@/modules/policy/scenario-candidates/CandidateList.vue'),
        meta: { title: '新增场景审核', resource: 'policy.scenario_candidates' },
      },
      {
        // 原来单个场景的审核页，现在在列表行里决定：旧地址转到列表，筛出这个场景并展开
        path: 'policy/scenario-candidates/:id',
        redirect: to => ({ name: 'policy-scenario-candidates', query: { focus: String(to.params.id) } }),
      },
      {
        path: 'tender/statistics',
        name: 'tender-statistics',
        component: () => import('@/modules/tender/TenderStatistics.vue'),
        meta: { title: '招标统计分析', resource: 'tender.statistics' },
      },
      {
        path: 'tender/purchaser',
        name: 'tender-purchaser',
        component: () => import('@/modules/tender/PurchaserList.vue'),
        meta: { title: '招标基础数据', resource: 'tender.purchaser' },
      },
      {
        path: 'tender/purchaser/:id',
        name: 'tender-purchaser-detail',
        component: () => import('@/modules/tender/PurchaserDetail.vue'),
        meta: { title: '招标基础数据详情', resource: 'tender.purchaser', menuPath: '/tender/purchaser' },
      },
      {
        path: 'tender/winbid',
        name: 'tender-winbid',
        component: () => import('@/modules/tender/WinbidList.vue'),
        meta: { title: '中标基础数据', resource: 'tender.winbid' },
      },
      {
        path: 'tender/winbid/:id',
        name: 'tender-winbid-detail',
        component: () => import('@/modules/tender/WinbidDetail.vue'),
        meta: { title: '中标基础数据详情', resource: 'tender.winbid', menuPath: '/tender/winbid' },
      },
      {
        path: 'thinktank/statistics',
        name: 'thinktank-statistics',
        component: () => import('@/modules/thinktank/statistics/ThinktankStatistics.vue'),
        meta: { title: '智库统计', resource: 'thinktank.statistics' },
      },
      {
        path: 'thinktank/knowledge',
        name: 'thinktank-knowledge',
        component: () => import('@/modules/thinktank/knowledge/KnowledgeList.vue'),
        meta: { title: '资料库', resource: 'thinktank.knowledge' },
      },
      {
        path: 'thinktank/knowledge/:id',
        name: 'thinktank-knowledge-preview',
        component: () => import('@/modules/thinktank/knowledge/KnowledgePreview.vue'),
        meta: { title: '资料库文件预览', resource: 'thinktank.knowledge', menuPath: '/thinktank/knowledge' },
      },
      {
        path: 'thinktank/reports',
        name: 'thinktank-reports',
        component: () => import('@/modules/thinktank/reports/ReportList.vue'),
        meta: { title: '报告库', resource: 'thinktank.reports' },
      },
      {
        path: 'thinktank/reports/:id',
        name: 'thinktank-report-preview',
        component: () => import('@/modules/thinktank/reports/ReportPreview.vue'),
        meta: { title: '报告库文件预览', resource: 'thinktank.reports', menuPath: '/thinktank/reports' },
      },
      {
        path: 'thinktank/proposals',
        name: 'thinktank-proposals',
        component: () => import('@/modules/thinktank/proposals/ProposalList.vue'),
        meta: { title: '方案库', resource: 'thinktank.proposals' },
      },
      {
        path: 'thinktank/proposals/:id',
        name: 'thinktank-proposal-preview',
        component: () => import('@/modules/thinktank/proposals/ProposalPreview.vue'),
        meta: { title: '方案库文件预览', resource: 'thinktank.proposals', menuPath: '/thinktank/proposals' },
      },
      {
        path: 'thinktank/favorites',
        name: 'thinktank-favorites',
        component: () => import('@/modules/thinktank/favorites/FavoritesList.vue'),
        meta: { title: '我的收藏', resource: 'thinktank.favorites' },
      },
      {
        path: 'ai/prompts',
        name: 'ai-prompts',
        component: () => import('@/modules/ai/prompts/PromptListPage.vue'),
        meta: { title: '提示词模板', resource: 'ai.prompts' },
      },
      {
        // 新建是 /ai/prompts/new，保存后同一条路由换成模板 ID。
        path: 'ai/prompts/:id',
        name: 'ai-prompt-edit',
        component: () => import('@/modules/ai/prompts/PromptEditorPage.vue'),
        meta: { title: '提示词模板', resource: 'ai.prompts', menuPath: '/ai/prompts' },
      },
      {
        path: 'ai/batch-runs',
        name: 'ai-batch-runs',
        component: () => import('@/modules/ai/batch/BatchRunsPage.vue'),
        meta: { title: '批量任务', resource: 'ai.batch_runs' },
      },
      {
        path: 'ai/models',
        name: 'ai-models',
        component: () => import('@/modules/ai/models/ModelList.vue'),
        meta: { title: '模型配置', resource: 'ai.models' },
      },
      {
        path: 'ai/billing',
        name: 'ai-billing',
        component: () => import('@/modules/ai/billing/BillingPage.vue'),
        meta: { title: '费用账单', resource: 'ai.billing' },
      },
      {
        path: 'forbidden',
        name: 'forbidden',
        component: () => import('@/views/ForbiddenView.vue'),
        meta: { title: '无权访问' },
      },
      {
        // 限定公司网络的模块（智库）被拦下：不在公司网络、也没有自己的有效白名单。不挂 resource：谁被拦都能看到说明。
        path: 'network-denied',
        name: 'network-denied',
        component: () => import('@/views/NetworkDeniedView.vue'),
        meta: { title: '当前网络不能访问' },
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
