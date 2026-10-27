import { AI_BASE, type PromptFileKind, type RunFileKind } from '@/api/ai'
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
