import { describe, expect, it } from 'vitest'
import { fieldLink, fieldText, fieldValue } from './cellValue'

describe('cell values', () => {
  it('shows scalars and hides objects instead of printing [object Object]', () => {
    expect(fieldValue({ a: '甲', n: 3, b: false }, 'a')).toBe('甲')
    expect(fieldValue({ n: 3 }, 'n')).toBe('3')
    expect(fieldValue({ b: false }, 'b')).toBe('false')
    expect(fieldValue({ o: { x: 1 } }, 'o')).toBe('')
    expect(fieldValue({}, 'missing')).toBe('')
  })

  it('formats time columns in Beijing time and marks empty values with a dash', () => {
    expect(fieldText({ t: '2026-10-21T01:14:32Z' }, { prop: 't', label: '入库时间', time: true })).toBe('2026-10-21 09:14:32')
    expect(fieldText({ t: '' }, { prop: 't', label: '入库时间' })).toBe('—')
    expect(fieldText({ name: '甲' }, { prop: 'name', label: '名称' })).toBe('甲')
  })

  it('only links to http and https, adding https when the scheme is missing', () => {
    const col = { prop: 'url', label: '网址', link: true }
    expect(fieldLink({ url: 'example.gov.cn/a' }, col)).toBe('https://example.gov.cn/a')
    expect(fieldLink({ url: 'http://example.gov.cn' }, col)).toBe('http://example.gov.cn/')
    expect(fieldLink({ url: 'javascript:alert(1)' }, col)).toBeUndefined()
    expect(fieldLink({ url: '  ' }, col)).toBeUndefined()
    expect(fieldLink({ url: 'http://' }, col)).toBeUndefined()
  })
})
