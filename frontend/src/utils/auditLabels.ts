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

/** 业务模块 = 顶部菜单目录。登录、退出、改密码（auth / iam）都算系统管理；省市区编码在码表管理下（用户定的）。 */
const DIRECTORY_LABELS: Record<string, string> = {
  auth: '系统管理',
  iam: '系统管理',
  system: '系统管理',
  policy: '政策',
  codebook: '码表管理',
  ai: 'AI提问',
  customer: '客户',
  tender: '招投标',
}

/** 模板类型编码 -> 类型（与 ai-service 的 domain/categories.py 一致）。 */
const LINE_LABELS: Record<string, string> = { policy: '政策', customer: '客户', tender: '招投标' }

export function directoryLabel(code: string | null | undefined): string {
  const root = (code || '').split('.')[0] || ''
  return DIRECTORY_LABELS[root] || '-'
}

/** 类型 = 业务线（政策 / 客户 / 招投标）。政策、客户、招投标模块按目录；AI提问按事件里记的模板类型
 * （早先的事件没记，按事件目标回 AI 服务查，模板和任务都删光了才显示「-」）；系统管理、码表管理不属于哪条业务线，显示「-」。 */
export function businessLineLabel(
  code: string | null | undefined,
  changes?: Record<string, unknown> | null,
  resolved?: string,
): string {
  const root = (code || '').split('.')[0] || ''
  if (root === 'ai') {
    // 事件里记了就用记的；早先的事件没记，用按目标ID 回 AI 服务查到的（resolved）。
    const category = typeof changes?.category === 'string' ? changes.category : resolved
    return (category && LINE_LABELS[category]) || '-'
  }
  return LINE_LABELS[root] || '-'
}

/** 这一页里要回 AI 服务查类型的目标ID：AI 事件、事件里没记类型、有目标ID。 */
export function aiTargetsToResolve(rows: { module_code: string | null; target_id: string | null; changes: Record<string, unknown> | null }[]): string[] {
  const ids = rows
    .filter(row => (row.module_code || '').startsWith('ai.') && typeof row.changes?.category !== 'string' && row.target_id)
    .map(row => row.target_id as string)
  return [...new Set(ids)]
}
