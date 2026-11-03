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

/** 页面上做完会改变数字的事（新增场景审核里做了决定）时调一下，侧栏马上重取，不等换页。 */
const changed = ref(0)
export function refreshMenuBadges(): void {
  changed.value += 1
}

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

  // 新增场景审核里换页签、筛选（地址变了）强制刷新，别处按一分钟一次；在列表行上做完决定地址不变，靠 refreshMenuBadges
  watch(() => route.fullPath, () => { void refresh(route.path.startsWith('/policy/scenario-candidates')) }, { immediate: true })
  watch(changed, () => { void refresh(true) })
  return { counts, refresh }
}
