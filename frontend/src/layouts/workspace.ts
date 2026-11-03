import { computed, type Component } from 'vue'
import { Collection, Connection, Cpu, DataAnalysis, EditPen, Files, Finished, Key, Link, MapLocation, Menu, Money, Monitor, PriceTag, Reading, Tickets, Timer, User, UserFilled, Unlock } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { pathForRouteName } from '@/router/menu'

export interface WorkspaceEntry { title: string; path: string; description: string; icon: Component }
export interface WorkspaceGroup { key: string; title: string; entries: WorkspaceEntry[] }

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
  '/system/users': '管理账号与角色分配',
  '/system/roles': '配置模块和操作权限',
  '/system/sessions': '看谁在线，按设备下线',
  '/system/login-logs': '谁在什么时候从哪里登录，失败原因和 IP 限制',
  '/system/scheduler': '配置每日同步与查看执行记录',
  '/system/audit': '追溯操作与权限变更',
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
  '/system/users': User,
  '/system/roles': Key,
  '/system/sessions': UserFilled,
  '/system/login-logs': Unlock,
  '/system/audit': Tickets,
  '/system/scheduler': Timer,
  '/ai/prompts': EditPen,
  '/ai/batch-runs': Files,
  '/ai/models': Cpu,
  '/ai/billing': Money,
}

export function useWorkspace() {
  const auth = useAuthStore()
  const groups = computed<WorkspaceGroup[]>(() => {
    const result = new Map<string, WorkspaceGroup>()
    for (const item of auth.visibleMenus) {
      const path = pathForRouteName(item.route_name)
      if (!path) continue
      const key = path.split('/')[1] || 'other'
      const parent = auth.visibleMenus.find(menu => menu.id === item.parent_id)
      if (!result.has(key)) result.set(key, { key, title: parent?.title || '业务模块', entries: [] })
      result.get(key)!.entries.push({ title: item.title, path, description: ENTRY_DESCRIPTIONS[path] || '进入业务模块', icon: entryIcons[path] || Menu })
    }
    // 模块顺序以 iam 菜单 sort_order 为准（系统管理、政策、码表管理、AI提问），前端不另行排序。
    return [...result.values()]
  })
  return { auth, groups }
}
