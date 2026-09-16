export type GrantLevel = 'NONE' | 'READ' | 'FULL'

const RANK: Record<GrantLevel, number> = {
  NONE: 0,
  READ: 1,
  FULL: 2,
}

export function levelSatisfies(effective: string | null | undefined, required: GrantLevel): boolean {
  const rank = RANK[(effective as GrantLevel) || 'NONE'] ?? 0
  return rank >= RANK[required]
}

export function canRead(level: string | null | undefined): boolean {
  return levelSatisfies(level, 'READ')
}

export function canWrite(level: string | null | undefined): boolean {
  return levelSatisfies(level, 'FULL')
}

export interface GrantSnapshot {
  resource_code: string
  level: GrantLevel
}

export function grantsFromTree(
  nodes: { code: string; published: boolean; node_type: string; children?: unknown[] }[],
  selected: Record<string, GrantLevel>,
): GrantSnapshot[] {
  const result: GrantSnapshot[] = []
  const walk = (items: typeof nodes) => {
    for (const node of items) {
      if (node.node_type === 'resource' && node.published) {
        const level = selected[node.code] ?? 'NONE'
        result.push({ resource_code: node.code, level })
      }
      const children = (node.children ?? []) as typeof nodes
      if (children.length) {
        walk(children)
      }
    }
  }
  walk(nodes)
  return result
}

export function applyParentLevel(
  node: { published: boolean; node_type: string; code: string; children?: unknown[] },
  level: GrantLevel,
  selected: Record<string, GrantLevel>,
): Record<string, GrantLevel> {
  const next = { ...selected }
  const walk = (current: typeof node) => {
    if (current.node_type === 'resource' && current.published) {
      next[current.code] = level
    }
    for (const child of (current.children ?? []) as typeof node[]) {
      walk(child)
    }
  }
  walk(node)
  return next
}

export function grantDiff(before: GrantSnapshot[], after: GrantSnapshot[]): { code: string; from: GrantLevel; to: GrantLevel }[] {
  const prev = new Map(before.map((item) => [item.resource_code, item.level]))
  const changes: { code: string; from: GrantLevel; to: GrantLevel }[] = []
  for (const item of after) {
    const from = prev.get(item.resource_code) ?? 'NONE'
    if (from !== item.level) {
      changes.push({ code: item.resource_code, from, to: item.level })
    }
  }
  return changes
}
