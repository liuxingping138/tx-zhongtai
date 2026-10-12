import { describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive, ref } from 'vue'
import type { FormInstance } from 'element-plus'

class FakeElement {
  constructor(readonly invalid?: { focus: () => void; scrollIntoView: () => void }) {}
  querySelector() { return this.invalid ?? null }
}
vi.stubGlobal('HTMLElement', FakeElement)

import { useFieldValidation } from './useFieldValidation'

function setup(root?: FakeElement) {
  const values = reactive({ name: '', code: '' })
  const form = ref({ $el: root } as unknown as FormInstance)
  const validation = effectScope().run(() => useFieldValidation(values, form))!
  return { values, validation }
}

describe('useFieldValidation', () => {
  it('只记录有内容的错误，全部为空时通过', async () => {
    const { validation } = setup()
    expect(await validation.validate({ name: '', code: '' })).toBe(true)
    expect(await validation.validate({ name: '请填写名称', code: '' })).toBe(false)
    expect({ ...validation.errors }).toEqual({ name: '请填写名称' })
  })

  it('再次校验先清掉上一次的错误', async () => {
    const { validation } = setup()
    await validation.validate({ name: '请填写名称' })
    await validation.validate({ code: '编码重复' })
    expect({ ...validation.errors }).toEqual({ code: '编码重复' })
  })

  it('改了哪个字段就清掉哪个字段的错误', async () => {
    const { values, validation } = setup()
    await validation.validate({ name: '请填写名称', code: '编码重复' })
    values.name = '甲'
    await nextTick()
    expect({ ...validation.errors }).toEqual({ code: '编码重复' })
  })
  it('校验不过时把焦点放到第一个出错的字段', async () => {
    const invalid = { focus: vi.fn(), scrollIntoView: vi.fn() }
    const { validation } = setup(new FakeElement(invalid))
    await validation.validate({ name: '请填写名称' })
    expect(invalid.focus).toHaveBeenCalled()
    expect(invalid.scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' })
  })
})
