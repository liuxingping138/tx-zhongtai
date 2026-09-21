import { describe, expect, it } from 'vitest'

import { filtersForExport } from './useListQuery'

describe('filtersForExport', () => {
  it('去掉分页参数，导出本来就不分页', () => {
    expect(filtersForExport({ site_name: '北京', page: 3, page_size: 50 })).toEqual({ site_name: '北京' })
  })

  it('丢掉空筛选项，不把空条件发给后端', () => {
    expect(filtersForExport({ site_name: '', tag: '政策', province_name: '' })).toEqual({ tag: '政策' })
  })

  it('保留全部已填条件，保证「所见即所导」', () => {
    expect(filtersForExport({ site_name: '北京', tag: '政策', city_name: '朝阳', page: 1, page_size: 20 })).toEqual({
      site_name: '北京',
      tag: '政策',
      city_name: '朝阳',
    })
  })

  it('无筛选时返回空对象，导出全表', () => {
    expect(filtersForExport({ page: 1, page_size: 20 })).toEqual({})
  })

  it('忽略数组等非标量值，后端筛选参数都是标量', () => {
    expect(filtersForExport({ tags: ['a', 'b'], tag: '政策' })).toEqual({ tag: '政策' })
  })
})
