import { describe, expect, it } from 'vitest'
import { listQuery, parseReviewQuery, reviewQuery } from './reviewQuery'

const KEYS = ['policy_title', 'data_status', 'industry_l1']

describe('review page query', () => {
  it('carries the applied filters and the position, but not the list paging', () => {
    const query = reviewQuery({ policy_title: [], data_status: ['待验证'], industry_l1: ['制造业', '教育'], page: 3, page_size: 50 }, 102, 50)
    expect(query).toEqual({ data_status: ['待验证'], industry_l1: ['制造业', '教育'], pos: '102', ps: '50' })
  })

  it('leaves the page size out when it is the default', () => {
    expect(reviewQuery({ data_status: [] }, 0, 20)).toEqual({ pos: '0' })
  })

  it('reads back only the known filters and a valid position', () => {
    const context = parseReviewQuery({ data_status: '待验证', industry_l1: ['制造业', '教育'], other: 'x', pos: '7', ps: '50' }, KEYS)
    expect(context).toEqual({ filters: { data_status: ['待验证'], industry_l1: ['制造业', '教育'] }, position: 7, pageSize: 50 })
  })

  it('treats a missing or broken position as opened directly, without previous and next', () => {
    expect(parseReviewQuery({}, KEYS).position).toBeNull()
    expect(parseReviewQuery({ pos: '-1' }, KEYS).position).toBeNull()
    expect(parseReviewQuery({ pos: 'abc' }, KEYS).position).toBeNull()
    expect(parseReviewQuery({ ps: '7' }, KEYS).pageSize).toBe(20)
  })

  it('returns to the list page that holds the record, with the same filters', () => {
    const context = parseReviewQuery({ data_status: '待验证', pos: '45', ps: '20' }, KEYS)
    expect(listQuery(context)).toEqual({ data_status: ['待验证'], page: '3' })
    expect(listQuery(parseReviewQuery({ pos: '5', ps: '50' }, KEYS))).toEqual({ page_size: '50' })
  })
})
