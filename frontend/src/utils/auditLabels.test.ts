import { describe, expect, it } from 'vitest'

import { actionLabel, moduleLabel } from './auditLabels'

describe('auditLabels', () => {
  it('模块编码转中文', () => {
    expect(moduleLabel('policy.sources')).toBe('信源管理')
    expect(moduleLabel('codebook.area_codes')).toBe('省市区编码表')
    expect(moduleLabel('auth')).toBe('登录认证')
  })

  it('动作编码转中文', () => {
    expect(actionLabel('import')).toBe('导入')
    expect(actionLabel('login')).toBe('登录')
    expect(actionLabel('catalog_sync')).toBe('同步清单')
    // 后端真会发的动作码都要有中文，不然日志里直接露出 ask、publish。
    expect([actionLabel('ask'), actionLabel('publish'), actionLabel('sync_scenarios')]).toEqual(['试发 / 样本试跑', '上线 / 下线', '同步新增场景'])
    expect(moduleLabel('ai.releases')).toBe('模板上线')
  })

  it('未知编码原样返回', () => {
    expect(moduleLabel('unknown.module')).toBe('unknown.module')
    expect(actionLabel('unknown')).toBe('unknown')
  })
})
