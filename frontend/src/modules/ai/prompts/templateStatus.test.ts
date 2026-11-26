import { describe, expect, it } from 'vitest'

import type { BatchRun, PromptTemplate, SampleSummary, TemplateReleaseInfo } from '@/api/ai'
import { releaseEntry, releaseState, sampleCurrent, sampleFromRun, sampleState } from './templateStatus'

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
    expect(releaseEntry(changed, true, 'header')).toEqual({ label: '发布 v3', emphasis: 'primary' })
    expect(releaseEntry(changed, true, 'list')).toEqual({ label: '发布 v3', emphasis: 'primary' })

    const online = template({ release: release() })
    expect(releaseEntry(online, true, 'header')).toEqual({ label: '线上版本', emphasis: 'subtle' })
    expect(releaseEntry(online, true, 'list')).toEqual({ label: '版本', emphasis: 'subtle' })
  })

  it('无上线权限人员：未上线不展示抽屉入口，有改动看改动，已上线看线上版本', () => {
    expect(releaseEntry(template(), false, 'header')).toBeNull()
    expect(releaseEntry(template(), false, 'list')).toBeNull()
    expect(releaseEntry(template({ release: release(['码表']) }), false, 'header')).toEqual({ label: '查看改动', emphasis: 'subtle' })
    expect(releaseEntry(template({ release: release(['码表']) }), false, 'list')).toEqual({ label: '改动', emphasis: 'subtle' })
    expect(releaseEntry(template({ release: release() }), false, 'list')).toEqual({ label: '版本', emphasis: 'subtle' })
  })
})
