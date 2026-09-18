export const ROUTE_BY_NAME: Record<string, string> = {
  'system-users': '/system/users',
  'system-roles': '/system/roles',
  'system-permissions': '/system/permissions',
  'system-audit': '/system/audit',
  'codebook-policy-types': '/codebook/policy-types',
  'codebook-scenarios': '/codebook/scenarios',
}

export function pathForRouteName(routeName: string | null): string | null {
  if (!routeName) {
    return null
  }
  return ROUTE_BY_NAME[routeName] ?? null
}
