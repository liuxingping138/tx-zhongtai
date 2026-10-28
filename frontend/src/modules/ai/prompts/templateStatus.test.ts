import { describe, expect, it } from 'vitest'

import type { BatchRun, PromptTemplate, SampleSummary, TemplateReleaseInfo } from '@/api/ai'
import { flowSteps, releaseState, sampleFromRun, sampleState, stepActions } from './templateStatus'

const release = (changes: string[] = []): TemplateReleaseInfo => ({
  id: 'r', release_no: 2, released_at: '2026-10-22 16:24', released_by_name: '管理员', unreleased_changes: changes,
  title: '政策解读', category_name: '政策', content: '', fields: [], variables: [], model_id: 'm', model_name: '模型', code: '',
})
const sample = (overrides: Partial<SampleSummary> = {}): SampleSummary => ({
  id: 's', status: 'done', total_count: 10, done_count: 10, failed_count: 0, format_failed_count: 0,
  created_at: '2026-10-26 15:20', created_by_name: '张三', current: true, ...overrides,
})
const template = (overrides: Partial<PromptTemplate> = {}): PromptTemplate => ({
  id: 't', title: '政策解读', category: 'policy', category_name: '政策', editable: true, content: '内容', output_fields: '行业',
  fields: ['行业'], model_id: 'm', model_name: '模型', excel_name: '样本.xlsx', excel_rows: 10, excel_headers: [], code_name: '',
  code_table: '', code_table_name: '', release: null, sample: null, version: 1, created_at: '', created_by_name: '',
  updated_at: '2026-10-26 15:00', updated_by_name: '张三', ...overrides,
})

describe('上线状态', () => {
  it('分未上线、有改动未上线、已上线', () => {
    expect(releaseState(template()).kind).toBe('offline')
    expect(releaseState(template({ release: release(['提示词内容', '码表']) }))).toMatchObject({
      kind: 'changed', text: '第 2 版在线，草稿改了提示词内容、码表',
    })
    expect(releaseState(template({ release: release() }))).toMatchObject({ kind: 'online', text: '第 2 版已上线' })
  })
})

describe('样本试跑状态', () => {
  it('没有样本、没试跑、试跑中、草稿改过、有失败、没跑完、全部成功', () => {
    expect(sampleState(template({ excel_name: '' })).kind).toBe('nosample')
    expect(sampleState(template()).kind).toBe('none')
    expect(sampleState(template({ sample: sample({ status: 'running', done_count: 3 }) })).text).toBe('试跑中 3/10')
    expect(sampleState(template({ sample: sample({ current: false }) })).kind).toBe('stale')
    expect(sampleState(template({ sample: sample({ failed_count: 2, format_failed_count: 1 }) })).text).toBe('10 条里 2 条失败（格式不对 1）')
    expect(sampleState(template({ sample: sample({ status: 'cancelled', done_count: 4 }) })).kind).toBe('stopped')
    expect(sampleState(template({ sample: sample() })).text).toBe('10 条全部解析成功')
  })
})

describe('流程条', () => {
  const tones = (steps: ReturnType<typeof flowSteps>) => steps.map(step => step.tone)

  it('新模板：第一步是下一步，后两步还轮不到', () => {
    expect(tones(flowSteps(null, true, false))).toEqual(['current', 'todo', 'todo'])
  })

  it('先传了样本、提示词还空着：第一步还没完成', () => {
    const steps = flowSteps(template({ content: '' }), false, true)
    expect(tones(steps)).toEqual(['current', 'todo', 'todo'])
    expect(steps[0]?.text).toBe('还没写提示词')
  })

  it('有未保存的修改时先保存', () => {
    expect(tones(flowSteps(template({ sample: sample() }), true, true))).toEqual(['current', 'done', 'todo'])
  })

  it('试跑通过、没上线：下一步是上线；业务人员看到的是请管理员上线', () => {
    const steps = flowSteps(template({ sample: sample() }), false, false)
    expect(tones(steps)).toEqual(['done', 'done', 'current'])
    expect(steps[2]?.text).toBe('未上线，确认无误后请管理员上线')
  })

  it('试跑有失败算完成但要留意；草稿改过要重新试跑', () => {
    expect(tones(flowSteps(template({ sample: sample({ failed_count: 1 }) }), false, true))).toEqual(['done', 'warn', 'current'])
    expect(tones(flowSteps(template({ sample: sample({ current: false }), release: release(['提示词内容']) }), false, true)))
      .toEqual(['done', 'current', 'todo'])
  })

  it('已上线且草稿没再改、也没试跑过：照实写没试跑，但不当成下一步去催', () => {
    const steps = flowSteps(template({ release: release() }), false, true)
    expect(tones(steps)).toEqual(['done', 'todo', 'done'])
    expect(steps[1]?.text).toBe(sampleState(template()).text)
  })

  it('已上线且草稿没再改：三步都完成', () => {
    expect(tones(flowSteps(template({ sample: sample(), release: release() }), false, true))).toEqual(['done', 'done', 'done'])
  })
})

describe('流程条上的按钮', () => {
  const admin = { canEdit: true, canRelease: true, sampleOpen: false }
  const actionsOf = (item: PromptTemplate, context = admin) => stepActions(item, flowSteps(item, false, context.canRelease), context)

  it('试跑是下一步时给「去试跑」，右栏已经在试跑上就不给', () => {
    expect(actionsOf(template())).toEqual({ test: '去试跑' })
    expect(actionsOf(template(), { ...admin, sampleOpen: true })).toEqual({})
  })

  it('管理员：该上线时给版本号；上线后改了草稿但还要重新试跑时给「看改动」；没有改动给「上线管理」', () => {
    expect(actionsOf(template({ sample: sample() }))).toEqual({ release: '上线' })
    expect(actionsOf(template({ sample: sample(), release: release(['提示词内容']) }))).toEqual({ release: '上线第 3 版' })
    expect(actionsOf(template({ sample: sample({ current: false }), release: release(['提示词内容']) })))
      .toEqual({ test: '去试跑', release: '看改动' })
    expect(actionsOf(template({ sample: sample(), release: release() }))).toEqual({ release: '上线管理' })
  })

  it('业务人员和只读的人：有改动都能「看改动」，否则只能查看上线内容', () => {
    const staff = { canEdit: true, canRelease: false, sampleOpen: true }
    expect(actionsOf(template({ sample: sample(), release: release(['码表']) }), staff)).toEqual({ release: '看改动' })
    expect(actionsOf(template({ sample: sample() }), staff)).toEqual({ release: '查看上线内容' })
    const reader = { canEdit: false, canRelease: false, sampleOpen: false }
    expect(actionsOf(template({ release: release(['码表']) }), reader)).toEqual({ release: '看改动' })
    expect(actionsOf(template({ release: release() }), reader)).toEqual({ release: '查看上线内容' })
    expect(actionsOf(template(), reader)).toEqual({})
  })
})

describe('试跑任务换成模板上的摘要', () => {
  it('跑的是现在的草稿才算 current；模板没定模型时不比模型', () => {
    const run = { id: 'r', status: 'done', total_count: 2, done_count: 2, failed_count: 0, format_failed_count: 0,
      created_at: 't', created_by_name: '张三', prompt_content: '内容', output_fields: '行业', model_id: 'm' } as BatchRun
    expect(sampleFromRun(run, template()).current).toBe(true)
    expect(sampleFromRun(run, template({ content: '改过' })).current).toBe(false)
    expect(sampleFromRun(run, template({ model_id: 'other' })).current).toBe(false)
    expect(sampleFromRun(run, template({ model_id: '' })).current).toBe(true)
  })
})
