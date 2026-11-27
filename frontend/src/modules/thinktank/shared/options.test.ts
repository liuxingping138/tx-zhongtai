import { describe, expect, it } from 'vitest'

import {
  DEPARTMENT_FALLBACK,
  displayCategory,
  FILE_TYPE_FALLBACK,
  INDUSTRY_FALLBACK,
  joinPipeTags,
  joinWhoWhen,
  MARKET_CATEGORY_FALLBACK,
  parseContentDispositionFilename,
  preferOptions,
  PRODUCT_TYPE_FALLBACK,
  PROPOSAL_RESULT_OPTIONS,
  PROVINCE_FALLBACK,
  scopedOptions,
  splitPipeTags,
  suffixTagType,
  TAG_STATUS_OPTIONS,
  YES_NO_OPTIONS,
} from './options'

describe('thinktank shared options helpers', () => {
  it('exposes complete 6 codebook fallback arrays', () => {
    expect(FILE_TYPE_FALLBACK).toHaveLength(14)
    expect(DEPARTMENT_FALLBACK).toHaveLength(9)
    expect(INDUSTRY_FALLBACK).toHaveLength(12)
    expect(PRODUCT_TYPE_FALLBACK).toHaveLength(12)
    expect(PROVINCE_FALLBACK).toHaveLength(32)
    expect(PROVINCE_FALLBACK[0]).toBe('集团')
    expect(MARKET_CATEGORY_FALLBACK).toEqual(['行客', '商客', '综合', '无'])
    expect(YES_NO_OPTIONS).toEqual(['是', '否'])
    expect(PROPOSAL_RESULT_OPTIONS).toEqual(['中标', '未中标', '待定', '流标'])
    expect(TAG_STATUS_OPTIONS).toEqual(['已定义', '未定义'])
  })

  it('prefers non-empty deduplicated dynamic options and falls back gracefully', () => {
    expect(preferOptions([' 产品 ', '产品', '', '通知'], ['兜底'])).toEqual(['产品', '通知'])
    expect(preferOptions([], ['兜底A', ' 兜底B ', '兜底A'])).toEqual(['兜底A', '兜底B'])
    expect(preferOptions(undefined, ['默认'])).toEqual(['默认'])
    expect(preferOptions(null, ['默认'])).toEqual(['默认'])
    expect(preferOptions(undefined)).toEqual([])
  })

  it('filters dynamic/fallback options by allowed scope and exclusions', () => {
    expect(scopedOptions(['产品', '未定义', '经分'], ['兜底'], ['产品', '经分'], ['未定义'])).toEqual(['产品', '经分'])
    expect(scopedOptions([], ['产品', '经分'], ['经分'])).toEqual(['经分'])
    expect(scopedOptions(['产品', '未定义'], ['兜底'], undefined, ['未定义'])).toEqual(['产品'])
    expect(scopedOptions(['产品', '经分'], ['兜底'], null)).toEqual(['产品', '经分'])
  })

  it('handles pipe tags, category display, suffix tags, filenames and who-when join', () => {
    expect(splitPipeTags('')).toEqual([])
    expect(splitPipeTags(undefined)).toEqual([])
    expect(splitPipeTags('党政 | 教育 | ')).toEqual(['党政', '教育'])
    expect(joinPipeTags([' 党政 ', '', '金融'])).toBe('党政|金融')
    expect(displayCategory('')).toBe('未定义')
    expect(displayCategory('  ')).toBe('未定义')
    expect(displayCategory('行业研究报告')).toBe('行业研究报告')
    expect(suffixTagType('pdf')).toBe('danger')
    expect(suffixTagType('PPT')).toBe('warning')
    expect(suffixTagType('EXCEL')).toBe('success')
    expect(suffixTagType('WORD')).toBe('info')
    expect(suffixTagType('')).toBe('info')
    expect(parseContentDispositionFilename("attachment; filename*=UTF-8''%E6%8A%A5%E5%91%8A.xlsx", 'x.xlsx')).toBe('报告.xlsx')
    expect(parseContentDispositionFilename("attachment; filename*=UTF-8''%E0%A4%A", 'bad.xlsx')).toBe('bad.xlsx')
    expect(parseContentDispositionFilename('attachment; filename="a.pdf"', 'b.pdf')).toBe('a.pdf')
    expect(parseContentDispositionFilename('attachment;', 'b.pdf')).toBe('b.pdf')
    expect(parseContentDispositionFilename(undefined, 'b.pdf')).toBe('b.pdf')
    expect(joinWhoWhen('张三', '2026-01-01', v => v)).toBe('张三 · 2026-01-01')
    expect(joinWhoWhen('张三', '', v => v)).toBe('张三')
    expect(joinWhoWhen('', '', v => v)).toBe('—')
  })
})
