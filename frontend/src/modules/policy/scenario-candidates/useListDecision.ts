import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import type { CandidateContext, CandidateDetail, CandidateItem } from '@/api/scenarioCandidates'
import { defaultMergeTarget, doneText, type DecisionMode } from './candidates'
import type { useCandidateExtras } from './useCandidateExtras'

export interface DecisionTarget {
  candidate: CandidateDetail
  context: CandidateContext | null
  target: string[] | null
}

/**
 * 列表行上点了决定：先取这一行的依据（确认框要写清会改什么、合并要列出像它的），再开确认框；
 * 做完提示一句、丢掉这一行的缓存、重新载入列表（这一行出待审，下一行顶上来）。
 * target 不传表示照这一行写着的预选（defaultMergeTarget），传 null 表示自己在码表里选。
 */
export function useListDecision(extras: ReturnType<typeof useCandidateExtras>, after: () => Promise<void>) {
  const busy = ref<{ id: string; mode: DecisionMode } | null>(null)
  const mode = ref<DecisionMode | null>(null)
  const current = ref<DecisionTarget | null>(null)

  async function open(row: CandidateItem, next: DecisionMode, target?: string[] | null): Promise<void> {
    if (busy.value) return
    busy.value = { id: row.id, mode: next }
    try {
      const found = await extras.ensure(row.id)
      if (!found.detail) {
        ElMessage.error(found.error || '这个场景的详情没取到，请重试')
        return
      }
      const similar = found.context?.similar ?? []
      const preset = next !== 'merge' ? null : target === undefined ? defaultMergeTarget(row, similar) : target
      current.value = { candidate: found.detail, context: found.context, target: preset }
      mode.value = next
    } finally {
      busy.value = null
    }
  }

  function close(): void {
    mode.value = null
  }

  async function done(row: CandidateItem): Promise<void> {
    mode.value = null
    ElMessage.success(doneText(row))
    extras.drop(row.id)
    await after()
  }

  return { busy, mode, current, open, close, done }
}
