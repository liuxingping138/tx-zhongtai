import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'

import { errorMessage } from '@/api/errors'
import { setInterpretationsDataStatus, type InterpretationItem } from '@/api/policy'

interface ReviewState {
  ready: Ref<boolean>
  record: Ref<InterpretationItem | null>
  advance: () => Promise<boolean>
}

/**
 * 核对页「核对无误，标为人工验证」：标掉这条，接着打开下一条。按「待验证」筛着时，
 * 标完的这条会出列表，下一条补到同一位置（review.advance）。
 * 改状态和打开下一条分开报：状态已经改好、只是下一条没打开时，不能说成「没能改成人工验证」，用户会以为要重来。
 */
export function useVerify(review: ReviewState) {
  const verifying = ref(false)

  async function verify(row: InterpretationItem): Promise<void> {
    // 翻条后新记录还没回来时，按钮旁显示的还是上一条：不能把上一条标掉。
    if (!review.ready.value || row.id !== review.record.value?.id || verifying.value) return
    verifying.value = true
    try {
      try {
        await setInterpretationsDataStatus([row.id], '人工验证')
      } catch (error) {
        ElMessage.error(errorMessage(error, '没能改成人工验证，请重试'))
        return
      }
      // 新增场景标完还要同步才进码表，顺带提醒入口在哪。
      const sync = row.is_new_scenario === '是' ? '。新增场景回列表点「同步新增场景」写进码表' : ''
      try {
        const moved = await review.advance()
        ElMessage.success(`${moved ? '已标为人工验证，打开了下一条' : '已标为人工验证'}${sync}`)
      } catch (error) {
        ElMessage.warning(`已标为人工验证${sync}。没能打开下一条：${errorMessage(error, '请稍后点「下一条」')}`)
      }
    } finally {
      verifying.value = false
    }
  }

  return { verifying, verify }
}
