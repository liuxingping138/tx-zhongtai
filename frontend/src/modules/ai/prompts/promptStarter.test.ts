import { describe, expect, it } from 'vitest'

import { compactPriceText, formatState, smartModelParts, splitFields } from '../shared/aiText'
import { starterPromptForCategory } from './promptStarter'

describe('新建冷启动骨架与模型智能拆解', () => {
  it('按政策、客户、招投标分类生成的标准骨架均自带已对齐的 JSON 返回格式要求', () => {
    for (const category of ['policy', 'customer', 'bidding']) {
      const spec = starterPromptForCategory(category)
      const fields = splitFields(spec.outputFields)
      expect(fields.length).toBeGreaterThanOrEqual(3)
      expect(formatState(spec.content, fields)).toBe('match')
    }
    expect(starterPromptForCategory('policy').buttonLabel).toContain('政策')
    expect(starterPromptForCategory('customer').buttonLabel).toContain('客户')
    expect(starterPromptForCategory('bidding').buttonLabel).toContain('招投标')
  })

  it('拆解长模型名为家族版本、档位后缀与是否联网，压缩单行计价文案', () => {
    expect(smartModelParts('字节-DeepSeek-V4.1-Flash经济版（不联网）')).toEqual({
      family: 'DeepSeek V4.1',
      tier: 'Flash经济',
      online: false,
    })
    expect(smartModelParts('字节-DeepSeek-V4-Flash（联网）')).toEqual({
      family: 'DeepSeek V4',
      tier: 'Flash',
      online: true,
    })
    expect(smartModelParts('')).toEqual({ family: '未选', tier: '', online: false })
    expect(compactPriceText({ input_price: '0.0016', output_price: '0.0064', web_search: true })).toBe(
      '输入 ¥1.6 · 输出 ¥6.4 /百万 token · 含联网',
    )
  })
})
