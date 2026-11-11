import { describe, expect, it, vi } from 'vitest'

vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), error: vi.fn() }, ElMessageBox: { confirm: vi.fn() } }))

import type { AiModel } from '@/api/ai'
import { trialRequest } from './promptActions'

const model = { id: 'm1', supports_thinking: false } as AiModel

describe('试发一条的请求', () => {
  it('按页面上现在的草稿发，码表也是没保存的那个', () => {
    const draft = { category: 'tender', content: '问：@【上传码表】', output_fields: '行业', code_table: 'policy_types' }
    const request = trialRequest(draft, { template: { id: 't1', title: '政策类型' }, model, row: 2, thinking: true })
    expect(request.body).toMatchObject({ prompt_id: 't1', row: 2, code_table: 'policy_types', thinking: false, category: 'tender' })
    expect(request.shown).toBe('［政策类型］\n问：@【上传码表】')
  })
})
