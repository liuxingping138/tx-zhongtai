/** 批量任务的停止、重跑失败、跑全部、删除、下载：列表的操作列和详情抽屉共用，确认文案只写一份。 */
import { ElMessage, ElMessageBox } from 'element-plus'

import { deleteBatchRun, retryBatchRun, runAllBatchRun, stopBatchRun, type BatchRun, type RunFileKind } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { formatYuan } from '../shared/aiText'
import { downloadBatchFile } from '../shared/downloads'

export const RUN_FILES: { kind: RunFileKind; label: string }[] = [
  { kind: 'result', label: '结果 Excel' },
  { kind: 'raw', label: '原始返回 CSV' },
  { kind: 'failed', label: '失败清单' },
  { kind: 'log', label: '运行日志' },
]
const FILE_NAMES: Record<RunFileKind, string> = { result: '结果.xlsx', raw: '原始返回.csv', failed: '失败清单.csv', log: '运行日志.log' }

const confirm = (message: string, title: string, action: string, cancel = '取消') =>
  ElMessageBox.confirm(message, title, { type: 'warning', confirmButtonText: action, cancelButtonText: cancel }).then(() => true, () => false)

export async function downloadRunFile(run: BatchRun, kind: RunFileKind): Promise<void> {
  try {
    await downloadBatchFile(run.id, kind, `${run.prompt_title}-${FILE_NAMES[kind]}`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败，请重试'))
  }
}

/** 返回 true 表示任务变了，调用方刷新。 */
export async function stopRun(run: BatchRun): Promise<boolean> {
  if (!await confirm('已完成的行会保留并生成结果，进行中的请求返回后停止。', '停止这个任务？', '停止', '继续运行')) return false
  try {
    await stopBatchRun(run.id)
    return true
  } catch (error) {
    ElMessage.error(errorMessage(error, '停止失败，请重试'))
    return false
  }
}

export async function retryRun(run: BatchRun): Promise<boolean> {
  const parts = [
    run.failed_count ? `失败 ${run.failed_count} 条` : '',
    run.total_count > run.done_count ? `没跑到 ${run.total_count - run.done_count} 条` : '',
  ].filter(Boolean).join('、')
  const message = `将用「${run.model_name}」重新提问 ${run.pending_count} 条（${parts}），会产生模型费用。已成功的行保留，结果合并回这条记录。`
  if (!await confirm(message, '重跑失败的行？', '开始重跑')) return false
  try {
    await retryBatchRun(run.id)
    ElMessage.success(`已加入队列，重跑 ${run.pending_count} 条`)
    return true
  } catch (error) {
    ElMessage.error(errorMessage(error, '重跑失败，请重试'))
    return false
  }
}

/** 这次只跑了前几行、看着满意：同一份数据、同一版提示词跑全部，不用重新选模板、传 Excel。 */
export async function runAllRun(run: BatchRun): Promise<boolean> {
  const spent = run.inference_cost + run.search_cost
  const perRow = run.done_count ? `，按这次每条约 ${formatYuan(spent / run.done_count)} 估算` : ''
  const message = `用「${run.input_name || '这份数据'}」的全部行、这次冻结的提示词和「${run.model_name}」新建一个任务。`
    + `前 ${run.row_limit} 行里答好的沿用、不再花钱，其余每行都会产生模型费用${perRow}。`
  if (!await confirm(message, '用同一份数据跑全部？', '开始跑全部')) return false
  try {
    const created = await runAllBatchRun(run.id)
    ElMessage.success(created.reused_rows ? `已加入队列，共 ${created.total_count} 条，沿用 ${created.reused_rows} 条` : `已加入队列，共 ${created.total_count} 条`)
    return true
  } catch (error) {
    ElMessage.error(errorMessage(error, '没能开始，请重试'))
    return false
  }
}

export async function deleteRun(run: BatchRun): Promise<boolean> {
  if (!await confirm('记录和结果文件都会删除，不能恢复；花掉的费用仍算在费用账单里。', '删除这条记录？', '删除')) return false
  try {
    await deleteBatchRun(run.id)
    return true
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败，请重试'))
    return false
  }
}
