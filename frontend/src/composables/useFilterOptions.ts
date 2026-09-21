import { reactive, ref } from 'vue'

import {
  fetchFilterOptions,
  searchFilterOptions,
  type FilterOptionSet,
  type FilterOptionsPayload,
} from '@/api/filterOptions'

const EMPTY: FilterOptionSet = { items: [], truncated: false }

export interface FilterSelectBinding {
  options: string[]
  /** 候选值过多时提供；FilterSelect 会在用户输入时调用它做服务端搜索。 */
  remoteSearch?: (keyword: string) => Promise<string[]>
}

/**
 * 列表页筛选项。
 *
 * 所有字段的候选值都来自后端。候选值少的字段整份取回，点开即见、输入时
 * 本地过滤，不产生额外请求；候选值多的字段只取回前一段打底，用户输入时
 * 按关键词走服务端搜索——这样既不会再有「排序靠后就搜不到」的值，
 * 也不必每次进页面都传近 1MB 的候选列表。
 */
export function useFilterOptions(path: string) {
  const sets = reactive<Record<string, FilterOptionSet>>({})
  const cityByProvince = ref<Record<string, string[]>>({})
  const loaded = ref(false)

  async function load(): Promise<void> {
    try {
      const payload: FilterOptionsPayload = await fetchFilterOptions(path)
      Object.assign(sets, payload.options ?? {})
      cityByProvince.value = payload.city_by_province ?? {}
      loaded.value = true
    } catch {
      /* 选项取不到不影响列表本身，筛选框退化为可自由输入。 */
    }
  }

  function get(field: string): FilterOptionSet {
    return sets[field] ?? EMPTY
  }

  /** 绑定到 FilterSelect：`v-bind="filters.bind('site_name')"`。 */
  function bind(field: string): FilterSelectBinding {
    const set = get(field)
    if (!set.truncated) {
      return { options: set.items }
    }
    return {
      options: set.items,
      remoteSearch: async (keyword: string) => (await searchFilterOptions(path, field, keyword)).items,
    }
  }

  /**
   * 地市字段的特殊绑定：选了省份就用该省的完整地市列表（数量有限、且更准确），
   * 没选省份才回落到通用的预览 + 服务端搜索。
   */
  function bindCity(field: string, province: string): FilterSelectBinding {
    const scoped = province ? cityByProvince.value[province] : undefined
    return scoped ? { options: scoped } : bind(field)
  }

  return { load, bind, bindCity, get, cityByProvince, loaded }
}
