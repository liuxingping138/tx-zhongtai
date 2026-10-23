import { computed, ref, type Ref } from 'vue'

interface Clearable {
  clearSelection: () => void
}

/** 列表勾选：BusinessTable 传 selectable、`:ref="selection.bindTable"`、监听 selection-change 写 checked；批量操作完调 clear。 */
export function useTableSelection<T extends { id: string }>() {
  let table: Clearable | null = null
  const checked = ref([]) as Ref<T[]>
  const ids = computed(() => checked.value.map(item => item.id))

  /** 模板函数 ref：组件挂载时传入实例，卸载时传 null。 */
  function bindTable(instance: unknown): void {
    table = instance && typeof (instance as Clearable).clearSelection === 'function' ? (instance as Clearable) : null
  }

  function clear(): void {
    table?.clearSelection()
    checked.value = []
  }

  return { checked, ids, bindTable, clear }
}
