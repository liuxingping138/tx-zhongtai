import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { candidatePendingCount } from '@/api/scenarioCandidates'
import { useAuthStore } from '@/stores/auth'

/** 侧栏上带数字的入口：路径 -> 取数、看得到它要哪个资源。现在只有「新增场景审核」的待审数。 */
const SOURCES: Record<string, { resource: string; fetch: () => Promise<number> }> = {
  '/policy/scenario-candidates': {
    resource: 'policy.scenario_candidates',
    fetch: async () => (await candidatePendingCount()).pending,
  },
}
/** 换页时顺带刷新，但同一个数一分钟内只取一次：每次点菜单都去数一遍没必要。 */
export const REFRESH_MS = 60_000

export function useMenuBadges() {
  const auth = useAuthStore()
  const route = useRoute()
  const counts = ref<Record<string, number>>({})
  const fetchedAt: Record<string, number> = {}

  async function refresh(force = false): Promise<void> {
    const now = Date.now()
    await Promise.all(Object.entries(SOURCES).map(async ([path, source]) => {
      if (!auth.canRead(source.resource)) return
      if (!force && now - (fetchedAt[path] ?? 0) < REFRESH_MS) return
      fetchedAt[path] = now
      try {
        counts.value = { ...counts.value, [path]: await source.fetch() }
      } catch {
        /* 数取不到不影响菜单本身 */
      }
    }))
  }

  // 在新增场景审核里做完决定会换到下一个（地址变了）：这个页面里换页就强制刷新，别处按一分钟一次
  watch(() => route.fullPath, () => { void refresh(route.path.startsWith('/policy/scenario-candidates')) }, { immediate: true })
  return { counts, refresh }
}
