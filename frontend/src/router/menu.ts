export const ROUTE_BY_NAME: Record<string, string> = {
  'system-users': '/system/users',
  'system-roles': '/system/roles',
  'system-permissions': '/system/permissions',
  'system-scheduler': '/system/scheduler',
  'system-sessions': '/system/sessions',
  'system-login-logs': '/system/login-logs',
  'system-audit': '/system/audit',
  'system-ip-whitelist': '/system/ip-whitelist',
  'codebook-policy-types': '/codebook/policy-types',
  'codebook-scenarios': '/codebook/scenarios',
  'codebook-area-codes': '/codebook/area-codes',
  'codebook-thinktank-file-types': '/codebook/thinktank/file-types',
  'codebook-thinktank-departments': '/codebook/thinktank/departments',
  'codebook-thinktank-industries': '/codebook/thinktank/industries',
  'codebook-thinktank-product-types': '/codebook/thinktank/product-types',
  'codebook-thinktank-provinces': '/codebook/thinktank/provinces',
  'codebook-thinktank-market-categories': '/codebook/thinktank/market-categories',
  'policy-sources': '/policy/sources',
  'policy-crawler-monitoring': '/policy/crawler-monitoring',
  'policy-crawler-config': '/policy/crawler-config',
  'policy-base-tags': '/policy/base-tags',
  'policy-interpretations': '/policy/interpretations',
  'policy-scenario-candidates': '/policy/scenario-candidates',
  'tender-statistics': '/tender/statistics',
  'tender-purchaser': '/tender/purchaser',
  'tender-winbid': '/tender/winbid',
  'thinktank-knowledge': '/thinktank/knowledge',
  'thinktank-reports': '/thinktank/reports',
  'thinktank-proposals': '/thinktank/proposals',
  'thinktank-favorites': '/thinktank/favorites',
  'ai-prompts': '/ai/prompts',
  'ai-batch-runs': '/ai/batch-runs',
  'ai-models': '/ai/models',
  'ai-billing': '/ai/billing',
}

export function pathForRouteName(routeName: string | null): string | null {
  if (!routeName) {
    return null
  }
  return ROUTE_BY_NAME[routeName] ?? null
}
