// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'

vi.mock('vue-router', () => ({ useRoute: () => ({ path: '/policy/base-tags' }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 'u1' } }) }))

import ColumnPicker from './ColumnPicker.vue'
import type { DataColumn } from './dataColumns'
import { restoreColumns } from './columnSelection'

const CURRENT = ['name', 'plan', 'status', 'cost', 'watermark']
const STORAGE_KEY = 'zt:columns:v2:u1:/policy/base-tags'
const KNOWN_KEY = 'zt:columns:known:u1:/policy/base-tags'

const baseCols: DataColumn[] = [
  { prop: 'a', label: '列A' },
  { prop: 'b', label: '列B' },
]

function mountPicker(initialCols: DataColumn[], initialSelected = ['a', 'b']) {
  const columns = ref<DataColumn[]>([...initialCols])
  const selected = ref([...initialSelected])
  const Host = defineComponent({
    components: { ColumnPicker },
    setup: () => ({ columns, selected, defaults: initialCols.map(col => col.prop) }),
    template: '<ColumnPicker v-model="selected" :columns="columns" :defaults="defaults" />',
  })
  const wrapper = mount(Host, {
    global: {
      stubs: {
        'el-popover': { template: '<div><slot name="reference" /><slot /></div>' },
        'el-button': { template: '<button><slot /></button>' },
        'el-checkbox-group': { template: '<div><slot /></div>' },
        'el-checkbox': { template: '<label><slot /></label>' },
      },
    },
  })
  return { wrapper, columns, selected }
}

describe('列设置的记忆', () => {
  it('用户隐藏的列继续隐藏，页面上新加的列默认显示', () => {
    expect(restoreColumns(['name', 'status'], ['name', 'status', 'watermark'], CURRENT)).toEqual(['name', 'plan', 'status', 'cost'])
  })

  it('没有列清单的旧记录：分不清隐藏的和后加的，没记着的列都显示出来', () => {
    const old = ['name', 'enabled', 'daily_time', 'status', 'finished_at', 'watermark', 'next_run_at']
    expect(restoreColumns(old, null, CURRENT)).toEqual(CURRENT)
    expect(restoreColumns(['name', 'status'], null, CURRENT)).toEqual(CURRENT)
  })

  it('按页面列顺序返回；没记过或记的全不认识时交给默认值', () => {
    expect(restoreColumns(['watermark', 'name'], CURRENT, CURRENT)).toEqual(['name', 'watermark'])
    expect(restoreColumns(null, null, CURRENT)).toBeNull()
    expect(restoreColumns([], CURRENT, CURRENT)).toBeNull()
  })
})

describe('ColumnPicker 异步追加列', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('首屏之后动态追加的新列自动勾选并持久化，计数同步更新', async () => {
    const { wrapper, columns, selected } = mountPicker(baseCols)
    expect(selected.value).toEqual(['a', 'b'])
    expect(wrapper.find('.column-picker__count').text()).toBe('2/2')

    columns.value = [...baseCols, { prop: 'ai_industry', label: 'AI 行业', ai: true }]
    await nextTick()

    expect(selected.value).toEqual(['a', 'b', 'ai_industry'])
    expect(wrapper.find('.column-picker__count').text()).toBe('3/3')
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')).toEqual(['a', 'b', 'ai_industry'])
    expect(JSON.parse(localStorage.getItem(KNOWN_KEY) || '[]')).toEqual(['a', 'b', 'ai_industry'])
  })

  it('用户之前隐藏过的动态列再次异步加载时保持隐藏，新增的另一动态列自动显示', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(['a', 'b']))
    localStorage.setItem(KNOWN_KEY, JSON.stringify(['a', 'b', 'ai_old']))

    const { wrapper, columns, selected } = mountPicker(baseCols)
    expect(selected.value).toEqual(['a', 'b'])

    columns.value = [
      ...baseCols,
      { prop: 'ai_old', label: '旧 AI 列', ai: true },
      { prop: 'ai_new', label: '新 AI 列', ai: true },
    ]
    await nextTick()

    expect(selected.value).toEqual(['a', 'b', 'ai_new'])
    expect(wrapper.find('.column-picker__count').text()).toBe('3/4')
  })

  it('用户之前勾选过的动态列在异步加载后自动恢复显示', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(['a', 'ai_keep']))
    localStorage.setItem(KNOWN_KEY, JSON.stringify(['a', 'b', 'ai_keep']))

    const { wrapper, columns, selected } = mountPicker(baseCols)
    expect(selected.value).toEqual(['a'])

    columns.value = [...baseCols, { prop: 'ai_keep', label: '保留 AI 列', ai: true }]
    await nextTick()

    expect(selected.value).toEqual(['a', 'ai_keep'])
    expect(wrapper.find('.column-picker__count').text()).toBe('2/3')
  })
})
