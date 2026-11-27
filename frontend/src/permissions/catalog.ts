import type { ResourceNode } from '@/api/types'
import type { GrantLevel } from './levels'

/** 授权档位的界面名称，逐档包含。与后端 NONE / READ / EXPORT / FULL 一一对应。 */
export const LEVEL_TEXT: Record<GrantLevel, string> = {
  NONE: '无权限',
  READ: '仅查看',
  EXPORT: '查看和导出',
  FULL: '可管理',
}

/**
 * 动作的中文说明，按这个顺序展示（先增后改、先导入后清空）。只列「管理」档的写操作，
 * 查看和导出已经由列名说明。
 */
const WRITE_ACTIONS: [code: string, text: string][] = [
  ['execute', '立即执行任务'],
  ['create', '新增'],
  ['update', '编辑'],
  ['delete', '删除'],
  ['ask', '试发提问'],
  ['run', '运行批量任务'],
  ['stop', '停止任务'],
  ['publish', '上线、下线模板'],
  ['import', '导入 Excel'],
  ['upload_tags', '上传标签'],
  ['sync', '立即同步'],
  ['decide', '采纳、合并、驳回新增场景'],
  ['reset_password', '重置密码'],
  ['revoke_sessions', '强制下线、按设备下线'],
  ['grant', '给用户分配角色、配置角色权限'],
  // 后端另有规定：清空只有超级管理员能执行，给普通角色「管理」并不包含它。
  ['purge', '清空全表（仅超级管理员）'],
]
const WRITE_ORDER = new Map(WRITE_ACTIONS.map(([code], index) => [code, index]))
const WRITE_LABEL = new Map(WRITE_ACTIONS)
/** 同一个动作码在个别模块里说法不同。 */
const WRITE_LABEL_BY_RESOURCE: Record<string, Record<string, string>> = {
  'system.users': { delete: '删除账号', update: '编辑、解锁被锁账号' },
  'policy.ai_tagging': { update: '改打标任务设置和每日费用上限、启用或改执行时间', execute: '立即执行打标' },
  'policy.scenario_candidates': { decide: '采纳、合并、驳回新增场景（采纳、合并还要行业场景码表可管理）' },
  'thinktank.knowledge': { create: '上传文件' },
  'thinktank.reports': { create: '上传文件' },
  'thinktank.proposals': { create: '上传文件' },
}

/** 只能授予超级管理员角色的资源：用它能给别人（包括自己）加权限，后端也拒绝授给其他角色。 */
export const SUPERADMIN_ONLY = new Set(['system.permissions'])
export const SUPERADMIN_ROLE_CODE = 'superadmin'

export interface ModuleEntry {
  code: string
  name: string
  /**
   * 这个模块可选的档位，由它实际有哪些动作决定：没有导出就没有「导出」档，没有写操作就没有「管理」档，
   * 免得管理员以为多给了权限。
   */
  levels: GrantLevel[]
  /** 「管理」档包含的写操作。 */
  writes: string[]
}

export interface ModuleGroup {
  code: string
  name: string
  modules: ModuleEntry[]
}

const RANK: Record<GrantLevel, number> = { NONE: 0, READ: 1, EXPORT: 2, FULL: 3 }

export function rank(level: GrantLevel): number {
  return RANK[level]
}

function toEntry(node: ResourceNode): ModuleEntry {
  const actions = node.actions ?? []
  const hasExport = actions.some(action => action.required_level === 'EXPORT')
  const writes = actions
    .filter(action => action.required_level === 'FULL')
    .sort((a, b) => (WRITE_ORDER.get(a.action_code) ?? 99) - (WRITE_ORDER.get(b.action_code) ?? 99))
    .map(action => WRITE_LABEL_BY_RESOURCE[node.code]?.[action.action_code] ?? WRITE_LABEL.get(action.action_code) ?? action.action_code)
  const levels: GrantLevel[] = ['NONE', 'READ']
  if (hasExport) levels.push('EXPORT')
  if (writes.length) levels.push('FULL')
  return { code: node.code, name: node.name, levels, writes: [...new Set(writes)] }
}

/**
 * 把资源树整理成页面上的分组。只保留已发布模块：未开发的客户、招投标不出现在授权页，
 * 避免管理员以为勾了就能用。
 */
export function moduleGroups(tree: ResourceNode[]): ModuleGroup[] {
  const groups: ModuleGroup[] = []
  const loose: ModuleEntry[] = []
  for (const node of tree) {
    if (node.node_type === 'resource') {
      if (node.published && !SUPERADMIN_ONLY.has(node.code)) loose.push(toEntry(node))
      continue
    }
    const modules = (node.children ?? [])
      .filter(child => child.node_type === 'resource' && child.published && !SUPERADMIN_ONLY.has(child.code))
      .map(toEntry)
    if (modules.length) groups.push({ code: node.code, name: node.name, modules })
  }
  if (loose.length) groups.push({ code: '_other', name: '其他', modules: loose })
  return groups
}

/** 不在菜单里的能力。目前只有「分配角色」，单独展示，避免看成一个还能打开的旧页面。 */
export function capabilityModules(tree: ResourceNode[]): ModuleEntry[] {
  const found: ModuleEntry[] = []
  const walk = (nodes: ResourceNode[]) => {
    for (const node of nodes) {
      if (node.node_type === 'resource' && node.published && SUPERADMIN_ONLY.has(node.code)) {
        found.push({ ...toEntry(node), name: '分配角色' })
      }
      if (node.children?.length) walk(node.children)
    }
  }
  walk(tree)
  return found
}

/** 模块是否提供某一列（没有的列显示「—」）。 */
export function supports(entry: ModuleEntry, level: GrantLevel): boolean {
  return entry.levels.includes(level)
}

/** 当前档位下这一列是否勾选：档位逐档包含，高档自然覆盖低档。 */
export function isChecked(current: GrantLevel, column: GrantLevel): boolean {
  return rank(current) >= rank(column)
}

/**
 * 勾选或取消某一列后的新档位。
 * 勾上：升到这一列；取消：降到这个模块支持的、比这一列低的最高一档。
 */
export function toggleColumn(entry: ModuleEntry, current: GrantLevel, column: GrantLevel): GrantLevel {
  if (!isChecked(current, column)) return column
  const lower = entry.levels.filter(level => rank(level) < rank(column))
  return lower[lower.length - 1] ?? 'NONE'
}

/**
 * 不单设权限、跟着某个模块走的菜单：给了这个模块的权限，这几个菜单也一起看得到。
 * 写在权限说明里，免得管理员以为新菜单没人管。和后端 catalog.MENU_SPECS 的 resource_code 一致。
 */
const EXTRA_MENUS: Record<string, string[]> = {
  'system.users': ['在线用户'],
  'system.audit': ['登录日志'],
}

/** 这一行右侧的说明：「管理」具体包含什么，以及连带看得到哪些菜单。 */
export function writesHint(entry: ModuleEntry): string {
  const base = entry.writes.length ? `管理包含：${entry.writes.join('、')}` : '只读模块，没有新增或修改操作'
  const extra = EXTRA_MENUS[entry.code]
  return extra ? `${base}。同时可见「${extra.join('」「')}」菜单` : base
}

/** 一句话说明某个档位能做什么，用于用户的实际权限等只读展示。 */
export function levelHint(entry: ModuleEntry, level: GrantLevel): string {
  if (level === 'NONE') return '看不到这个模块'
  if (level === 'READ') return '可查看'
  if (level === 'EXPORT') return '可查看、导出 Excel'
  const base = entry.levels.includes('EXPORT') ? '可查看、导出 Excel' : '可查看'
  return entry.writes.length ? `${base}，还可${entry.writes.join('、')}` : base
}

/** 该模块对这个角色是否锁定（不能授予），返回锁定原因。 */
export function lockReason(code: string, roleCode: string | undefined): string {
  if (SUPERADMIN_ONLY.has(code) && roleCode !== SUPERADMIN_ROLE_CODE) {
    return '只能属于超级管理员：拥有它就能给任何人（包括自己）加权限'
  }
  return ''
}

/** 模块编码到中文名，用于保存确认等需要展示名称的地方。 */
export function moduleNames(groups: ModuleGroup[]): Record<string, string> {
  const out: Record<string, string> = {}
  for (const group of groups) {
    for (const module of group.modules) out[module.code] = `${group.name} / ${module.name}`
  }
  return out
}
