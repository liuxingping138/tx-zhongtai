import { computed, type Component } from 'vue'
import { Timer, Collection, Connection, DataLine, Key, Link, MapLocation, Menu, Monitor, PriceTag, Reading, Tickets, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { pathForRouteName } from '@/router/menu'

export interface WorkspaceEntry { title: string; path: string; description: string; icon: Component }
export interface WorkspaceGroup { key: string; title: string; entries: WorkspaceEntry[] }

const descriptions: Record<string, string> = {
  '/policy/sources': '维护采集网站与信源信息',
  '/policy/crawler-monitoring': '按任务核查采集与异常',
  '/policy/crawler-monitoring-v2': '按网站查看采集健康状况',
  '/policy/interpretations': '整理政策内容与业务解读',
  '/policy/base-tags': '维护政策分类与基础标签',
  '/codebook/policy-types': '统一政策分类口径',
  '/codebook/scenarios': '管理行业与业务场景',
  '/codebook/area-codes': '维护省、市、区地域编码',
  '/system/users': '管理账号与角色分配',
  '/system/roles': '配置模块和操作权限',
  '/system/scheduler': '配置每日同步与查看执行记录',
  '/system/audit': '追溯操作与权限变更',
}

// 图标按子模块用途配置，不继承一级模块图标；同一入口在导航和查找中保持一致。
const entryIcons: Record<string, Component> = {
  '/policy/sources': Link,
  '/policy/crawler-monitoring': DataLine,
  '/policy/crawler-monitoring-v2': Monitor,
  '/policy/interpretations': Reading,
  '/policy/base-tags': PriceTag,
  '/codebook/policy-types': Collection,
  '/codebook/scenarios': Connection,
  '/codebook/area-codes': MapLocation,
  '/system/users': User,
  '/system/roles': Key,
  '/system/audit': Tickets,
  '/system/scheduler': Timer,
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
      result.get(key)!.entries.push({ title: item.title, path, description: descriptions[path] || '进入业务模块', icon: entryIcons[path] || Menu })
    }
    // 模块顺序以 iam 菜单 sort_order 为准（系统管理、政策、码表管理），前端不另行排序。
    return [...result.values()]
  })
  return { auth, groups }
}
