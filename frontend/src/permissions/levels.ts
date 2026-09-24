/** 逐档包含：查看 < 查看+导出 < 管理。导出单列一档：能看不等于能把整表数据带走。 */
export type GrantLevel = 'NONE' | 'READ' | 'EXPORT' | 'FULL'

const RANK: Record<GrantLevel, number> = {
  NONE: 0,
  READ: 1,
  EXPORT: 2,
  FULL: 3,
}

export function levelSatisfies(effective: string | null | undefined, required: GrantLevel): boolean {
  const rank = RANK[(effective as GrantLevel) || 'NONE'] ?? 0
  return rank >= RANK[required]
}

export function canRead(level: string | null | undefined): boolean {
  return levelSatisfies(level, 'READ')
}

export function canExport(level: string | null | undefined): boolean {
  return levelSatisfies(level, 'EXPORT')
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

/**
 * 一句话概括角色能用多少模块。全部可管理时直接说「均可管理」，
 * 不再写「12 个模块，其中 12 个可管理」这种要读两遍的句子。
 */
export function roleModuleSummary(counts?: { read: number; export: number; full: number }): string {
  const full = counts?.full ?? 0
  const opened = (counts?.read ?? 0) + (counts?.export ?? 0) + full
  if (!opened) return ''
  if (full === opened) return `${opened} 个模块 · 均可管理`
  if (!full) return `${opened} 个模块 · 仅查看或导出`
  return `${opened} 个模块 · 其中 ${full} 个可管理`
}
