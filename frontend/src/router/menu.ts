export const ROUTE_BY_NAME: Record<string, string> = {
  'system-users': '/system/users',
  'system-roles': '/system/roles',
  'system-permissions': '/system/permissions',
  'system-audit': '/system/audit',
  'codebook-policy-types': '/codebook/policy-types',
  'codebook-scenarios': '/codebook/scenarios',
  'codebook-area-codes': '/codebook/area-codes',
  'policy-sources': '/policy/sources',
  'policy-base-tags': '/policy/base-tags',
  'policy-interpretations': '/policy/interpretations',
}

export function pathForRouteName(routeName: string | null): string | null {
  if (!routeName) {
    return null
  }
  return ROUTE_BY_NAME[routeName] ?? null
}
