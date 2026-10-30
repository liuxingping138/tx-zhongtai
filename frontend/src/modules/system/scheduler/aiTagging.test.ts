import { describe, expect, it } from 'vitest'

import { cursorToSend, formatYuan, runResultText, taskOfJob } from './aiTagging'

describe('政策 AI 打标', () => {
  it('金额到分，试跑的小额保留 4 位', () => {
    expect([formatYuan('12.345'), formatYuan('0.0031'), formatYuan(0), formatYuan(null)]).toEqual(['¥12.35', '¥0.0031', '¥0.00', '¥0.00'])
    expect(formatYuan('abc')).toBe('—')
  })

  it('任务调度编码对回三个打标任务，别的任务不算', () => {
    expect(['policy_ai_type', 'policy_ai_interpret', 'policy_ai_opportunity'].map(taskOfJob)).toEqual(['type', 'interpret', 'opportunity'])
    expect([taskOfJob('crawler'), taskOfJob('policy_ai'), taskOfJob('policy_ai_x')]).toEqual([null, null, null])
  })

  it('执行结果：失败写原因，成功写说明，花过钱带上金额', () => {
    expect(runResultText({ error_message: '还没有选模板', note: '' })).toBe('还没有选模板')
    expect(runResultText({ error_message: '', note: '读取 10 条', cost: '0.325566' })).toBe('读取 10 条 · ¥0.33')
    expect(runResultText({ error_message: '', note: '没有待解读的政策', cost: '0' })).toBe('没有待解读的政策')
    expect(runResultText(null)).toBe('—')
  })
})

describe('cursorToSend', () => {
  it('没改起始日期就不发，免得把这期间已前移的读取进度改回去', () => {
    expect(cursorToSend('2026-10-20', '2026-10-20')).toBe('')
    expect(cursorToSend('2026-09-01', '2026-10-20')).toBe('2026-09-01')
  })
})
