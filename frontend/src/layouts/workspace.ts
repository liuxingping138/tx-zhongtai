import { computed, type Component } from 'vue'
import {
  Box, Briefcase, Collection, Connection, Cpu, DataAnalysis, Document, EditPen, Files, Finished,
  Folder, Grid, Key, Link, Lock, MapLocation, Menu, Money, Monitor, OfficeBuilding, PriceTag, Reading,
  Setting, Star, Tickets, Timer, User, UserFilled, Unlock,
} from '@element-plus/icons-vue'
import type { MenuItem } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { pathForRouteName } from '@/router/menu'

export interface WorkspaceEntry { title: string; path: string; description: string; icon: Component }
export interface WorkspaceSection { id: string; title: string; entries: WorkspaceEntry[]; emptyHint?: string }
export interface WorkspaceGroup {
  key: string
  title: string
  icon: Component
  entries: WorkspaceEntry[]
  sections?: WorkspaceSection[]
}

/** 顶部一级分类专属领域图标，践行 Google M3 导航规范 */
const DOMAIN_ICONS: Record<string, Component> = {
  policy: Reading,
  tender: Tickets,
  codebook: Collection,
  thinktank: Files,
  ai: Cpu,
  system: Setting,
}

/** 顶部「查找模块」里每个入口的用途说明。新菜单要在这里登记，没登记的会显示成「进入业务模块」（有单测兜住）。 */
export const ENTRY_DESCRIPTIONS: Record<string, string> = {
  '/policy/sources': '维护采集网站与信源信息',
  '/policy/crawler-monitoring': '按网站查看采集健康状况',
  '/policy/crawler-config': '按周、按省统计上线的爬虫栏目数',
  '/policy/interpretations': '整理政策内容与业务解读',
  '/policy/scenario-candidates': 'AI 解读出的新场景按场景决定进不进码表',
  '/policy/base-tags': '维护政策分类与基础标签',
  '/codebook/policy-types': '统一政策分类口径',
  '/codebook/scenarios': '管理行业与业务场景',
  '/codebook/area-codes': '维护省、市、区地域编码',
  '/codebook/thinktank/file-types': '维护智库资料库的文件类别枚举',
  '/codebook/thinktank/departments': '维护智库使用的客户部门归属枚举',
  '/codebook/thinktank/industries': '维护智库使用的行业类别枚举',
  '/codebook/thinktank/product-types': '维护智库使用的产品类别枚举',
  '/codebook/thinktank/provinces': '维护智库专属省份码表（含集团及全国 31 省）',
  '/codebook/thinktank/market-categories': '维护智库使用的市场类别枚举',
  '/thinktank/statistics': '三库资产总览、核心分类分布、生产消费趋势与热门贡献排行榜',
  '/thinktank/knowledge': '资料库文档查询、按文件类型与行业类型授权及操作审计',
  '/thinktank/reports': '报告库文档查询、预览、打标与操作审计',
  '/thinktank/proposals': '方案库文档查询、预览、打标与操作审计',
  '/thinktank/favorites': '集中查看、预览与管理资料库、报告库与方案库的个人收藏',
  '/system/users': '管理账号与角色分配',
  '/system/roles': '配置模块和操作权限',
  '/system/sessions': '看谁在线，按设备下线',
  '/system/login-logs': '谁在什么时候从哪里登录，失败原因和 IP 限制',
  '/system/scheduler': '配置每日同步与查看执行记录',
  '/system/audit': '追溯操作与权限变更',
  '/system/ip-whitelist': '智库只在公司网络可用，在外面使用的人由管理员按账号和 IP 开通有时效的白名单',
  '/tender/statistics': '按天、按省查看招中标接入与人工处理量',
  '/tender/purchaser': '查看原始或已审核招标数据',
  '/tender/winbid': '查看原始或已审核中标数据',
  '/ai/prompts': '写提示词、用样本试跑，管理员上线',
  '/ai/batch-runs': '用上线的模板跑这次上传的 Excel',
  '/ai/models': '维护可选模型、接入点和单价',
  '/ai/billing': '按日期、模型和用途看所有模型调用花了多少',
}

// 图标按子模块用途配置，不继承一级模块图标；同一入口在导航和查找中保持一致。
const entryIcons: Record<string, Component> = {
  '/policy/sources': Link,
  '/policy/crawler-monitoring': Monitor,
  '/policy/crawler-config': DataAnalysis,
  '/policy/interpretations': Reading,
  '/policy/scenario-candidates': Finished,
  '/policy/base-tags': PriceTag,
  '/codebook/policy-types': Collection,
  '/codebook/scenarios': Connection,
  '/codebook/area-codes': MapLocation,
  '/codebook/thinktank/file-types': Folder,
  '/codebook/thinktank/departments': OfficeBuilding,
  '/codebook/thinktank/industries': Grid,
  '/codebook/thinktank/product-types': Box,
  '/codebook/thinktank/provinces': MapLocation,
  '/codebook/thinktank/market-categories': PriceTag,
  '/thinktank/statistics': DataAnalysis,
  '/thinktank/knowledge': Reading,
  '/thinktank/reports': Document,
  '/thinktank/proposals': Briefcase,
  '/thinktank/favorites': Star,
  '/system/users': User,
  '/system/roles': Key,
  '/system/sessions': UserFilled,
  '/system/login-logs': Unlock,
  '/system/audit': Tickets,
  '/system/scheduler': Timer,
  '/system/ip-whitelist': Lock,
  '/tender/statistics': DataAnalysis,
  '/tender/purchaser': Tickets,
  '/tender/winbid': Finished,
  '/ai/prompts': EditPen,
  '/ai/batch-runs': Files,
  '/ai/models': Cpu,
  '/ai/billing': Money,
}

function buildEntry(item: MenuItem, path: string): WorkspaceEntry {
  return {
    title: item.title,
    path,
    description: ENTRY_DESCRIPTIONS[path] || '进入业务模块',
    icon: entryIcons[path] || Menu,
  }
}

function buildRootMap(menus: readonly MenuItem[]) {
  const byId = new Map<string, MenuItem>(menus.map(m => [m.id, m]))
  const rootOf = (menu: MenuItem): MenuItem => {
    let cur = menu
    while (cur.parent_id && byId.has(cur.parent_id)) {
      cur = byId.get(cur.parent_id)!
    }
    return cur
  }
  return { byId, rootOf }
}

function ensureSection(
  sectionsByRoot: Map<string, Map<string, WorkspaceSection>>,
  rootId: string,
  dir: MenuItem,
): WorkspaceSection {
  let map = sectionsByRoot.get(rootId)
  if (!map) {
    map = new Map()
    sectionsByRoot.set(rootId, map)
  }
  let sec = map.get(dir.id)
  if (!sec) {
    sec = { id: dir.id, title: dir.title, entries: [], emptyHint: '暂无码表' }
    map.set(dir.id, sec)
  }
  return sec
}

function appendEntryToGroup(
  result: Map<string, WorkspaceGroup>,
  groupByRootId: Map<string, WorkspaceGroup>,
  sectionsByRoot: Map<string, Map<string, WorkspaceSection>>,
  item: MenuItem,
  byId: Map<string, MenuItem>,
  rootOf: (m: MenuItem) => MenuItem,
) {
  const path = pathForRouteName(item.route_name)
  if (!path) return
  const key = path.split('/')[1] || 'other'
  const root = rootOf(item)
  if (!result.has(key)) {
    const group: WorkspaceGroup = { key, title: root.title || '业务模块', icon: DOMAIN_ICONS[key] || Menu, entries: [] }
    result.set(key, group)
    groupByRootId.set(root.id, group)
  }
  const entry = buildEntry(item, path)
  result.get(key)!.entries.push(entry)
  const parent = item.parent_id ? byId.get(item.parent_id) : undefined
  if (parent && parent.id !== root.id) {
    ensureSection(sectionsByRoot, root.id, parent).entries.push(entry)
  }
}

function buildWorkspaceGroups(menus: readonly MenuItem[]): WorkspaceGroup[] {
  const { byId, rootOf } = buildRootMap(menus)
  const result = new Map<string, WorkspaceGroup>()
  const groupByRootId = new Map<string, WorkspaceGroup>()
  const sectionsByRoot = new Map<string, Map<string, WorkspaceSection>>()

  for (const item of menus) {
    appendEntryToGroup(result, groupByRootId, sectionsByRoot, item, byId, rootOf)
  }
  for (const dir of menus) {
    if (!dir.route_name && dir.parent_id && groupByRootId.has(dir.parent_id)) {
      ensureSection(sectionsByRoot, dir.parent_id, dir)
    }
  }
  for (const [rootId, secMap] of sectionsByRoot) {
    const group = groupByRootId.get(rootId)
    if (group) group.sections = [...secMap.values()]
  }
  return [...result.values()]
}

export function useWorkspace() {
  const auth = useAuthStore()
  const groups = computed<WorkspaceGroup[]>(() => buildWorkspaceGroups(auth.visibleMenus))
  return { auth, groups }
}
