import { reactive } from 'vue'

import { errorMessage } from '@/api/errors'
import { getCandidate, getCandidateContext, type CandidateContext, type CandidateDetail } from '@/api/scenarioCandidates'

/** 一个场景展开后、做决定时要的依据：详情（各行业几行、AI 的理由、下级）和码表上下文（同一位置已有、像它的）。 */
export interface CandidateExtras {
  loading: boolean
  detail: CandidateDetail | null
  context: CandidateContext | null
  /** 详情没取到：展开里写出来，决定按钮要它，取不到就不让开确认框 */
  error: string
  /** 码表上下文没取到：照样能决定，只是看不到同级和像它的 */
  contextError: string
}

/**
 * 列表上按需取每行的依据，只在展开或点决定时取，取过的留着（同一行展开再收起、再点决定不重取）。
 * 做完决定、被并入别的场景后 drop 掉，下次重取。
 */
export function useCandidateExtras() {
  const entries = reactive(new Map<string, CandidateExtras>())
  const pending = new Map<string, Promise<CandidateExtras>>()

  async function fetch(id: string, entry: CandidateExtras): Promise<CandidateExtras> {
    const [detail, context] = await Promise.allSettled([getCandidate(id), getCandidateContext(id)])
    if (detail.status === 'fulfilled') entry.detail = detail.value
    else entry.error = errorMessage(detail.reason, '这个场景的详情没取到，请重试')
    if (context.status === 'fulfilled') entry.context = context.value
    else entry.contextError = errorMessage(context.reason, '码表暂时取不到，同级场景和像它的场景先看不了')
    entry.loading = false
    pending.delete(id)
    return entry
  }

  /** 取这一行的依据；正在取的等它，取过且成功的直接给，上次失败的重取。 */
  function ensure(id: string): Promise<CandidateExtras> {
    const known = entries.get(id)
    if (known?.detail) return Promise.resolve(known)
    const running = pending.get(id)
    if (running) return running
    entries.set(id, { loading: true, detail: null, context: null, error: '', contextError: '' })
    // 从 reactive Map 里取回代理对象再写，页面才看得到变化
    const job = fetch(id, entries.get(id) as CandidateExtras)
    pending.set(id, job)
    return job
  }

  function get(id: string): CandidateExtras | undefined {
    return entries.get(id)
  }

  function drop(...ids: string[]): void {
    for (const id of ids) {
      entries.delete(id)
      pending.delete(id)
    }
  }

  return { ensure, get, drop }
}
