import { describe, expect, it } from 'vitest'

import { missingFieldsWarning } from './outputFields'

describe('没设输出字段的提醒', () => {
  it('设了输出字段不提醒', () => {
    expect(missingFieldsWarning('返回 {"行业": ""}', ['行业'])).toBe('')
  })
  it('提示词写了返回格式的，说出该填哪几个字段', () => {
    const content = '以json格式返回：\n{\n  "信息化属性": "信息化项目|非信息化",\n  "判断依据": "",\n  "剔除原因": []\n}'
    expect(missingFieldsWarning(content, [])).toBe('没设输出字段：结果 Excel 里不会有 AI 回答的那几列。提示词里要求返回「信息化属性、判断依据、剔除原因」，把这些名字一字不差填进「输出字段」')
  })
  it('提示词里看不出字段的，只说要填', () => {
    expect(missingFieldsWarning('总结这条政策', [])).toBe('没设输出字段：结果 Excel 里不会有 AI 回答的那几列。把要从回答里取的字段名填进「输出字段」')
  })
})
