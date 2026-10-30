import { ElMessage } from 'element-plus'
import { reactive } from 'vue'

import { AI_BASE, type PromptFileKind, type RunFileKind, type RunVersion } from '@/api/ai'
import { downloadFile } from '@/api/download'

/**
 * 正在准备的下载。原始返回、结果 Excel 可能几百 MB，浏览器要整份收完才弹出保存，
 * 几十秒没反应用户会再点：准备期间给一条一直显示的提示，同一个文件再点只提醒、不重复下载。
 */
const pending = reactive(new Set<string>())

async function download(path: string, filename: string, params?: Record<string, string>): Promise<void> {
  const key = params ? `${path}?${new URLSearchParams(params).toString()}` : path
  if (pending.has(key)) {
    ElMessage.info(`「${filename}」正在准备，下载开始前不用再点`)
    return
  }
  pending.add(key)
  const notice = ElMessage({ message: `正在准备「${filename}」，文件大时要等几十秒…`, type: 'info', duration: 0 })
  try {
    await downloadFile(path, filename, params)
  } finally {
    notice.close()
    pending.delete(key)
  }
}

export function downloadPromptFile(id: string, kind: PromptFileKind, filename: string): Promise<void> {
  return download(`${AI_BASE}/prompts/${id}/files/${kind}`, filename)
}

export function downloadSampleFile(promptId: string, runId: string, kind: RunFileKind, filename: string): Promise<void> {
  return download(`${AI_BASE}/prompts/${promptId}/sample-run/${runId}/files/${kind}`, filename)
}

export function downloadBatchFile(id: string, kind: RunFileKind, filename: string): Promise<void> {
  return download(`${AI_BASE}/batch-runs/${id}/files/${kind}`, filename)
}

/** 按要跑的那一版（上线版本或草稿）引用的列生成、只有表头的空白数据表 */
export function downloadBatchInputTemplate(promptId: string, version: RunVersion, filename: string): Promise<void> {
  return download(`${AI_BASE}/batch-runs/input-template`, filename, { prompt_id: promptId, version })
}
