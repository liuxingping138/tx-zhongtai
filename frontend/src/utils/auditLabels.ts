export const MODULE_LABELS: Record<string, string> = {
  auth: '登录认证',
  iam: '身份认证',
  system: '系统管理',
  'system.users': '用户管理',
  'system.roles': '角色与权限',
  'system.permissions': '权限分配',
  'system.audit': '操作日志',
  'system.scheduler': '任务调度',
  policy: '政策',
  'policy.sources': '信源管理',
  'policy.base_tags': '政策基础标签表',
  'policy.interpretations': '政策解读列表',
  'policy.scenario_candidates': '新增场景审核',
  'policy.crawler_monitoring': '爬虫监测',
  'policy.crawler_config': '爬虫配置统计',
  codebook: '码表管理',
  'codebook.policy_types': '政策类型码表',
  'codebook.scenarios': '行业场景码表',
  'codebook.area_codes': '省市区编码表',
  customer: '客户',
  tender: '招投标',
  ai: 'AI提问',
  'ai.prompts': '提示词模板',
  'ai.batch_runs': '批量任务',
  'ai.models': '模型配置',
  'ai.billing': '费用账单',
  'ai.releases': '模板上线',
}

export const ACTION_LABELS: Record<string, string> = {
  login: '登录',
  refresh: '刷新令牌',
  logout: '退出登录',
  logout_all: '退出全部会话',
  password_change: '修改密码',
  create: '新增',
  update: '编辑',
  import: '导入',
  export: '导出',
  reset_password: '重置密码',
  revoke_sessions: '强制下线',
  revoke_session: '下线一台设备',
  unlock: '解除登录锁定',
  delete: '删除',
  assign_roles: '分配角色',
  protect: '保护校验',
  grant: '授权',
  catalog_sync: '同步清单',
  admin_create: '创建管理员',
  authorize: '鉴权',
  list: '查询列表',
  read: '查看',
  cleanup: '清理',
  execute: '执行任务',
  purge: '清空',
  run: '运行',
  stop: '停止',
  ask: '试发 / 样本试跑',
  publish: '上线 / 下线',
  sync_scenarios: '同步新增场景',
  decide: '决定新增场景',
  resolve: '补码',
  sync: '同步',
}

export function moduleLabel(code: string | null | undefined): string {
  if (!code) {
    return '-'
  }
  return MODULE_LABELS[code] || code
}

export function actionLabel(code: string | null | undefined): string {
  if (!code) {
    return '-'
  }
  return ACTION_LABELS[code] || code
}

/** 业务模块 = 顶部菜单目录 -> 它包含的模块编码第一段。登录、退出、改密码（auth / iam）都算系统管理；省市区编码在码表管理下（用户定的）。
 * 客户、招投标还没有模块，不列出来（不给占位业务暴露空入口）。 */
export const DIRECTORY_ROOTS: Record<string, string[]> = {
  系统管理: ['auth', 'iam', 'system'],
  政策: ['policy'],
  码表管理: ['codebook'],
  AI提问: ['ai'],
}
export const DIRECTORIES = Object.keys(DIRECTORY_ROOTS)

/** 类型 = 业务线编码 -> 中文。审计服务入库时算好存在 business_line（policy / customer / tender）。 */
export const LINE_LABELS: Record<string, string> = { policy: '政策', customer: '客户', tender: '招投标' }
export const LINES = Object.keys(LINE_LABELS)

function rootOf(code: string | null | undefined): string {
  return (code || '').split('.')[0] || ''
}

export function directoryLabel(code: string | null | undefined): string {
  const root = rootOf(code)
  return DIRECTORIES.find(name => DIRECTORY_ROOTS[name]?.includes(root)) || '-'
}

/** 类型列：系统管理、码表管理不属于哪条业务线，以及查不到模板类型的早先 AI 事件，显示「-」。 */
export function businessLineLabel(line: string | null | undefined): string {
  return (line && LINE_LABELS[line]) || '-'
}

/** 选中的业务模块 -> 请求里的 module_root（模块编码第一段）。 */
export function directoryRoots(directories: string[]): string[] {
  return directories.flatMap(name => DIRECTORY_ROOTS[name] ?? [])
}

/** 「模块」选项随「业务模块」收窄：没选业务模块时全列。 */
export function modulesInDirectories(codes: string[], directories: string[]): string[] {
  if (!directories.length) return codes
  const roots = new Set(directoryRoots(directories))
  return codes.filter(code => roots.has(rootOf(code)))
}
