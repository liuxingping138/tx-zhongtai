// @vitest-environment happy-dom
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'

import BatchDbPicker from './BatchDbPicker.vue'
import BatchVersionPick from './BatchVersionPick.vue'
import NewBatchTask from './NewBatchTask.vue'
import { MODELS, summary, template } from './batch.testkit'

const api = vi.hoisted(() => ({ fromRows: vi.fn(), upload: vi.fn(), confirm: vi.fn() }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: () => undefined }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), error: vi.fn() }, ElMessageBox: { confirm: api.confirm } }))
vi.mock('@/api/ai', () => ({ previewBatchInput: vi.fn(), startBatchRun: api.upload, AI_BASE: '/api/v1/ai' }))
vi.mock('@/api/aiSamples', () => ({ startBatchRunFromRows: api.fromRows }))
vi.mock('@/api/aiTagging', () => ({ getTaggingSamples: vi.fn() }))
vi.mock('./useSampleTasks', () => ({
  useSampleTasks: () => ({
    tasks: ref([{ code: 'opportunity', name: '政策市场机会', columns: [] }]),
    provinces: ref(['广东省']),
    industries: ref(['党政行业']),
    ensure: () => Promise.resolve(),
  }),
}))

// 抽屉要把正文和底部按钮都画出来；其余子组件用自动替身：只看父组件怎么收结果、什么时候锁住选择。
const Drawer = defineComponent({ setup: (_, { slots }) => () => h('div', [slots.default?.(), slots.footer?.()]) })

const ELEMENT_STUBS = Object.fromEntries(
  ['el-radio-group', 'el-radio-button', 'el-radio', 'el-button', 'el-icon', 'el-input-number', 'el-switch', 'el-alert'].map(name => [name, true]),
)

type Emitter = { $emit: (event: string, ...args: unknown[]) => void }
const fire = (found: { vm: unknown }, event: string, ...args: unknown[]) => (found.vm as Emitter).$emit(event, ...args)

async function openDrawer() {
  const wrapper = mount(NewBatchTask, {
    props: { templates: [template()], models: MODELS, modelValue: false },
    global: { stubs: { BatchVersionPick: true, BatchDbPicker: true, 'el-drawer': Drawer, ...ELEMENT_STUBS }, renderStubDefaultSlot: true },
  })
  await wrapper.setProps({ modelValue: true })
  fire(wrapper.findComponent(BatchVersionPick), 'update:templateId', 't1')
  await flushPromises()
  // 第一个单选组是「上传 Excel / 从政策库取数」
  fire(wrapper.findAllComponents({ name: 'el-radio-group' })[0]!, 'update:modelValue', 'db')
  await flushPromises()
  return wrapper
}

const ROWS = { file_name: '数据库样本.xlsx', headers: ['一级行业'], rows: [['党政行业'], ['教育行业']] }
const loaded = (overrides: Record<string, unknown> = {}) => ({ payload: ROWS, summary: summary(), note: '取了 2 条', templateId: 't1', version: 'release', ...overrides })
const startButton = (wrapper: { findAllComponents: VueWrapper['findAllComponents'] }) => wrapper.findAllComponents({ name: 'el-button' }).find(item => item.text().startsWith('开始运行'))!

describe('NewBatchTask 从政策库取数', () => {
  beforeEach(() => {
    api.fromRows.mockReset().mockResolvedValue({})
    api.upload.mockReset()
    api.confirm.mockReset().mockResolvedValue('confirm')
  })

  it('取数检查期间锁住模板和版本的选择', async () => {
    const wrapper = await openDrawer()
    fire(wrapper.findComponent(BatchDbPicker), 'loading', true)
    await flushPromises()
    expect(wrapper.findComponent(BatchVersionPick).props('disabled')).toBe(true)
    fire(wrapper.findComponent(BatchDbPicker), 'loading', false)
    await flushPromises()
    expect(wrapper.findComponent(BatchVersionPick).props('disabled')).toBe(false)
  })

  it('丢掉换了模板或版本之前的旧结果，只收这一版的', async () => {
    const wrapper = await openDrawer()
    const picker = wrapper.findComponent(BatchDbPicker)
    fire(picker, 'loaded', loaded({ version: 'draft' }))
    fire(picker, 'loaded', loaded({ templateId: 't2' }))
    await flushPromises()
    expect(wrapper.text()).not.toContain('取了 2 条')
    expect(startButton(wrapper).attributes('disabled')).toBe('true')

    fire(picker, 'loaded', loaded({ summary: summary({ warning: '有 1 个单元格超过 Excel 单元格上限' }) }))
    await flushPromises()
    expect(wrapper.text()).toContain('取了 2 条')
    expect(wrapper.text()).toContain('有 1 个单元格超过 Excel 单元格上限')
    expect(startButton(wrapper).attributes('disabled')).toBe('false')
    fire(startButton(wrapper), 'click')
    await flushPromises()
    expect(api.fromRows).toHaveBeenCalledWith({ prompt_id: 't1', version: 'release', thinking: false, limit: 0 }, ROWS)
    expect(api.upload).not.toHaveBeenCalled()
  })

  it('切回上传 Excel 后，晚到的取数结果不再生效', async () => {
    const wrapper = await openDrawer()
    const picker = wrapper.findComponent(BatchDbPicker)
    fire(wrapper.findAllComponents({ name: 'el-radio-group' })[0]!, 'update:modelValue', 'upload')
    await flushPromises()
    fire(picker, 'loaded', loaded())
    await flushPromises()
    expect(wrapper.text()).not.toContain('取了 2 条')
    expect(startButton(wrapper).attributes('disabled')).toBe('true')
  })
})
