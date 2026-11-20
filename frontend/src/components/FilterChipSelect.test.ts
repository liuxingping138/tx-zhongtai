import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, h, nextTick, reactive, type Component, type SetupContext } from 'vue'
import { renderToString } from 'vue/server-renderer'

vi.mock('vue', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue')>()
  return { ...actual, useSSRContext: () => ({ modules: new Set<string>() }) }
})

import FilterChipSelect from './FilterChipSelect.vue'

interface ExposedChipApi {
  open: { value: boolean }
  keyword: { value: string }
  displayOptions: { value: string[] }
  emptyText: { value: string }
  summaryText: { value: string }
  searching: { value: boolean }
  remoteFailed: { value: boolean }
  toggleValue: (value: string) => void
  onEnterKeyword: () => void
  clearAll: () => void
}

async function renderChipHtml(initialProps: Record<string, unknown>): Promise<string> {
  const app = createSSRApp(FilterChipSelect as Component, initialProps)
  const StubPopover: Component = {
    inheritAttrs: false,
    setup(_props: unknown, { slots }: SetupContext) {
      return () => h('div', [slots.reference?.(), slots.default?.()])
    },
  }
  const StubIcon: Component = {
    inheritAttrs: false,
    setup: (_p: unknown, { slots }: SetupContext) => () => h('span', slots.default?.()),
  }
  const StubInput: Component = { inheritAttrs: false, render: () => h('input') }
  app.component('ElPopover', StubPopover)
  app.component('ElIcon', StubIcon)
  app.component('ElInput', StubInput)
  return renderToString(app)
}

function mountChipSetup(initialProps: {
  modelValue: string[]
  label: string
  options: string[]
  labels?: Record<string, string>
  remoteSearch?: (keyword: string) => Promise<string[]>
}) {
  const props = reactive({ ...initialProps })
  const emitted: string[][] = []
  let exposed!: ExposedChipApi
  const scope = effectScope()
  scope.run(() => {
    const setupFn = (FilterChipSelect as { setup?: (p: unknown, c: unknown) => unknown }).setup
    setupFn?.(props, {
      emit: (_event: string, value: string[]) => {
        emitted.push(value)
        props.modelValue = value
      },
      expose: (api: ExposedChipApi) => { exposed = api },
      attrs: {},
      slots: {},
    })
  })
  return { props, emitted, exposed, scope }
}

const scopes: Array<() => void> = []
afterEach(() => {
  while (scopes.length) scopes.pop()?.()
  vi.useRealTimers()
})

describe('FilterChipSelect', () => {
  it('renders unselected label and selected multi-value summary with clear button', async () => {
    const idleHtml = await renderChipHtml({
      modelValue: [],
      label: '文件类型',
      options: ['产品', '经分'],
    })
    expect(idleHtml).toContain('文件类型')
    expect(idleHtml).not.toContain('aria-label="清除"')

    const activeHtml = await renderChipHtml({
      modelValue: ['产品', '经分'],
      label: '文件类型',
      options: ['产品', '经分'],
    })
    expect(activeHtml).toContain('文件类型:')
    expect(activeHtml).toContain('产品 +1')
    expect(activeHtml).toContain('title="产品、经分"')
    expect(activeHtml).toContain('aria-label="清除"')
  })

  it('toggles multiple values, shows mapped summary, and clears inline', () => {
    const { emitted, exposed, scope } = mountChipSetup({
      modelValue: [],
      label: '文件类型',
      options: ['prod', 'jf', 'notice'],
      labels: { prod: '产品', jf: '经分', notice: '通知' },
    })
    scopes.push(() => scope.stop())

    exposed.toggleValue('prod')
    expect(emitted.at(-1)).toEqual(['prod'])
    expect(exposed.summaryText.value).toBe('产品')

    exposed.toggleValue('jf')
    expect(emitted.at(-1)).toEqual(['prod', 'jf'])
    expect(exposed.summaryText.value).toBe('产品 +1')

    exposed.toggleValue('prod')
    expect(emitted.at(-1)).toEqual(['jf'])
    expect(exposed.summaryText.value).toBe('经分')

    exposed.clearAll()
    expect(emitted.at(-1)).toEqual([])
  })

  it('adds custom keyword on Enter without removing existing item and supports remoteSearch', async () => {
    vi.useFakeTimers()
    const remoteSearch = vi.fn().mockResolvedValue(['广东省', '广西壮族自治区'])
    const { props, emitted, exposed, scope } = mountChipSetup({
      modelValue: ['北京市'],
      label: '省份',
      options: ['集团', '河北省'],
      remoteSearch,
    })
    scopes.push(() => scope.stop())

    expect(exposed.displayOptions.value[0]).toBe('北京市')

    // 回车直接添加自定义关键词，重复输入同一值不会误删
    exposed.keyword.value = ' 上海市 '
    exposed.onEnterKeyword()
    expect(emitted.at(-1)).toEqual(['北京市', '上海市'])
    expect(exposed.keyword.value).toBe('')

    exposed.keyword.value = '上海市'
    exposed.onEnterKeyword()
    expect(props.modelValue).toEqual(['北京市', '上海市'])

    // 触发防抖 remoteSearch
    exposed.open.value = true
    exposed.keyword.value = '广'
    await nextTick()
    expect(remoteSearch).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(250)
    await nextTick()
    expect(remoteSearch).toHaveBeenCalledOnce()
    expect(remoteSearch).toHaveBeenCalledWith('广')
    expect(exposed.displayOptions.value).toEqual(['北京市', '上海市', '广东省', '广西壮族自治区'])

    // 关闭面板清空搜索关键词与远端临时结果
    exposed.open.value = false
    await nextTick()
    expect(exposed.keyword.value).toBe('')
  })
})
