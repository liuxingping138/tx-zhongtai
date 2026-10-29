import { describe, expect, it } from 'vitest'

import type { RunRow, SampleSummary } from '@/api/ai'
import type { SampleCompare } from '@/api/aiSamples'
import {
  answerLines, compareText, estimateCost, fieldCell, firstDiff, previousText, rowCounts, rowMatches, rowNote, rowsToWatch,
  sampleBars, shortTime, trialVerdict, versionLabel,
} from './sampleView'

const FIELDS = ['一级行业', '一级场景']

function row(number: number, status: RunRow['status'], overrides: Partial<RunRow> = {}): RunRow {
  return { row: number, inputs: { 政策标题: `政策${number}` }, status, error: '', items: [], answer: '', ...overrides }
}

const done = (scene: string) => [{ 一级行业: '医卫行业', 一级场景: scene }]

function compare(overrides: Partial<SampleCompare> = {}): SampleCompare {
  const run = { no: 2, id: 'r2', status: 'done' as const, total_count: 10, done_count: 10, failed_count: 0, format_failed_count: 0, created_at: '2026-10-28 16:02:00' }
  return { run, same_input: true, fields_changed: false, fixed: 1, broke: 1, changed: 1, same: 7, ...overrides }
}

describe('样本试跑：逐行状态和要看的行', () => {
  const rows = [
    row(1, 'done', { items: done('智慧航空') }),
    row(3, 'done', { items: done('智慧医院'), change: 'changed', previous: { status: 'done', items: done('智慧城市'), error: '', answer: '' } }),
    row(5, 'done', { items: done('数字政府'), change: 'fixed', previous: { status: 'format', items: [], error: '返回格式不对', answer: '说不清' } }),
    row(6, 'failed', { error: '模型 120 秒没回', previous: { status: 'failed', items: [], error: '超时', answer: '' } }),
    row(9, 'format', { change: 'broke', answer: '不做判断', previous: { status: 'done', items: done('数字政府'), error: '', answer: '' } }),
  ]

  it('计数，要看的行有问题的在前、变了的在后', () => {
    expect(rowCounts(rows)).toEqual({ done: 3, failed: 1, format: 1, changed: 3 })
    expect(rowsToWatch(rows).map(item => item.row)).toEqual([6, 9, 3, 5])
  })

  it('每一行为什么要看：失败原因、格式不对是不是这次改坏的、修好了、字段怎么变的', () => {
    const notes = Object.fromEntries(rowsToWatch(rows).map(item => [item.row, rowNote(item, FIELDS)]))
    expect(notes[6]).toEqual({ labels: [{ tone: 'failed', text: '调用失败' }], text: '模型 120 秒没回' })
    expect(notes[9]?.labels.map(item => item.text)).toEqual(['格式不对', '上次成功'])
    expect(notes[9]?.text).toContain('多半和这次改的提示词有关')
    expect(notes[5]).toEqual({ labels: [{ tone: 'fixed', text: '修好了' }], text: '上次格式不对，这次解析成功' })
    expect(notes[3]?.text).toBe('一级场景「智慧城市」改成「智慧医院」')
    expect(previousText(rows[3]!)).toBe('上次也是调用失败')
    expect(previousText(rows[0]!)).toBe('')
  })

  it('表格格子只在和上次不同时给出上次的值；展开时把回答写成一字段一行', () => {
    expect(fieldCell(rows[1]!, '一级场景')).toEqual({ now: '智慧医院', before: '智慧城市' })
    expect(fieldCell(rows[1]!, '一级行业')).toEqual({ now: '医卫行业', before: null })
    expect(fieldCell(rows[0]!, '一级场景').before).toBeNull()
    expect(answerLines(rows[0]!, FIELDS)).toBe('一级行业：医卫行业\n一级场景：智慧航空')
    expect(answerLines(rows[4]!, FIELDS)).toBe('不做判断')
    expect(answerLines(row(2, 'pending'), FIELDS)).toBe('这次没跑到这一行')
    expect(answerLines(row(2, 'done'), FIELDS)).toBe('（空）')
  })

  it('第一处不同：条数不同先说条数', () => {
    expect(firstDiff(done('A'), [...done('A'), ...done('B')], FIELDS)).toEqual({ field: '条数', before: '2 条', after: '1 条' })
    expect(firstDiff(done('A'), done('A'), FIELDS)).toBeNull()
  })

  it('说明文字只是措辞不同不算变了，标签变了照样指出来', () => {
    const fields = ['三级场景', '打标理由']
    const reason = (text: string) => text.repeat(10)
    const before = [{ 三级场景: '政务IT运维服务', 打标理由: reason('属于政务部门') }]
    expect(firstDiff([{ 三级场景: '政务IT运维服务', 打标理由: reason('招标单位是公安局') }], before, fields)).toBeNull()
    expect(firstDiff([{ 三级场景: '', 打标理由: reason('招标单位是公安局') }], before, fields)).toEqual({ field: '三级场景', before: '政务IT运维服务', after: '' })
    const changed = row(1, 'done', { items: [{ 三级场景: '', 打标理由: reason('换个说法') }], change: 'changed', previous: { status: 'done', items: before, error: '', answer: '' } })
    expect(fieldCell(changed, '打标理由').before).toBeNull()
    expect(fieldCell(changed, '三级场景').before).toBe('政务IT运维服务')
  })

  it('查找输入、字段、原因和原话', () => {
    expect(rowMatches(rows[1]!, '医院')).toBe(true)
    expect(rowMatches(rows[3]!, '120 秒')).toBe(true)
    expect(rowMatches(rows[4]!, '不做判断')).toBe(true)
    expect(rowMatches(rows[0]!, '  ')).toBe(true)
    expect(rowMatches(rows[0]!, '教育')).toBe(false)
  })
})

describe('和上一次试跑比的一句话', () => {
  it('写清修好、弄坏、变了各几行', () => {
    expect(compareText(compare())).toBe('对比第 2 次试跑（10-28 16:02）：修好 1 行，新出问题 1 行，1 行字段值变了，其余 7 行一样。')
    expect(compareText(compare({ fixed: 0, broke: 0, changed: 2, same: 0, fields_changed: true }))).toBe('对比第 2 次试跑（10-28 16:02）：两次的输出字段不同，2 行字段值变了。')
    expect(compareText(compare({ fixed: 0, broke: 0, changed: 0 }))).toBe('和第 2 次试跑（10-28 16:02）比，跑到的行结果都一样。')
  })

  it('测试样本换过就不逐行比；没有可比的不说', () => {
    expect(compareText(compare({ same_input: false, fixed: undefined }))).toBe('第 2 次试跑（10-28 16:02）用的测试样本和这次不同，没法逐行对比。')
    expect(compareText(null)).toBe('')
  })
})

describe('试发一行之后和样本试跑比', () => {
  const failed = row(9, 'format')
  const passed = row(3, 'done', { items: done('智慧城市') })

  it('修好了、还是不对、变坏了、结果变了、一样', () => {
    expect(trialVerdict(failed, done('数字政府'), 3, FIELDS)).toMatchObject({ tone: 'good', label: '修好了' })
    expect(trialVerdict(failed, null, 3, FIELDS)).toMatchObject({ tone: 'bad', label: '还是不对' })
    expect(trialVerdict(passed, null, 3, FIELDS)).toMatchObject({ tone: 'bad', label: '变坏了' })
    expect(trialVerdict(passed, done('智慧医院'), 3, FIELDS)?.text).toBe('和这一行在第 3 次样本试跑里比，一级场景「智慧城市」改成「智慧医院」。')
    expect(trialVerdict(passed, done('智慧城市'), 3, FIELDS)).toMatchObject({ tone: 'same' })
  })

  it('没试跑过这一行、没跑到、没设输出字段时不比', () => {
    expect(trialVerdict(undefined, done('A'), 3, FIELDS)).toBeNull()
    expect(trialVerdict(row(1, 'pending'), done('A'), 3, FIELDS)).toBeNull()
    expect(trialVerdict(passed, undefined, 3, FIELDS)).toBeNull()
  })
})

describe('批量任务的版本、估费和列表小竖条', () => {
  it('第 N 版或哪次保存的草稿', () => {
    expect(versionLabel({ release_no: 3, draft_saved_at: '' })).toBe('第 3 版')
    expect(versionLabel({ release_no: null, draft_saved_at: '2026-10-28 16:22:00' })).toBe('草稿 10-28 16:22')
    expect(versionLabel({ release_no: null, draft_saved_at: '' })).toBe('—')
    expect(shortTime('2026-10-28 16:22:00')).toBe('10-28 16:22')
  })

  it('按最近一次试跑每条的平均费用估；没试跑、没花钱、没行数给不出', () => {
    const sample = { done_count: 10, cost: 0.076 } as SampleSummary
    expect(estimateCost(sample, 2386)?.total).toBeCloseTo(18.1336)
    expect(estimateCost(sample, 2386)?.perRow).toBeCloseTo(0.0076)
    expect(estimateCost(null, 10)).toBeNull()
    expect(estimateCost({ ...sample, cost: 0 }, 10)).toBeNull()
    expect(estimateCost(sample, 0)).toBeNull()
  })

  it('10 条以内一条一根；更多时按比例分到 10 根', () => {
    expect(sampleBars({ total_count: 10, done_count: 10, failed_count: 2, format_failed_count: 1 }))
      .toEqual(['done', 'done', 'done', 'done', 'done', 'done', 'done', 'done', 'failed', 'format'])
    expect(sampleBars({ total_count: 4, done_count: 2, failed_count: 0, format_failed_count: 0 })).toEqual(['done', 'done', 'pending', 'pending'])
    expect(sampleBars({ total_count: 50, done_count: 50, failed_count: 10, format_failed_count: 0 })).toHaveLength(10)
    expect(sampleBars({ total_count: 0, done_count: 0, failed_count: 0, format_failed_count: 0 })).toEqual([])
  })
})
