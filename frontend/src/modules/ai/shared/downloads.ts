import { AI_BASE, type PromptFileKind, type RunFileKind, type RunVersion } from '@/api/ai'
import { downloadFile } from '@/api/download'

export function downloadPromptFile(id: string, kind: PromptFileKind, filename: string): Promise<void> {
  return downloadFile(`${AI_BASE}/prompts/${id}/files/${kind}`, filename)
}

export function downloadSampleFile(promptId: string, runId: string, kind: RunFileKind, filename: string): Promise<void> {
  return downloadFile(`${AI_BASE}/prompts/${promptId}/sample-run/${runId}/files/${kind}`, filename)
}

export function downloadBatchFile(id: string, kind: RunFileKind, filename: string): Promise<void> {
  return downloadFile(`${AI_BASE}/batch-runs/${id}/files/${kind}`, filename)
}

/** 按要跑的那一版（上线版本或草稿）引用的列生成、只有表头的空白数据表 */
export function downloadBatchInputTemplate(promptId: string, version: RunVersion, filename: string): Promise<void> {
  return downloadFile(`${AI_BASE}/batch-runs/input-template`, filename, { prompt_id: promptId, version })
}
