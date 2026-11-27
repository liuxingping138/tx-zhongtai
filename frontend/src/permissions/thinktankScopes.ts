import type { ResourceNode } from '@/api/types'
import { isThinktankDownloadCode, rank, type ModuleEntry, type ModuleGroup } from './catalog'
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
  downloadCode?: string
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
  const downloadChild = (libNode.children ?? []).find(
    child => child.node_type === 'resource' && child.published && isThinktankDownloadCode(child.code),
  )
  const dimensions = (libNode.children ?? [])
    .map(buildDimensionGroup)
    .filter((item): item is ModuleGroup => item !== null)
  return dimensions.length
    ? {
        code: libNode.code,
        name: libNode.name,
        ...(downloadChild ? { downloadCode: downloadChild.code } : {}),
        dimensions,
      }
    : null
}

/**
 * 提取「智库」下各子库（资料库，及报告库、方案库等子库）的数据范围维度。
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

/** 将某数据维度一键设为指定档位（用于「全部清空 / 全设为仅查看 / 查看和导出 / 可管理」批量操作）。 */
export function setDimensionLevel(dimension: ModuleGroup, grants: Grants, level: GrantLevel): Grants {
  const next = { ...grants }
  for (const item of dimension.modules) {
    next[item.code] = level
  }
  return next
}

/** 将某数据维度一键设为「全部范围（跟随子库菜单档位）」。 */
export function applyDimensionAllMode(dimension: ModuleGroup, grants: Grants, menuLevel: GrantLevel): Grants {
  return setDimensionLevel(dimension, grants, menuLevel)
}

/** 统计某数据维度下与原始值不同的条目数量。 */
export function countDimensionChanges(dimension: ModuleGroup, grants: Grants, original: Grants): number {
  return dimension.modules.filter(item => levelOf(grants, item.code) !== levelOf(original, item.code)).length
}

function shortDimensionLabel(name: string): string {
  return name.replace(/(类型)?范围$/, '').trim() || name
}

/** 生成智库子库在「菜单权限」行旁展示的数据范围摘要文案；未开通子库时返回空串。 */
export function scopeBadgeText(lib: ThinktankLibraryScope, grants: Grants): string {
  const menuLevel = levelOf(grants, lib.code)
  if (menuLevel === 'NONE' || !lib.dimensions.length) return ''
  const counts = lib.dimensions.map(dim => ({
    dim,
    opened: dim.modules.filter(item => levelOf(grants, item.code) !== 'NONE').length,
  }))
  if (counts.every(c => c.opened === 0)) return '待选数据范围'
  const allFollow = lib.dimensions.every(dim => isDimensionAllMode(dim, grants, menuLevel))
  if (allFollow) return '数据范围：全部'
  const parts = counts.map(({ dim, opened }) => `${shortDimensionLabel(dim.name)} ${opened}/${dim.modules.length}`)
  return `范围：${parts.join(' · ')}`
}

/** 找出已开通菜单权限、但至少有一个数据维度尚未勾选任何项的子库（用于保存前防忘配提醒）。 */
export function findIncompleteThinktankLibraries(
  libraries: ThinktankLibraryScope[],
  grants: Grants,
): ThinktankLibraryScope[] {
  return libraries.filter(lib => {
    if (levelOf(grants, lib.code) === 'NONE' || !lib.dimensions.length) return false
    return lib.dimensions.some(dim => dim.modules.every(item => levelOf(grants, item.code) === 'NONE'))
  })
}

/** 将某子库全部数据维度一键设为指定档位（用于「全部放行」或「清空重选」）。 */
export function setLibraryDimensionsLevel(
  lib: ThinktankLibraryScope,
  grants: Grants,
  level: GrantLevel,
): Grants {
  const next = { ...grants }
  for (const dim of lib.dimensions) {
    for (const item of dim.modules) next[item.code] = level
  }
  return next
}

/** 批量生成智库子库编码 -> 范围摘要文案映射。 */
export function buildScopeBadges(libraries: ThinktankLibraryScope[], grants: Grants): Record<string, string> {
  const out: Record<string, string> = {}
  for (const lib of libraries) {
    const text = scopeBadgeText(lib, grants)
    if (text) out[lib.code] = text
  }
  return out
}

/** 拆分折叠后的变更摘要为「菜单权限」和「智库数据权限」两组，用于页签未保存计数徽章。 */
export function splitGrantDiffs(
  libraries: ThinktankLibraryScope[],
  diffs: DiffEntry[],
): { menuDiffs: DiffEntry[]; scopeDiffs: DiffEntry[] } {
  const dimCodes = new Set(libraries.flatMap(lib => lib.dimensions.map(dim => dim.code)))
  const menuDiffs: DiffEntry[] = []
  const scopeDiffs: DiffEntry[] = []
  for (const diff of diffs) {
    if (isThinktankScopeCode(diff.code) || dimCodes.has(diff.code)) scopeDiffs.push(diff)
    else menuDiffs.push(diff)
  }
  return { menuDiffs, scopeDiffs }
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
 * 将整组同步变化的智库数据维度折叠为 1 条修改摘要，避免勾选 1 个「资料库」时弹窗和底部栏显示 29 项修改。
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
  // 首次从无权限开通子库时保持数据范围为空（正向勾选、最小权限），不再后台强行全选 28 项造成「反选」困扰。
  if (prevMenu === 'NONE') {
    for (const item of dim.modules) {
      if (rank(levelOf(out, item.code)) > rank(nextMenu)) out[item.code] = nextMenu
    }
    return
  }
  // 原本已经处于「全部范围」模式的子库，随菜单升/降档自动保持同步。
  if (isDimensionAllMode(dim, prev, prevMenu)) {
    for (const item of dim.modules) out[item.code] = nextMenu
    return
  }
  // 处于「指定范围」模式且菜单降档时，将高于新菜单档位的项封顶收敛。
  for (const item of dim.modules) {
    if (rank(levelOf(out, item.code)) > rank(nextMenu)) out[item.code] = nextMenu
  }
}

/**
 * 当管理员在「菜单权限」修改了智库某个子库（如资料库）的档位时，联动同步其数据维度：
 * 1. 子库关闭（NONE）-> 清空该子库下全部数据范围与独立下载权限；
 * 2. 子库首次开通（NONE -> 其他）-> 保持数据范围为空，引导正向勾选或一键全部放行；
 * 3. 已开通子库调档 -> 原为「全部范围」时自动同步至新档位；原为「指定范围」且降档时收敛超出项。
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
    if (nextMenu === 'NONE' && lib.downloadCode) out[lib.downloadCode] = 'NONE'
    for (const dim of lib.dimensions) {
      syncDimensionOnMenuChange(dim, prev, out, prevMenu, nextMenu)
    }
  }
  return out ?? next
}

/** 智库数据权限页签一键开通子库：默认保持数据范围为空（正向勾选），随后可按需勾选或点「全部放行」。 */
export function quickOpenThinktankLibrary(
  lib: ThinktankLibraryScope,
  grants: Grants,
  level: Exclude<GrantLevel, 'NONE'>,
): Grants {
  const next = setLibraryDimensionsLevel(lib, grants, 'NONE')
  next[lib.code] = level
  return next
}
