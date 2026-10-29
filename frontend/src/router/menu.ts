export const ROUTE_BY_NAME: Record<string, string> = {
  'system-users': '/system/users',
  'system-roles': '/system/roles',
  'system-permissions': '/system/permissions',
  'system-scheduler': '/system/scheduler',
  'system-sessions': '/system/sessions',
  'system-login-logs': '/system/login-logs',
  'system-audit': '/system/audit',
  'codebook-policy-types': '/codebook/policy-types',
  'codebook-scenarios': '/codebook/scenarios',
  'codebook-area-codes': '/codebook/area-codes',
  'policy-sources': '/policy/sources',
  'policy-crawler-monitoring': '/policy/crawler-monitoring',
  'policy-crawler-config': '/policy/crawler-config',
  'policy-base-tags': '/policy/base-tags',
  'policy-interpretations': '/policy/interpretations',
  'ai-prompts': '/ai/prompts',
  'ai-batch-runs': '/ai/batch-runs',
  'ai-chat': '/ai/chat',
  'ai-models': '/ai/models',
  'ai-billing': '/ai/billing',
}

export function pathForRouteName(routeName: string | null): string | null {
  if (!routeName) {
    return null
  }
  return ROUTE_BY_NAME[routeName] ?? null
}
