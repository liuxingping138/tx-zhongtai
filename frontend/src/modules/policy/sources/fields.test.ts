import { describe, expect, it } from 'vitest'

import { checkArea } from './fields'

describe('checkArea', () => {
  it('新建时省市区编码至少要有一项：要用它分配网站编码', () => {
    expect(checkArea({ province_code: '', city_code: '', district_code: '' }, null)?.key).toBe('province_code')
    expect(checkArea({ province_code: '11', city_code: '', district_code: '' }, null)).toBeUndefined()
  })

  it('编辑已有网站编码的信源不要求：全国、国央企信源本来就没有区划编码，改标签也要能保存', () => {
    expect(checkArea({ province_code: '', city_code: '', district_code: '' }, { id: 's1' })).toBeUndefined()
  })
})
