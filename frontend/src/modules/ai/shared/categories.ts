import type { TemplateCategory } from '@/api/ai'

/** 类型切换里的「全部」 */
export const ALL_CATEGORIES = ''

export function inCategory(category: string, filter: string): boolean {
  return filter === ALL_CATEGORIES || category === filter
}

/** 新模板的默认类型：正在看的类型能编辑就用它，否则用第一个能编辑的；一个都没有时为空，不能新建。 */
export function defaultCategory(editable: TemplateCategory[], filter: string): string {
  return editable.find(item => item.code === filter)?.code ?? editable[0]?.code ?? ''
}
