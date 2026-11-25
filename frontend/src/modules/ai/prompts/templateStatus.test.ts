import { describe, expect, it } from 'vitest'

import type { BatchRun, PromptTemplate, SampleSummary, TemplateReleaseInfo } from '@/api/ai'
import { flowSteps, releaseEntry, releaseState, sampleCurrent, sampleFromRun, sampleState, stepActions } from './templateStatus'

const release = (changes: string[] = []): TemplateReleaseInfo => ({
  id: 'r', release_no: 2, released_at: '2026-10-22 16:24', released_by_name: '管理员', unreleased_changes: changes,
  title: '政策解读', category_name: '政策', content: '', fields: [], variables: [], model_id: 'm', model_name: '模型', code: '',
})
const sample = (overrides: Partial<SampleSummary> = {}): SampleSummary => ({
  id: 's', status: 'done', total_count: 10, done_count: 10, failed_count: 0, format_failed_count: 0, cost: 0, thinking: false,
  created_at: '2026-10-26 15:20', created_by_name: '张三', current: true, ...overrides,
})
const template = (overrides: Partial<PromptTemplate> = {}): PromptTemplate => ({
  id: 't', title: '政策解读', category: 'policy', category_name: '政策', editable: true, content: '内容', output_fields: '行业',
  fields: ['行业'], model_id: 'm', model_name: '模型', excel_name: '样本.xlsx', excel_rows: 10, excel_headers: [], code_name: '',
  code_table: '', code_table_name: '', release: null, sample: null, version: 1, created_at: '', created_by_name: '',
  updated_at: '2026-10-26 15:00', updated_by_name: '张三', ...overrides,
})

describe('上线状态', () => {
  it('分未上线、有改动未上线、已上线，并输出紧凑状态文案', () => {
    expect(releaseState(template())).toMatchObject({ kind: 'offline', compact: '未上线' })
    expect(releaseState(template({ release: release(['提示词内容', '码表']) }))).toMatchObject({
      kind: 'changed', text: '第 2 版在线，草稿改了提示词内容、码表', compact: '第 2 版 · 有改动',
    })
    expect(releaseState(template({ release: release() }))).toMatchObject({
      kind: 'online', text: '第 2 版已上线', compact: '第 2 版已上线',
    })
  })
})

describe('样本试跑状态', () => {
  it('没有样本、没试跑、试跑中、草稿改过、有失败、没跑完、全部成功', () => {
    expect(sampleState(template({ excel_name: '' }))).toMatchObject({ kind: 'nosample', compact: '无样本' })
    expect(sampleState(template())).toMatchObject({ kind: 'none', compact: '未试跑' })
    expect(sampleState(template({ sample: sample({ status: 'running', done_count: 3 }) })).text).toBe('试跑中 3/10')
    expect(sampleState(template({ sample: sample({ current: false }) }))).toMatchObject({ kind: 'stale', compact: '待重跑 · 草稿已改' })
    expect(sampleState(template({ sample: sample({ failed_count: 2, format_failed_count: 1 }) }))).toMatchObject({
      text: '10 条里 2 条失败（格式不对 1）', compact: '10 条 · 2 异常',
    })
    expect(sampleState(template({ sample: sample({ status: 'cancelled', done_count: 4 }) }))).toMatchObject({
      kind: 'stopped', compact: '已中断 4/10',
    })
    expect(sampleState(template({ sample: sample() }))).toMatchObject({
      text: '10 条全部解析成功', compact: '10/10 解析通过',
    })
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

  it('能上线但改不了这类模板的管理员，第一次上线也有入口', () => {
    const releaser = { canEdit: false, canRelease: true, sampleOpen: false }
    expect(actionsOf(template({ sample: sample() }), releaser)).toEqual({ release: '上线' })
    expect(actionsOf(template({ sample: sample() }), { ...releaser, canRelease: false })).toEqual({})
  })

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

describe('样本试跑是不是现在的草稿', () => {
  const run = { draft_saved_at: '2026-10-29 10:00:00', prompt_content: '问', output_fields: '行业', model_id: 'm1' }
  const template = { content: '问', output_fields: '行业', model_id: 'm1', updated_at: '2026-10-29 10:00:00' }

  it('按试跑时记下的草稿保存时间比：换了码表、测试样本也算改过', () => {
    expect(sampleCurrent(run, template)).toBe(true)
    // 提示词、字段、模型都没变，只是换了码表（保存时间变了）：要重新试跑，预计费用才不会低估。
    expect(sampleCurrent(run, { ...template, updated_at: '2026-10-29 10:05:00' })).toBe(false)
  })

  it('早期的试跑没记保存时间，退回按内容比', () => {
    const old = { ...run, draft_saved_at: '' }
    expect(sampleCurrent(old, { ...template, updated_at: 'x' })).toBe(true)
    expect(sampleCurrent(old, { ...template, content: '改过' })).toBe(false)
  })
})

describe('双入口上线审核按钮（列表页与编辑页共用）', () => {
  it('管理员：未上线、有改动、已上线在顶栏与列表页均始终展示明确上线入口，不受未试跑遮蔽', () => {
    expect(releaseEntry(null, true, 'header')).toBeNull()
    expect(releaseEntry(template(), true, 'header')).toEqual({ label: '发布上线', emphasis: 'plain' })
    expect(releaseEntry(template(), true, 'list')).toEqual({ label: '上线', emphasis: 'plain' })

    const changed = template({ release: release(['提示词内容']), sample: null })
    expect(releaseEntry(changed, true, 'header')).toEqual({ label: '审核上线 · 第 3 版', emphasis: 'primary' })
    expect(releaseEntry(changed, true, 'list')).toEqual({ label: '审核上线', emphasis: 'primary' })

    const online = template({ release: release() })
    expect(releaseEntry(online, true, 'header')).toEqual({ label: '线上版本', emphasis: 'subtle' })
    expect(releaseEntry(online, true, 'list')).toEqual({ label: '线上版', emphasis: 'subtle' })
  })

  it('无上线权限人员：未上线不展示抽屉入口，有改动看改动，已上线看线上版本', () => {
    expect(releaseEntry(template(), false, 'header')).toBeNull()
    expect(releaseEntry(template(), false, 'list')).toBeNull()
    expect(releaseEntry(template({ release: release(['码表']) }), false, 'header')).toEqual({ label: '看改动', emphasis: 'subtle' })
    expect(releaseEntry(template({ release: release() }), false, 'list')).toEqual({ label: '线上版', emphasis: 'subtle' })
  })
})
