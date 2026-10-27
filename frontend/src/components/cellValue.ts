import { formatTime } from '@/utils/time'
import type { DataColumn } from './dataColumns'

// 单元格只展示标量；对象和数组不应该出现在业务列里，显示为空而不是「[object Object]」。
function scalarText(raw: unknown): string {
  return typeof raw === 'string' || typeof raw === 'number' || typeof raw === 'boolean' ? String(raw) : ''
}

/** 记录里某个字段的原始文字，没有值时是空串。 */
export function fieldValue(row: object, key: string): string {
  return scalarText((row as Record<string, unknown>)[key])
}

/** 按列定义展示的文字：时间列转北京时间，空值显示「—」。 */
export function fieldText(row: object, col: DataColumn): string {
  const value = fieldValue(row, col.prop)
  if (!value) return '—'
  return col.time ? formatTime(value) : value
}

/** 链接列的地址，只放行 http / https；没写协议的按 https 补上。 */
export function fieldLink(row: object, col: DataColumn): string | undefined {
  const value = fieldValue(row, col.prop).trim()
  if (!value) return undefined
  try {
    const url = new URL(/^https?:\/\//i.test(value) ? value : `https://${value}`)
    return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined
  } catch {
    return undefined
  }
}
