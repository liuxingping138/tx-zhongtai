import type { App, DirectiveBinding } from 'vue'

import { useAuthStore } from '@/stores/auth'
import { levelSatisfies, type GrantLevel } from './levels'

function apply(el: HTMLElement, binding: DirectiveBinding<string>) {
  const auth = useAuthStore()
  const raw = binding.value || ''
  const [resource, level] = raw.split(':')
  const required = (level as GrantLevel) || 'READ'
  const allowed = levelSatisfies(auth.resourceLevel(resource), required)
  el.style.display = allowed ? '' : 'none'
}

export function registerPermissionDirective(app: App): void {
  app.directive('perm', {
    mounted: apply,
    updated: apply,
  })
}
