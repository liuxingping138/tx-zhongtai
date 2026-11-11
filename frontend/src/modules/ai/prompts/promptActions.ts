import { ElMessage, ElMessageBox } from 'element-plus'

import { deletePrompt, type AiModel, type PromptTemplate } from '@/api/ai'
import { errorMessage } from '@/api/errors'

/** 删模板：先确认（测试样本、码表文件一起删，已发起的任务不受影响），删掉了返回 true。 */
export async function removeTemplate(target: Pick<PromptTemplate, 'id' | 'title'>): Promise<boolean> {
  const ok = await ElMessageBox.confirm(`删除「${target.title}」和它的测试样本、码表文件。已发起的任务和结果不受影响。`, '删除模板？', {
    type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
  }).then(() => true, () => false)
  if (!ok) return false
  try {
    await deletePrompt(target.id)
    ElMessage.success('模板已删除')
    return true
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败，请重试'))
    return false
  }
}

interface TrialDraft {
  /** 编辑页上选的模板类型：还没保存的新模板，费用账单按它归到一级业务板块 */
  category: string
  content: string
  output_fields: string
  code_table: string
}

/**
 * 试发一条的请求：用页面上现在的草稿（没保存也算），包括码表——右栏写的「码表全文整份放进去」才名副其实。
 * shown 是对话里显示的「问」，带上模板名好分辨是哪个模板试的。
 */
export function trialRequest(
  draft: TrialDraft,
  context: { template: Pick<PromptTemplate, 'id' | 'title'> | null; model: AiModel; row: number; thinking: boolean },
): { body: Record<string, unknown>; shown: string; thinking: boolean } {
  const thinking = context.thinking && Boolean(context.model.supports_thinking)
  const body = {
    content: draft.content,
    model_id: context.model.id,
    thinking,
    prompt_id: context.template?.id ?? null,
    row: context.row,
    output_fields: draft.output_fields,
    code_table: draft.code_table,
    category: draft.category,
  }
  const shown = context.template ? `［${context.template.title}］\n${draft.content}` : draft.content
  return { body, shown, thinking }
}
