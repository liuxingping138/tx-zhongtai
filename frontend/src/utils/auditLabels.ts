export const MODULE_LABELS: Record<string, string> = {
  auth: '登录认证',
  iam: '身份认证',
  system: '系统管理',
  'system.users': '用户管理',
  'system.roles': '角色管理',
  'system.permissions': '权限分配',
  'system.audit': '操作日志',
  policy: '政策',
  'policy.sources': '信源管理',
  'policy.base_tags': '政策基础标签表',
  'policy.interpretations': '政策解读列表',
  'policy.crawler_monitoring': '爬虫监测',
  codebook: '码表管理',
  'codebook.policy_types': '政策类型码表',
  'codebook.scenarios': '场景码表',
  'codebook.area_codes': '省市区编码表',
  customer: '客户',
  tender: '招投标',
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
  assign_roles: '分配角色',
  protect: '保护校验',
  grant: '授权',
  catalog_sync: '同步清单',
  admin_create: '创建管理员',
  authorize: '鉴权',
  list: '查询列表',
  read: '查看',
  cleanup: '清理',
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
