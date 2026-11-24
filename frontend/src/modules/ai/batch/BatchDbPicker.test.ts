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
  { code: 'type', name: '政策类型判断', columns: ['源ID', '政策正文'], required_fields: ['政策类型名称'], optional_fields: [] },
  { code: 'opportunity', name: '政策市场机会', columns: ['源ID', '一级行业', '一级场景'], required_fields: ['市场机会'], optional_fields: [] },
] as unknown as ContractTask[]
const SAMPLE = { file_name: '数据库样本.xlsx', headers: ['一级行业'], rows: [['党政行业']], note: '取了 1 条' } as unknown as TaggingSamples

// 只留按钮能点：Element Plus 的输入控件这里不关心。
const ElButton: Component = { emits: ['click'], setup: (_, { slots, emit }) => () => h('button', { onClick: () => emit('click') }, slots.default?.()) }
const stubs = { 'el-button': ElButton, 'el-radio-group': true, 'el-radio-button': true, 'el-date-picker': true, 'el-input-number': true, 'el-input': true, 'el-select': true, 'el-option': true, CodebookFilterSelect: true }

function mountPicker() {
  return mount(BatchDbPicker, {
    props: {
      template: template({ fields: ['市场机会'], release: { ...template().release!, fields: ['市场机会'] } }),
      version: 'release',
      tasks: TASKS,
      disabled: false,
    },
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

  it('按所选版本（线上版本 vs 草稿）的输出字段及晚到的任务契约推断默认取数步骤', async () => {
    api.samples.mockResolvedValue(SAMPLE)
    api.preview.mockResolvedValue(summary())
    const tpl = template({
      fields: ['市场机会'],
      release: { ...template().release!, fields: ['政策类型名称'] },
    })
    const wrapper = mount(BatchDbPicker, {
      props: { template: tpl, version: 'release', tasks: [], disabled: false },
      global: { stubs },
    })
    // 契约异步加载完成后，线上版本只有「政策类型名称」-> 推断为 type
    await wrapper.setProps({ tasks: TASKS })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(api.samples).toHaveBeenLastCalledWith('type', expect.any(String), 20, expect.anything())

    // 切到草稿（输出字段为「市场机会」）-> 自动切为 opportunity；设一级行业与关键词后再切回线上（type），隐藏筛选项自动清空
    await wrapper.setProps({ version: 'draft' })
    wrapper.findComponent({ name: 'CodebookFilterSelect' })
    const vm = wrapper.vm as unknown as { industryL1: string; keyword: string }
    vm.industryL1 = '党政行业'
    vm.keyword = '算力'
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(api.samples).toHaveBeenLastCalledWith('opportunity', expect.any(String), 20, {
      province: '',
      keyword: '算力',
      industry_l1: '党政行业',
    })

    await wrapper.setProps({ version: 'release' })
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(api.samples).toHaveBeenLastCalledWith('type', expect.any(String), 20, {
      province: '',
      keyword: '',
      industry_l1: '',
    })
  })
})
