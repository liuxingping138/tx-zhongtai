import { describe, expect, it } from 'vitest'
import { filtersForExport } from '@/composables/useListQuery'
import { crawlerFilters } from './filters'

describe('爬虫监测的列表与导出条件', () => {
  it.each([['正常', 'normal'], ['观察', 'watch'], ['断爬', 'broken'], ['从未出数', 'never']])(
    '筛选 %s 时导出使用相同的接口枚举 %s', (label, apiStatus) => {
      const applied = { site_name: ['测试网站'], health_status: [label], page: 2, page_size: 20 }
      const list = crawlerFilters(applied)
      const download = filtersForExport(crawlerFilters(applied))
      expect(list.health_status).toEqual([apiStatus])
      expect(download).toEqual({ site_name: ['测试网站'], health_status: [apiStatus] })
    },
  )

  it('多选状态全部换成接口枚举，未知状态名丢掉', () => {
    expect(crawlerFilters({ health_status: ['断爬', '从未出数', '不存在'] }).health_status).toEqual(['broken', 'never'])
  })

  it('兼容旧链接里的单值条件', () => {
    expect(crawlerFilters({ province_name: '广东省', health_status: '断爬' })).toMatchObject({
      province_name: ['广东省'],
      health_status: ['broken'],
    })
  })

  it('未提交的输入不改变已生效的下载范围', () => {
    const applied = { site_name: ['原网站'], health_status: ['断爬'] }
    const draft = { ...applied, site_name: ['新网站'], health_status: ['正常'] }
    expect(filtersForExport(crawlerFilters(applied))).toEqual({ site_name: ['原网站'], health_status: ['broken'] })
    expect(crawlerFilters(draft).health_status).toEqual(['normal'])
  })
})
