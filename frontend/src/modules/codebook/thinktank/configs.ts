import type { ThinktankDictSlug } from '@/api/codebook'

export interface ThinktankDictConfig {
  slug: ThinktankDictSlug
  title: string
  resource: string
  fieldLabel: string
  hint: string
}

export const THINKTANK_DICT_SLUGS: readonly ThinktankDictSlug[] = [
  'file-types',
  'departments',
  'industries',
  'product-types',
  'provinces',
  'market-categories',
] as const

export const THINKTANK_DICT_CONFIGS: Record<ThinktankDictSlug, ThinktankDictConfig> = {
  'file-types': {
    slug: 'file-types',
    title: '文件类别码表',
    resource: 'codebook.thinktank_file_types',
    fieldLabel: '文件类别',
    hint: '维护智库资料库的文件类别枚举，供智库筛选与打标使用。',
  },
  departments: {
    slug: 'departments',
    title: '客户部门归属码表',
    resource: 'codebook.thinktank_departments',
    fieldLabel: '客户部门归属',
    hint: '维护智库使用的客户部门归属枚举，供智库各子库选用。',
  },
  industries: {
    slug: 'industries',
    title: '行业类别码表',
    resource: 'codebook.thinktank_industries',
    fieldLabel: '行业类别',
    hint: '维护智库使用的行业类别枚举，供智库筛选与打标使用。',
  },
  'product-types': {
    slug: 'product-types',
    title: '产品类别码表',
    resource: 'codebook.thinktank_product_types',
    fieldLabel: '产品类别',
    hint: '维护智库使用的产品类别枚举，供智库资料库选用。',
  },
  provinces: {
    slug: 'provinces',
    title: '省份码表',
    resource: 'codebook.thinktank_provinces',
    fieldLabel: '省份名称',
    hint: '维护智库专属省份码表（含集团及全国 31 省），智库所有省份字段统一引用本码表。',
  },
  'market-categories': {
    slug: 'market-categories',
    title: '市场类别码表',
    resource: 'codebook.thinktank_market_categories',
    fieldLabel: '市场类别',
    hint: '维护智库使用的市场类别枚举，供智库资料库选用。',
  },
}

const SLUG_SET: ReadonlySet<string> = new Set(THINKTANK_DICT_SLUGS)

export function isThinktankDictSlug(value: unknown): value is ThinktankDictSlug {
  return typeof value === 'string' && SLUG_SET.has(value)
}

export function resolveThinktankDictSlug(
  propSlug?: ThinktankDictSlug,
  metaSlug?: unknown,
): ThinktankDictSlug {
  if (isThinktankDictSlug(propSlug)) return propSlug
  if (isThinktankDictSlug(metaSlug)) return metaSlug
  return 'file-types'
}

export function getThinktankDictConfig(slug: ThinktankDictSlug): ThinktankDictConfig {
  return THINKTANK_DICT_CONFIGS[slug]
}

export function thinktankDictBasePath(slug: ThinktankDictSlug): string {
  return `/codebook/thinktank/${slug}`
}

export function thinktankDictExportPath(slug: ThinktankDictSlug): string {
  return `/codebook/thinktank/${slug}/export`
}

export function thinktankDictExportFilename(config: ThinktankDictConfig): string {
  return `${config.title}.xlsx`
}

export function thinktankDictSkippedFilename(config: ThinktankDictConfig): string {
  return `${config.fieldLabel}-跳过明细.xlsx`
}
