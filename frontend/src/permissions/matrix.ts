import { isChecked, lockReason, supports, toggleColumn, type ModuleEntry, type ModuleGroup } from './catalog'
import type { GrantLevel } from './levels'

/** 角色权限矩阵的纯逻辑：谁被锁定、整组一列怎么勾、搜索与状态过滤怎么筛。组件只负责渲染。 */
export type Column = Exclude<GrantLevel, 'NONE'> | 'DOWNLOAD'
export type Grants = Record<string, GrantLevel>
export type PermissionStatusFilter = 'ALL' | 'OPEN' | 'CHANGED'

export const COLUMNS: { level: Column; label: string; sub: string; what: string }[] = [
  { level: 'READ', label: '查看', sub: '列表/详情', what: '打开菜单，看列表和详情' },
  { level: 'DOWNLOAD', label: '下载', sub: '原文件', what: '下载智库资料/报告/方案原文件（独立于导出 Excel）' },
  { level: 'EXPORT', label: '导出', sub: '导出 Excel', what: '导出当前列表或未定义清单 Excel' },
  { level: 'FULL', label: '管理', sub: '增删改/导入', what: '新增、编辑、上传、导入等' },
]

export function levelOf(grants: Grants, code: string): GrantLevel {
  return grants[code] ?? 'NONE'
}

export function isChanged(grants: Grants, original: Grants, code: string): boolean {
  return levelOf(grants, code) !== levelOf(original, code)
}

export function isDownloadEnabled(module: ModuleEntry, grants: Grants): boolean {
  if (!module.downloadCode) return false
  return levelOf(grants, module.code) !== 'NONE' && levelOf(grants, module.downloadCode) !== 'NONE'
}

export function supportsColumn(module: ModuleEntry, column: Column): boolean {
  if (column === 'DOWNLOAD') return Boolean(module.downloadCode)
  return supports(module, column)
}

export function isColumnChecked(module: ModuleEntry, column: Column, grants: Grants): boolean {
  if (column === 'DOWNLOAD') return isDownloadEnabled(module, grants)
  return isChecked(levelOf(grants, module.code), column)
}

export function isModuleChanged(module: ModuleEntry, grants: Grants, original: Grants): boolean {
  if (isChanged(grants, original, module.code)) return true
  return Boolean(module.downloadCode && isChanged(grants, original, module.downloadCode))
}

export function isLocked(module: ModuleEntry, roleCode: string | undefined): boolean {
  return !!lockReason(module.code, roleCode)
}

/** 按菜单名、模块编码或分组名搜索；分组名命中时整组保留。 */
export function filterGroups(groups: ModuleGroup[], keyword: string): ModuleGroup[] {
  const query = keyword.trim().toLowerCase()
  if (!query) return groups
  return groups.flatMap(group => {
    if (group.name.toLowerCase().includes(query)) return [group]
    const modules = group.modules.filter(module =>
      module.name.toLowerCase().includes(query) || module.code.toLowerCase().includes(query))
    return modules.length ? [{ ...group, modules }] : []
  })
}

/** 「特殊能力」区也能被搜到：额外带上「分配角色」「权限」两个关键词。 */
export function filterCapabilities(items: ModuleEntry[], keyword: string): ModuleEntry[] {
  const query = keyword.trim().toLowerCase()
  if (!query) return items
  return items.filter(module => `${module.name} ${module.code} 分配角色 权限`.toLowerCase().includes(query))
}

export function openedCount(group: ModuleGroup, grants: Grants): number {
  return group.modules.filter(module => levelOf(grants, module.code) !== 'NONE').length
}

function matchesStatus(
  module: ModuleEntry,
  grants: Grants,
  original: Grants,
  status: PermissionStatusFilter,
): boolean {
  if (status === 'OPEN') return levelOf(grants, module.code) !== 'NONE'
  if (status === 'CHANGED') return isModuleChanged(module, grants, original)
  return true
}

/** 联合关键词与状态（全部 / 已开通 / 已修改）过滤分组；过滤后空组隐藏。 */
export function filterGroupsByStatus(
  groups: ModuleGroup[],
  grants: Grants,
  original: Grants,
  keyword: string,
  status: PermissionStatusFilter,
): ModuleGroup[] {
  const searched = filterGroups(groups, keyword)
  if (status === 'ALL') return searched
  return searched.flatMap(group => {
    const modules = group.modules.filter(module => matchesStatus(module, grants, original, status))
    return modules.length ? [{ ...group, modules }] : []
  })
}

export function countTotalModules(groups: ModuleGroup[]): number {
  return groups.reduce((acc, group) => acc + group.modules.length, 0)
}

export function countOpenedModules(groups: ModuleGroup[], grants: Grants): number {
  return groups.reduce((acc, group) => acc + openedCount(group, grants), 0)
}

export function countChangedModules(groups: ModuleGroup[], grants: Grants, original: Grants): number {
  return groups.reduce(
    (acc, group) => acc + group.modules.filter(module => isModuleChanged(module, grants, original)).length,
    0,
  )
}

function applyModuleColumn(module: ModuleEntry, column: Column, grants: Grants, next: Grants): void {
  if (column === 'DOWNLOAD') {
    const dlCode = module.downloadCode
    if (!dlCode) return
    if (isDownloadEnabled(module, grants)) {
      next[dlCode] = 'NONE'
      return
    }
    if (levelOf(grants, module.code) === 'NONE') next[module.code] = 'READ'
    next[dlCode] = 'READ'
    return
  }
  const nextLevel = toggleColumn(module, levelOf(grants, module.code), column)
  next[module.code] = nextLevel
  if (nextLevel === 'NONE' && module.downloadCode) next[module.downloadCode] = 'NONE'
}

/** 点单个格子后的新授权；锁定或这个菜单没有这项操作时返回 null。 */
export function toggleCell(
  module: ModuleEntry, column: Column, grants: Grants, roleCode: string | undefined,
): Grants | null {
  if (isLocked(module, roleCode) || !supportsColumn(module, column)) return null
  const next = { ...grants }
  applyModuleColumn(module, column, grants, next)
  return next
}

function columnTargets(group: ModuleGroup, column: Column, roleCode: string | undefined): ModuleEntry[] {
  return group.modules.filter(module => !isLocked(module, roleCode) && supportsColumn(module, column))
}

/** 整组一列的复选框状态：没有可勾的行时 empty，不画复选框。 */
export function columnState(
  group: ModuleGroup, column: Column, grants: Grants, roleCode: string | undefined,
): { checked: boolean; indeterminate: boolean; empty: boolean } {
  const targets = columnTargets(group, column, roleCode)
  const on = targets.filter(module => isColumnChecked(module, column, grants)).length
  return { checked: targets.length > 0 && on === targets.length, indeterminate: on > 0 && on < targets.length, empty: !targets.length }
}

/** 整组一列：没勾满就全部勾上（已有更高档的保留），已勾满再点一次全部取消这一列。没有可操作的行时返回 null。 */
export function toggleGroupColumn(
  group: ModuleGroup, column: Column, grants: Grants, roleCode: string | undefined,
): Grants | null {
  const targets = columnTargets(group, column, roleCode)
  if (!targets.length) return null
  const allOn = targets.every(module => isColumnChecked(module, column, grants))
  const next = { ...grants }
  for (const module of targets) {
    if (allOn || !isColumnChecked(module, column, grants)) applyModuleColumn(module, column, grants, next)
  }
  return next
}
