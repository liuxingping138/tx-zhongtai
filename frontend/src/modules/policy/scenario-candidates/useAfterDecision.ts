import { ElMessage } from 'element-plus'

import { errorMessage } from '@/api/errors'
import type { CandidateItem } from '@/api/scenarioCandidates'

const DONE: Record<string, string> = {
  已采纳: '已采纳进行业场景码表',
  已合并: '已合并到已有场景',
  已驳回: '已驳回',
  待审: '已改判回待审',
}

/**
 * 做完一个决定接着打开下一个。按「待审」看着时，决定完的这个出列表，下一个补到同一位置（review.advance）。
 * 决定已经生效、只是下一个没打开时，不能说成「没成功」，用户会以为要重来。
 */
export function useAfterDecision(review: { advance: () => Promise<boolean> }) {
  async function finished(row: CandidateItem): Promise<void> {
    const done = DONE[row.status] ?? '已处理'
    try {
      const moved = await review.advance()
      ElMessage.success(moved ? `${done}，打开了下一个` : done)
    } catch (error) {
      ElMessage.warning(`${done}。没能打开下一个：${errorMessage(error, '请稍后点「下一个」')}`)
    }
  }

  return { finished }
}
