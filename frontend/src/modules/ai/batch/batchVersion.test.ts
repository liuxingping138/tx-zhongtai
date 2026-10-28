import { describe, expect, it } from 'vitest'

import type { AiModel, PromptTemplate, SampleSummary, TemplateReleaseInfo } from '@/api/ai'
import { defaultVersion, inputColumns, runSpec, versionOptions } from './batchVersion'

const models = [
  { id: 'flash', name: 'V4.1-Flash', available: true },
  { id: 'nokey', name: '千帆', available: false },
] as AiModel[]

function release(overrides: Partial<TemplateReleaseInfo> = {}): TemplateReleaseInfo {
  return {
    id: 'r', release_no: 1, released_at: '2026-10-22 16:23:00', released_by_name: '系统管理员', unreleased_changes: [],
    title: '行业场景', category_name: '政策', content: '@【政策标题】', fields: ['一级行业'], variables: ['政策标题'],
    model_id: 'flash', model_name: 'V4.1-Flash', code: '', ...overrides,
  }
}

function template(overrides: Partial<PromptTemplate> = {}): PromptTemplate {
  return {
    id: 't', title: '行业场景', category: 'policy', category_name: '政策', editable: true,
    content: '标题：@【政策标题】 正文：@【政策正文】 码表：@【上传码表】 再看 @【政策标题】', output_fields: '一级行业|一级场景',
    fields: ['一级行业', '一级场景'], model_id: 'flash', model_name: 'V4.1-Flash', excel_name: '', excel_rows: 0, excel_headers: [],
    code_name: '', code_table: 'scenario_l1', code_table_name: '一级行业 + 一级场景', release: null, sample: null, version: 1,
    created_at: '', created_by_name: '', updated_at: '2026-10-28 16:22:00', updated_by_name: '', ...overrides,
  }
}

const sample = (overrides: Partial<SampleSummary> = {}): SampleSummary => ({
  id: 's', status: 'done', total_count: 10, done_count: 10, failed_count: 2, format_failed_count: 1, cost: 0.07,
  created_at: '', created_by_name: '', current: true, ...overrides,
})

describe('新建批量任务跑哪一版', () => {
  it('草稿要的列：去重、按出现顺序，码表不算列', () => {
    expect(inputColumns(template().content)).toEqual(['政策标题', '政策正文'])
  })

  it('有上线版本默认跑线上，没上线只能跑草稿', () => {
    expect(defaultVersion(template({ release: release() }))).toBe('release')
    expect(defaultVersion(template())).toBe('draft')
    expect(defaultVersion(undefined)).toBe('draft')
  })

  it('两个选项写清是哪一版、草稿改了什么、试跑有没有问题', () => {
    const [online, draft] = versionOptions(template({ release: release({ unreleased_changes: ['提示词内容'] }), sample: sample() }))
    expect(online).toMatchObject({ title: '线上第 1 版', disabled: false })
    expect(online?.detail).toBe('10-22 16:23 系统管理员上线，定时任务也用这一版')
    expect(draft?.detail).toBe('10-28 16:22 保存，比第 1 版改了提示词内容')
    expect(draft?.warning).toBe('样本试跑 10 条里 2 条有问题')
    const [none, fresh] = versionOptions(template())
    expect(none).toMatchObject({ title: '线上版本', disabled: true })
    expect(fresh?.warning).toContain('还没做过样本试跑')
    expect(versionOptions(template({ sample: sample({ current: false }) }))[1]?.warning).toContain('草稿又改过')
    expect(versionOptions(template({ sample: sample({ failed_count: 0 }) }))[1]?.warning).toBe('')
  })

  it('跑线上版本按上线时冻结的内容；草稿按模板现在保存的', () => {
    const online = runSpec(template({ release: release() }), 'release', models)
    expect(online).toMatchObject({ label: '第 1 版', columns: ['政策标题'], fields: ['一级行业'], problem: '' })
    const draft = runSpec(template(), 'draft', models)
    expect(draft).toMatchObject({ label: '当前草稿', columns: ['政策标题', '政策正文'], code: '一级行业 + 一级场景', problem: '' })
    expect(runSpec(undefined, 'draft', models)).toBeNull()
  })

  it('跑不了的原因：没上线、草稿是空的、没选模型、模型停用或没配密钥', () => {
    expect(runSpec(template(), 'release', models)?.problem).toContain('选「当前草稿」跑')
    expect(runSpec(template({ content: ' ' }), 'draft', models)?.problem).toContain('提示词还是空的')
    expect(runSpec(template({ model_id: '' }), 'draft', models)?.problem).toContain('还没选模型')
    expect(runSpec(template({ model_id: 'gone', model_name: '旧模型' }), 'draft', models)?.problem).toBe('「旧模型」已停用，在模板里换一个模型并保存')
    expect(runSpec(template({ model_id: 'nokey' }), 'draft', models)?.problem).toContain('接口密钥还没配置')
    expect(runSpec(template({ release: release({ model_id: 'gone', model_name: '旧模型' }) }), 'release', models)?.problem).toContain('重新上线')
  })
})
