import { describe, expect, it } from 'vitest'

import { toggleValue } from '@/composables/useListQuery'
import { compactCount, siteFilters } from './filters'

describe('siteFilters', () => {
  it('maps status labels to API values and drops empty fields', () => {
    expect(siteFilters({ province_name: ['广东省', '海南省'], city_name: [], site_name: [], status: ['停更', '关注'] })).toEqual({
      province_name: ['广东省', '海南省'],
      city_name: undefined,
      site_name: undefined,
      status: ['stale', 'watch'],
    })
  })

  it('ignores unknown status labels instead of sending them', () => {
    expect(siteFilters({ status: ['断爬'] }).status).toBeUndefined()
  })
})

describe('toggleValue', () => {
  it('adds a missing value and removes an existing one', () => {
    expect(toggleValue(['正常'], '停更')).toEqual(['正常', '停更'])
    expect(toggleValue(['正常', '停更'], '停更')).toEqual(['正常'])
    expect(toggleValue('', '停更')).toEqual(['停更'])
  })
})

describe('compactCount', () => {
  it('keeps small numbers exact and abbreviates large ones', () => {
    expect(compactCount(9876)).toBe('9,876')
    expect(compactCount(123_456)).toBe('12.3 万')
    expect(compactCount(461_234_567)).toBe('4.61 亿')
  })
})
