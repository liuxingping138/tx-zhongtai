import { describe, expect, it } from 'vitest'

import { actionLabel, aiTargetsToResolve, businessLineLabel, directoryLabel, moduleLabel } from './auditLabels'

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

  it('业务模块取菜单目录，类型取业务线', () => {
    expect(['auth', 'system.users', 'policy.sources', 'codebook.area_codes', 'ai.prompts'].map(directoryLabel))
      .toEqual(['系统管理', '系统管理', '政策', '码表管理', 'AI提问'])
    expect(businessLineLabel('policy.base_tags')).toBe('政策')
    expect(businessLineLabel('ai.batch_runs', { category: 'tender' })).toBe('招投标')
    // AI 的旧事件没记模板类型、系统管理和码表管理不属于哪条业务线：都显示「-」。
    expect([businessLineLabel('ai.models', {}), businessLineLabel('system.users'), businessLineLabel('codebook.scenarios')])
      .toEqual(['-', '-', '-'])
  })

  it('早先没记类型的 AI 事件，用按目标ID 查到的类型', () => {
    expect(businessLineLabel('ai.prompts', {}, 'customer')).toBe('客户')
    // 事件里记了的以记的为准。
    expect(businessLineLabel('ai.prompts', { category: 'tender' }, 'customer')).toBe('招投标')
    const rows = [
      { module_code: 'ai.prompts', target_id: 'p1', changes: {} },
      { module_code: 'ai.batch_runs', target_id: 'p1', changes: null },
      { module_code: 'ai.prompts', target_id: 'p2', changes: { category: 'policy' } },
      { module_code: 'policy.sources', target_id: 's1', changes: null },
      { module_code: 'ai.models', target_id: null, changes: null },
    ]
    expect(aiTargetsToResolve(rows)).toEqual(['p1'])
  })
})
