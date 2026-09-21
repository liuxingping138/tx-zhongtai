import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useFilterOptions } from './useFilterOptions'

const fetchMock = vi.fn()
const searchMock = vi.fn()

vi.mock('@/api/filterOptions', () => ({
  fetchFilterOptions: (...args: unknown[]) => fetchMock(...args),
  searchFilterOptions: (...args: unknown[]) => searchMock(...args),
}))

beforeEach(() => {
  fetchMock.mockReset()
  searchMock.mockReset()
})

describe('useFilterOptions', () => {
  it('候选完整的字段只给 options，不走服务端搜索', async () => {
    fetchMock.mockResolvedValue({
      options: { province_name: { items: ['北京市', '上海市'], truncated: false } },
    })
    const filters = useFilterOptions('/policy/sources')
    await filters.load()

    const bound = filters.bind('province_name')
    expect(bound.options).toEqual(['北京市', '上海市'])
    expect(bound.remoteSearch).toBeUndefined()
  })

  it('候选被截断的字段提供服务端搜索', async () => {
    fetchMock.mockResolvedValue({
      options: { site_name: { items: ['打底1'], truncated: true } },
    })
    searchMock.mockResolvedValue({ items: ['北京市人民政府'] })
    const filters = useFilterOptions('/policy/sources')
    await filters.load()

    const bound = filters.bind('site_name')
    expect(bound.options).toEqual(['打底1'])
    expect(bound.remoteSearch).toBeTypeOf('function')

    await expect(bound.remoteSearch!('北京')).resolves.toEqual(['北京市人民政府'])
    expect(searchMock).toHaveBeenCalledWith('/policy/sources', 'site_name', '北京')
  })

  it('未知字段退化为空候选，不抛错', async () => {
    fetchMock.mockResolvedValue({ options: {} })
    const filters = useFilterOptions('/policy/sources')
    await filters.load()

    expect(filters.bind('zz_missing').options).toEqual([])
  })

  it('选了省份时地市用该省列表，不走服务端搜索', async () => {
    fetchMock.mockResolvedValue({
      options: { city_name: { items: ['打底'], truncated: true } },
      city_by_province: { 北京市: ['北京市'], 江苏省: ['南京市', '苏州市'] },
    })
    const filters = useFilterOptions('/policy/sources')
    await filters.load()

    const scoped = filters.bindCity('city_name', '江苏省')
    expect(scoped.options).toEqual(['南京市', '苏州市'])
    expect(scoped.remoteSearch).toBeUndefined()
  })

  it('没选省份时地市回落到服务端搜索', async () => {
    fetchMock.mockResolvedValue({
      options: { city_name: { items: ['打底'], truncated: true } },
      city_by_province: { 江苏省: ['南京市'] },
    })
    const filters = useFilterOptions('/policy/sources')
    await filters.load()

    expect(filters.bindCity('city_name', '').remoteSearch).toBeTypeOf('function')
  })

  it('选项接口失败不抛错，筛选框退化为自由输入', async () => {
    fetchMock.mockRejectedValue(new Error('boom'))
    const filters = useFilterOptions('/policy/sources')
    await expect(filters.load()).resolves.toBeUndefined()
    expect(filters.loaded.value).toBe(false)
    expect(filters.bind('site_name').options).toEqual([])
  })
})
