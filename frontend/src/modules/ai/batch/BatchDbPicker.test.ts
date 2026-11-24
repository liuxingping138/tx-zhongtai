// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h, type Component } from 'vue'

import type { BatchRowsSummary } from '@/api/aiSamples'
import type { ContractTask, TaggingSamples } from '@/api/aiTagging'
import BatchDbPicker from './BatchDbPicker.vue'
import { deferred, summary, template } from './batch.testkit'

const api = vi.hoisted(() => ({ samples: vi.fn(), preview: vi.fn() }))
vi.mock('@/api/aiTagging', () => ({ getTaggingSamples: api.samples }))
vi.mock('@/api/aiSamples', () => ({ previewBatchRows: api.preview }))

const TASKS = [
  { code: 'opportunity', name: '政策市场机会', columns: ['源ID', '一级行业', '一级场景'], required_fields: ['市场机会'], optional_fields: [] },
] as unknown as ContractTask[]
const SAMPLE = { file_name: '数据库样本.xlsx', headers: ['一级行业'], rows: [['党政行业']], note: '取了 1 条' } as unknown as TaggingSamples

// 只留按钮能点：Element Plus 的输入控件这里不关心。
const ElButton: Component = { emits: ['click'], setup: (_, { slots, emit }) => () => h('button', { onClick: () => emit('click') }, slots.default?.()) }
const stubs = { 'el-button': ElButton, 'el-radio-group': true, 'el-radio-button': true, 'el-date-picker': true, 'el-input-number': true, 'el-input': true }

function mountPicker() {
  return mount(BatchDbPicker, {
    props: { template: template(), version: 'release', tasks: TASKS, disabled: false },
    global: { stubs },
  })
}

describe('BatchDbPicker 从政策库取数', () => {
  beforeEach(() => {
    api.samples.mockReset()
    api.preview.mockReset()
  })

  it('取数、预检后交回数据，带上检查它的模板和版本', async () => {
    api.samples.mockResolvedValue(SAMPLE)
    api.preview.mockResolvedValue(summary())
    const wrapper = mountPicker()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(api.preview).toHaveBeenCalledWith('t1', 'release', { file_name: '数据库样本.xlsx', headers: ['一级行业'], rows: [['党政行业']] })
    expect(wrapper.emitted('loaded')?.[0]?.[0]).toMatchObject({ templateId: 't1', version: 'release', note: '取了 1 条' })
    expect(wrapper.emitted('loading')).toEqual([[true], [false]])
  })

  it('请求在路上时换了版本：旧结果晚到也不交回，按钮马上能再点', async () => {
    const slow = deferred<BatchRowsSummary>()
    api.samples.mockResolvedValue(SAMPLE)
    api.preview.mockReturnValueOnce(slow.promise)
    const wrapper = mountPicker()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    await wrapper.setProps({ version: 'draft' })
    slow.resolve(summary())
    await flushPromises()
    expect(wrapper.emitted('loaded')).toBeUndefined()
    expect(wrapper.emitted('loading')).toEqual([[true]])
    // 换版本后再取：按新版本检查、交回
    api.preview.mockResolvedValueOnce(summary({ version: 'draft' }))
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(api.preview).toHaveBeenLastCalledWith('t1', 'draft', expect.anything())
    expect(wrapper.emitted('loaded')?.[0]?.[0]).toMatchObject({ version: 'draft' })
  })

  it('换了模板、或面板被卸载后，晚到的失败也不报', async () => {
    const slow = deferred<TaggingSamples>()
    api.samples.mockReturnValueOnce(slow.promise)
    const wrapper = mountPicker()
    await wrapper.find('button').trigger('click')
    await wrapper.setProps({ template: template({ id: 't2' }) })
    slow.reject(new Error('源库连不上'))
    await flushPromises()
    expect(wrapper.emitted('error')).toEqual([['']])
    expect(api.preview).not.toHaveBeenCalled()

    const late = deferred<TaggingSamples>()
    api.samples.mockReturnValueOnce(late.promise)
    await wrapper.find('button').trigger('click')
    wrapper.unmount()
    late.resolve(SAMPLE)
    await flushPromises()
    expect(api.preview).not.toHaveBeenCalled()
  })
})
