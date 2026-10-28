import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import type { ContractTask } from '@/api/aiTagging'
import { useAuthStore } from '@/stores/auth'
import { useTaskFit } from './useTaskFit'

const TASKS: ContractTask[] = [
  { code: 'type', name: '政策类型判断', columns: ['政策标题', '政策正文'], required_fields: ['政策类型名称'], optional_fields: [], prompt_id: 'p1' },
  { code: 'opportunity', name: '政策市场机会', columns: ['政策正文', '行业场景'], required_fields: ['市场机会'], optional_fields: [], prompt_id: '' },
]
const contract = vi.fn(() => Promise.resolve({ tasks: TASKS }))
vi.mock('@/api/aiTagging', () => ({ getTaggingContract: () => contract() }))

describe('政策类模板的定时任务适配', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    contract.mockClear()
  })

  it('有政策数据查看权才去取约定；按草稿检查，不是政策类就不显示', async () => {
    const form = reactive({ category: 'policy', content: '@【政策标题】@【政策正文】', output_fields: '政策类型名称', code_table: 'policy_types' })
    const fit = useTaskFit(form)
    await fit.load()
    expect(contract).not.toHaveBeenCalled()
    expect(fit.results.value).toEqual([])

    useAuthStore().resources = [{ code: 'policy.base_tags', level: 'READ' }] as never
    await fit.load()
    await fit.load()
    expect(contract).toHaveBeenCalledOnce()
    expect(fit.results.value.map(item => [item.code, item.check.errors.length, item.skip])).toEqual([['type', 0, false], ['opportunity', 2, true]])
    expect(fit.visible.value).toBe(true)
    expect(fit.sampleTasks.value).toHaveLength(2)
    expect(fit.usedBy('p1')).toEqual(['政策类型判断'])
    expect(fit.usedBy('p2')).toEqual([])
    expect(fit.usedBy('')).toEqual([])

    form.content = ''
    form.output_fields = ''
    expect(fit.results.value).toEqual([])
    expect(fit.visible.value).toBe(true)

    form.category = 'customer'
    expect(fit.results.value).toEqual([])
    expect(fit.sampleTasks.value).toEqual([])
    expect(fit.usedBy('p1')).toEqual([])  // 定时任务只用政策类模板
  })

  it('政策服务暂时取不到约定：先不显示，下次再试', async () => {
    useAuthStore().resources = [{ code: 'policy.base_tags', level: 'READ' }] as never
    contract.mockRejectedValueOnce(new Error('503'))
    const fit = useTaskFit(reactive({ category: 'policy', content: '@【政策正文】', output_fields: '', code_table: '' }))
    await fit.load()
    expect(fit.visible.value).toBe(false)
    expect(fit.usedBy('p1')).toBeNull()  // 取不到就说不清谁在用，不能当成没人用
    await fit.load()
    expect(fit.results.value).toHaveLength(2)
  })
})
