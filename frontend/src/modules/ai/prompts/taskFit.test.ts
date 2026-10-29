import { describe, expect, it } from 'vitest'

import type { ContractTask } from '@/api/aiTagging'
import { checkTemplate, fitLevel, fitResults, fitSummary, guessTask } from './taskFit'

const BASE = ['源ID', '政策标题', '政策正文', '省份', '地市', '出台时间', '发文部门', '政策层级']
const TASK = { optional_fields: [], prompt_id: '' }
const TYPE: ContractTask = { ...TASK, code: 'type', name: '政策类型判断', columns: BASE, required_fields: ['政策类型名称'] }
const INTERPRET: ContractTask = {
  ...TASK,
  code: 'interpret',
  name: '政策解读',
  columns: BASE,
  required_fields: ['一级行业', '一级场景'],
  optional_fields: [['政策要文', '政策概览'], ['二级行业'], ['三级行业'], ['二级场景'], ['三级场景'], ['备注']],
}
const CHANCE: ContractTask = { ...TASK, code: 'opportunity', name: '政策市场机会', columns: [...BASE, '行业场景'], required_fields: ['市场机会'] }

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

  it('能跑但可能不理想的给提醒：没用正文、市场机会没输出和没用行业场景、码表不是系统的', () => {
    const check = checkTemplate(CHANCE, ['政策标题', '上传码表'], ['市场机会'], false)
    expect(check.errors).toEqual([])
    expect(check.warnings).toHaveLength(4)
    expect(fitLevel({ check, skip: false })).toBe('warn')
    // 输出写成「一级行业 / 一级场景」也认，和政策服务的规则一致。
    expect(checkTemplate(CHANCE, ['政策正文', '行业场景'], ['一级行业', '一级场景', '市场机会'], true).warnings).toEqual([])
  })

  it('一个必需字段都没有的任务算不适用，不标红；上线确认只提用得上和想用但有问题的', () => {
    const results = fitResults([TYPE, INTERPRET, CHANCE], ['政策标题', '政策正文'], ['政策类型名称', '一级行业'], true)
    expect(results.map(item => fitLevel(item))).toEqual(['ok', 'error', 'skip'])
    expect(fitSummary(results)).toEqual({ level: 'warn', text: '可用于政策类型判断；不能用于政策解读：输出字段缺少：一级场景，结果写不回表' })
    expect(fitSummary(fitResults([TYPE, CHANCE], ['政策正文'], ['政策类型名称'], true))).toEqual({ level: 'ok', text: '可用于政策类型判断' })
    expect(fitSummary(fitResults([CHANCE], ['政策正文'], ['政策类型名称'], true))).toBeNull()
  })

  it('解读模板只输出一级行业、一级场景也能写回，但要说清哪些列会空着；同一列的另一种写法也算', () => {
    const thin = checkTemplate(INTERPRET, ['政策正文'], ['一级行业', '一级场景', '判断理由'], true)
    expect(thin.errors).toEqual([])
    expect(thin.warnings).toEqual(['没有输出政策要文、二级行业、三级行业、二级场景等 6 个字段，写回时这些列会空着'])
    expect(fitSummary(fitResults([INTERPRET], ['政策正文'], ['一级行业', '一级场景'], true))?.text)
      .toBe('可用于政策解读，但没有输出政策要文、二级行业、三级行业、二级场景等 6 个字段，写回时这些列会空着')
    const full = ['政策概览', '一级行业', '一级场景', '二级行业', '三级行业', '二级场景', '三级场景']
    expect(checkTemplate(INTERPRET, ['政策正文'], full, true).warnings).toEqual(['没有输出备注，写回时这些列会空着'])
  })

  it('按输出字段猜模板给哪个任务用', () => {
    expect(guessTask([TYPE, INTERPRET, CHANCE], ['政策类型名称'])).toBe('type')
    expect(guessTask([TYPE, INTERPRET, CHANCE], ['政策概览', '一级行业', '一级场景'])).toBe('interpret')
    expect(guessTask([TYPE, INTERPRET, CHANCE], ['行业', '场景', '市场机会'])).toBe('opportunity')
    expect(guessTask([TYPE, INTERPRET, CHANCE], [])).toBe('type')
  })
})
