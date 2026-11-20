import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, h, reactive, type Component, type SetupContext } from 'vue'
import { renderToString } from 'vue/server-renderer'

vi.mock('vue', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue')>()
  return { ...actual, useSSRContext: () => ({ modules: new Set<string>() }) }
})

import FilterChipDate from './FilterChipDate.vue'
import FilterChipInput from './FilterChipInput.vue'

interface DateChipApi {
  open: { value: boolean }
  hasValue: { value: boolean }
  summaryText: { value: string }
  clearAll: () => void
  applyShortcut: (s: { text: string; value: () => [Date, Date] }) => void
  onPickerChange: (val: [string, string] | null) => void
}

interface InputChipApi {
  open: { value: boolean }
  draft: { value: string }
  hasValue: { value: boolean }
  summaryText: { value: string }
  applyDraft: () => void
  clearAll: () => void
}

function stubApp(comp: Component, props: Record<string, unknown>) {
  const app = createSSRApp(comp, props)
  const StubSlot: Component = {
    inheritAttrs: false,
    setup: (_p: unknown, { slots }: SetupContext) => () => h('div', [slots.reference?.(), slots.default?.()]),
  }
  const StubLeaf: Component = { inheritAttrs: false, render: () => h('span') }
  app.component('ElPopover', StubSlot)
  app.component('ElIcon', StubSlot)
  app.component('ElDatePicker', StubLeaf)
  app.component('ElInput', StubLeaf)
  app.component('ElButton', StubSlot)
  return renderToString(app)
}

const cleanups: Array<() => void> = []
afterEach(() => {
  while (cleanups.length) cleanups.pop()?.()
})

describe('FilterChipDate', () => {
  it('renders unselected and selected states and handles shortcut/clear', async () => {
    const emptyHtml = await stubApp(FilterChipDate as Component, { modelValue: null, label: '上线时间' })
    expect(emptyHtml).toContain('上线时间')
    expect(emptyHtml).not.toContain('is-active')

    const props = reactive<{ modelValue: [string, string] | null; label: string }>({
      modelValue: null,
      label: '上线时间',
    })
    const emitted: Array<[string, string] | null> = []
    let api!: DateChipApi
    const scope = effectScope()
    scope.run(() => {
      const setupFn = (FilterChipDate as { setup?: (p: unknown, c: unknown) => unknown }).setup
      setupFn?.(props, {
        emit: (_e: string, v: [string, string] | null) => {
          emitted.push(v)
          props.modelValue = v
        },
        expose: (v: DateChipApi) => { api = v },
        attrs: {},
        slots: {},
      })
    })
    cleanups.push(() => scope.stop())

    api.applyShortcut({
      text: '固定7天',
      value: () => [new Date(2025, 0, 2), new Date(2025, 0, 8)],
    })
    expect(emitted.at(-1)).toEqual(['2025-01-02', '2025-01-08'])
    expect(api.hasValue.value).toBe(true)
    expect(api.summaryText.value).toBe('2025-01-02 ~ 2025-01-08')

    api.clearAll()
    expect(emitted.at(-1)).toBeNull()
    expect(api.hasValue.value).toBe(false)

    const activeHtml = await stubApp(FilterChipDate as Component, {
      modelValue: ['2025-01-02', '2025-01-08'],
      label: '上线时间',
    })
    expect(activeHtml).toContain('is-active')
    expect(activeHtml).toContain('2025-01-02 ~ 2025-01-08')
  })
})

describe('FilterChipInput', () => {
  it('renders prefix summary and supports apply/clear', async () => {
    const props = reactive({ modelValue: '', label: '政策数', prefix: '≥ ' })
    const emitted: string[] = []
    let api!: InputChipApi
    const scope = effectScope()
    scope.run(() => {
      const setupFn = (FilterChipInput as { setup?: (p: unknown, c: unknown) => unknown }).setup
      setupFn?.(props, {
        emit: (_e: string, v: string) => {
          emitted.push(v)
          props.modelValue = v
        },
        expose: (v: InputChipApi) => { api = v },
        attrs: {},
        slots: {},
      })
    })
    cleanups.push(() => scope.stop())

    api.draft.value = ' 5 '
    api.applyDraft()
    expect(emitted.at(-1)).toBe('5')
    expect(api.hasValue.value).toBe(true)
    expect(api.summaryText.value).toBe('≥ 5')

    const activeHtml = await stubApp(FilterChipInput as Component, {
      modelValue: '5',
      label: '政策数',
      prefix: '≥ ',
    })
    expect(activeHtml).toContain('is-active')
    expect(activeHtml).toContain('≥ 5')

    api.clearAll()
    expect(emitted.at(-1)).toBe('')
    expect(api.hasValue.value).toBe(false)
  })
})
