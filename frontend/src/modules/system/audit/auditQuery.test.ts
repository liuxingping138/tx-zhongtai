import { describe, expect, it } from 'vitest'

import { emptyAuditQuery, hasFilters, toRequestParams } from './auditQuery'

describe('操作日志请求参数', () => {
  it('业务模块换成模块编码第一段，空条件不发', () => {
    const params = toRequestParams({ ...emptyAuditQuery(), directory: ['系统管理'], business_line: ['tender'] })
    expect(params).toMatchObject({ module_root: ['auth', 'iam', 'system'], business_line: ['tender'], module_code: undefined })
    expect(toRequestParams(emptyAuditQuery()).module_root).toBeUndefined()
    expect([hasFilters(emptyAuditQuery()), hasFilters({ ...emptyAuditQuery(), directory: ['政策'] })]).toEqual([false, true])
  })
})
