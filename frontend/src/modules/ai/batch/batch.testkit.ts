/** 批量任务单测共用的替身：模板、上线版本、一个能手动放行的 Promise。 */
import type { AiModel, PromptTemplate, TemplateReleaseInfo } from '@/api/ai'
import type { BatchRowsSummary } from '@/api/aiSamples'

export const MODELS = [{ id: 'flash', name: 'V4.1-Flash', available: true }] as AiModel[]

export function release(overrides: Partial<TemplateReleaseInfo> = {}): TemplateReleaseInfo {
  return {
    id: 'r', release_no: 1, released_at: '2026-10-22 16:23:00', released_by_name: '系统管理员', unreleased_changes: [],
    title: '市场机会', category_name: '政策', content: '@【一级行业】@【一级场景】@【政策正文】', fields: ['市场机会'],
    variables: ['一级行业', '一级场景', '政策正文'], model_id: 'flash', model_name: 'V4.1-Flash', code: '', ...overrides,
  }
}

export function template(overrides: Partial<PromptTemplate> = {}): PromptTemplate {
  return {
    id: 't1', title: '市场机会', category: 'policy', category_name: '政策', editable: true,
    content: '@【一级行业】@【一级场景】@【政策正文】', output_fields: '市场机会', fields: ['市场机会'], model_id: 'flash',
    model_name: 'V4.1-Flash', excel_name: '', excel_rows: 0, excel_headers: [], code_name: '', code_table: '', code_table_name: '',
    release: release(), sample: null, version: 1, created_at: '', created_by_name: '', updated_at: '2026-10-28 16:22:00',
    updated_by_name: '', ...overrides,
  }
}

export function summary(overrides: Partial<BatchRowsSummary> = {}): BatchRowsSummary {
  return { name: '数据库样本.xlsx', rows: 2, headers: ['一级行业'], version: 'release', release_no: 1, model_name: 'V4.1-Flash', ...overrides }
}

/** 测试里手动 resolve / reject 的 Promise，用来摆出「慢的旧请求晚到」的先后。 */
export function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}
