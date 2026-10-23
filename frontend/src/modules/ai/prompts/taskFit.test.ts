import { describe, expect, it } from 'vitest'

import type { ContractTask } from '@/api/aiTagging'
import { checkTemplate, fitLevel, fitResults, fitSummary, guessTask } from './taskFit'

const BASE = ['源ID', '政策标题', '政策正文', '省份', '地市', '出台时间', '发文部门', '政策层级']
const TYPE: ContractTask = { code: 'type', name: '政策类型判断', columns: BASE, required_fields: ['政策类型名称'] }
const INTERPRET: ContractTask = { code: 'interpret', name: '政策解读', columns: BASE, required_fields: ['一级行业', '一级场景'] }
const CHANCE: ContractTask = { code: 'opportunity', name: '政策市场机会', columns: [...BASE, '行业场景'], required_fields: ['市场机会'] }

describe('模板放进打标任务前的检查', () => {
  it('列和输出字段都对得上就没有问题', () => {
    const check = checkTemplate(TYPE, ['政策标题', '政策正文', '上传码表'], ['政策类型名称'], true)
    expect(check).toEqual({ errors: [], warnings: [] })
    expect(fitLevel({ check, skip: false })).toBe('ok')
  })

  it('用了任务不提供的列、缺输出字段是必须改的', () => {
    const check = checkTemplate(INTERPRET, ['企业名称', '政策正文'], ['政策概览'], true)
    expect(check.errors[0]).toMatch(/^用了这个任务不提供的列：@【企业名称】/)
    expect(check.errors[1]).toBe('输出字段缺少：一级行业、一级场景，结果写不回表')
    expect(fitLevel({ check, skip: false })).toBe('error')
  })

  it('能跑但可能不理想的给提醒：没用正文、市场机会没用行业场景、码表不是系统的', () => {
    const check = checkTemplate(CHANCE, ['政策标题', '上传码表'], ['市场机会'], false)
    expect(check.errors).toEqual([])
    expect(check.warnings).toHaveLength(3)
    expect(fitLevel({ check, skip: false })).toBe('warn')
  })

  it('一个必需字段都没有的任务算不适用，不标红；上线确认只提用得上和想用但有问题的', () => {
    const results = fitResults([TYPE, INTERPRET, CHANCE], ['政策标题', '政策正文'], ['政策类型名称', '一级行业'], true)
    expect(results.map(item => fitLevel(item))).toEqual(['ok', 'error', 'skip'])
    expect(fitSummary(results)).toBe('可用于政策类型判断；不能用于政策解读')
    expect(fitSummary(fitResults([TYPE, CHANCE], ['政策正文'], ['政策类型名称'], true))).toBe('可用于政策类型判断')
  })

  it('按输出字段猜模板给哪个任务用', () => {
    expect(guessTask([TYPE, INTERPRET, CHANCE], ['政策类型名称'])).toBe('type')
    expect(guessTask([TYPE, INTERPRET, CHANCE], ['政策概览', '一级行业', '一级场景'])).toBe('interpret')
    expect(guessTask([TYPE, INTERPRET, CHANCE], ['行业', '场景', '市场机会'])).toBe('opportunity')
    expect(guessTask([TYPE, INTERPRET, CHANCE], [])).toBe('type')
  })
})
