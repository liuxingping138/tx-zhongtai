import { describe, expect, it, vi } from 'vitest'
import type { App, DirectiveBinding, ObjectDirective } from 'vue'

const levels = vi.hoisted(() => ({ value: new Map<string, string>() }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ resourceLevel: (code: string) => levels.value.get(code) ?? 'NONE' }),
}))

import { registerPermissionDirective } from './directive'

function directive(): ObjectDirective<HTMLElement, string> {
  let registered: ObjectDirective<HTMLElement, string> | undefined
  const app = { directive: (_: string, value: ObjectDirective<HTMLElement, string>) => { registered = value } }
  registerPermissionDirective(app as unknown as App)
  return registered!
}

function display(value: string): string {
  const el = { style: { display: '' } } as HTMLElement
  directive().mounted!(el, { value } as DirectiveBinding<string>, null!, null)
  return el.style.display
}

describe('v-perm', () => {
  it('不写档位时按查看判断', () => {
    levels.value = new Map([['policy.sources', 'READ']])
    expect(display('policy.sources')).toBe('')
    expect(display('policy.tags')).toBe('none')
  })

  it('档位不够就隐藏，高档包含低档', () => {
    levels.value = new Map([['policy.sources', 'EXPORT']])
    expect(display('policy.sources:EXPORT')).toBe('')
    expect(display('policy.sources:READ')).toBe('')
    expect(display('policy.sources:FULL')).toBe('none')
  })

  it('权限变化后更新时重新判断', () => {
    levels.value = new Map()
    const el = { style: { display: '' } } as HTMLElement
    const perm = directive()
    perm.mounted!(el, { value: 'system.users' } as DirectiveBinding<string>, null!, null)
    expect(el.style.display).toBe('none')
    levels.value = new Map([['system.users', 'FULL']])
    perm.updated!(el, { value: 'system.users' } as DirectiveBinding<string>, null!, null!)
    expect(el.style.display).toBe('')
  })
})
