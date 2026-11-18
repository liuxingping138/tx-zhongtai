import type { ResourceNode } from '@/api/types'
import { rank, type ModuleEntry, type ModuleGroup } from './catalog'
import type { GrantLevel } from './levels'
import { levelOf, type Grants } from './matrix'

const WRITE_LABELS: Record<string, string> = {
  create: '上传',
  update: '编辑、上传与删除',
  delete: '删除',
}

export interface ThinktankLibraryScope {
  code: string
  name: string
  dimensions: ModuleGroup[]
}

export function isThinktankScopeCode(code: string): boolean {
  return code.startsWith('thinktank.file_type.') || code.startsWith('thinktank.industry_type.')
}

function cleanScopeItemName(raw: string): string {
  return raw.replace(/^(文件类型|行业类型)[：:]\s*/, '').trim() || raw
}

function toScopeEntry(node: ResourceNode): ModuleEntry {
  const actions = node.actions ?? []
  const hasExport = actions.some(a => a.required_level === 'EXPORT')
  const writes = actions
    .filter(a => a.required_level === 'FULL')
    .map(a => WRITE_LABELS[a.action_code] ?? a.action_code)
  const levels: GrantLevel[] = ['NONE', 'READ']
  if (hasExport) levels.push('EXPORT')
  if (writes.length) levels.push('FULL')
  return {
    code: node.code,
    name: cleanScopeItemName(node.name),
    levels,
    writes: [...new Set(writes)],
  }
}

function buildDimensionGroup(dimNode: ResourceNode): ModuleGroup | null {
  if (dimNode.node_type !== 'directory' || !dimNode.published) return null
  const modules = (dimNode.children ?? [])
    .filter(item => item.node_type === 'resource' && item.published)
    .map(toScopeEntry)
  return modules.length ? { code: dimNode.code, name: dimNode.name, modules } : null
}

function buildLibraryScope(libNode: ResourceNode): ThinktankLibraryScope | null {
  if (libNode.node_type !== 'resource' || !libNode.published) return null
  const dimensions = (libNode.children ?? [])
    .map(buildDimensionGroup)
    .filter((item): item is ModuleGroup => item !== null)
  return dimensions.length ? { code: libNode.code, name: libNode.name, dimensions } : null
}

/**
 * 提取「智库」下各子库（知识库，及未来报告库、方案库等 6~7 个子库）的数据范围维度。
 * 结构：thinktank(directory) -> 子库(resource) -> 维度(directory) -> 范围项(resource)。
 */
export function thinktankLibraries(tree: ResourceNode[]): ThinktankLibraryScope[] {
  const thinktank = tree.find(node => node.code === 'thinktank')
  return (thinktank?.children ?? [])
    .map(buildLibraryScope)
    .filter((item): item is ThinktankLibraryScope => item !== null)
}

/** 智库数据范围编码 -> 可读名称，用于保存确认弹窗展示。 */
export function thinktankScopeNames(libraries: ThinktankLibraryScope[]): Record<string, string> {
  const out: Record<string, string> = {}
  for (const lib of libraries) {
    for (const dim of lib.dimensions) {
      for (const item of dim.modules) {
        out[item.code] = `智库·${lib.name} / ${dim.name}：${item.name}`
      }
    }
  }
  return out
}

/** 判断某数据维度是否处于「全部范围（跟随子库菜单档位）」状态。 */
export function isDimensionAllMode(dimension: ModuleGroup, grants: Grants, menuLevel: GrantLevel): boolean {
  if (menuLevel === 'NONE' || !dimension.modules.length) return false
  return dimension.modules.every(item => levelOf(grants, item.code) === menuLevel)
}

/** 将某数据维度一键设为「全部范围（跟随子库菜单档位）」。 */
export function applyDimensionAllMode(dimension: ModuleGroup, grants: Grants, menuLevel: GrantLevel): Grants {
  const next = { ...grants }
  for (const item of dimension.modules) {
    next[item.code] = menuLevel
  }
  return next
}

/** 按子库菜单档位上限收敛维度内各项可选档位（例如菜单为仅查看时，数据范围不可勾导出/管理）。 */
export function capDimensionToMenuLevel(dimension: ModuleGroup, menuLevel: GrantLevel): ModuleGroup {
  const maxRank = rank(menuLevel)
  return {
    ...dimension,
    modules: dimension.modules.map(item => ({
      ...item,
      levels: item.levels.filter(lvl => rank(lvl) <= maxRank),
    })),
  }
}

export interface DiffEntry {
  code: string
  from: GrantLevel
  to: GrantLevel
  label?: string
}

function tryCollapseDimension(
  libName: string,
  dim: ModuleGroup,
  byCode: Map<string, DiffEntry>,
): DiffEntry | null {
  if (!dim.modules.length) return null
  const first = byCode.get(dim.modules[0]!.code)
  if (!first) return null
  const allSame = dim.modules.every(item => {
    const d = byCode.get(item.code)
    return d !== undefined && d.from === first.from && d.to === first.to
  })
  if (!allSame) return null
  return {
    code: dim.code,
    from: first.from,
    to: first.to,
    label: `智库·${libName} / ${dim.name}（全部 ${dim.modules.length} 项）`,
  }
}

/**
 * 将整组同步变化的智库数据维度折叠为 1 条修改摘要，避免勾选 1 个「知识库」时弹窗和底部栏显示 29 项修改。
 */
export function collapseScopeDiffs(libraries: ThinktankLibraryScope[], diffs: DiffEntry[]): DiffEntry[] {
  if (!diffs.length || !libraries.length) return diffs
  const byCode = new Map(diffs.map(d => [d.code, d]))
  const collapsedCodes = new Set<string>()
  const summaryByFirstCode = new Map<string, DiffEntry>()

  for (const lib of libraries) {
    for (const dim of lib.dimensions) {
      const summary = tryCollapseDimension(lib.name, dim, byCode)
      if (!summary) continue
      summaryByFirstCode.set(dim.modules[0]!.code, summary)
      for (const item of dim.modules) collapsedCodes.add(item.code)
    }
  }

  const out: DiffEntry[] = []
  for (const d of diffs) {
    const summary = summaryByFirstCode.get(d.code)
    if (summary) out.push(summary)
    if (!collapsedCodes.has(d.code)) out.push(d)
  }
  return out
}

function syncDimensionOnMenuChange(
  dim: ModuleGroup,
  prev: Grants,
  out: Grants,
  prevMenu: GrantLevel,
  nextMenu: GrantLevel,
): void {
  if (nextMenu === 'NONE') {
    for (const item of dim.modules) out[item.code] = 'NONE'
    return
  }
  const wasAllNone = dim.modules.every(item => levelOf(prev, item.code) === 'NONE')
  const wasFollowingMenu = isDimensionAllMode(dim, prev, prevMenu)
  if (wasAllNone || wasFollowingMenu) {
    for (const item of dim.modules) out[item.code] = nextMenu
    return
  }
  for (const item of dim.modules) {
    if (rank(levelOf(out, item.code)) > rank(nextMenu)) out[item.code] = nextMenu
  }
}

/**
 * 当管理员在「菜单权限」修改了智库某个子库（如知识库）的档位时，联动同步其数据维度：
 * 1. 子库关闭（NONE）-> 清空该子库下全部数据范围；
 * 2. 子库开通或调档 -> 若某维度原本全空或处于「全部跟随」状态，自动同步为新档位；
 *    若某维度处于「指定范围」且新菜单档位降低，则将超出菜单档位的项收敛到新菜单档位。
 */
export function syncThinktankScopesWithMenu(
  libraries: ThinktankLibraryScope[],
  prev: Grants,
  next: Grants,
): Grants {
  let out: Grants | null = null
  for (const lib of libraries) {
    const prevMenu = levelOf(prev, lib.code)
    const nextMenu = levelOf(next, lib.code)
    if (prevMenu === nextMenu) continue
    out = out ?? { ...next }
    for (const dim of lib.dimensions) {
      syncDimensionOnMenuChange(dim, prev, out, prevMenu, nextMenu)
    }
  }
  return out ?? next
}
