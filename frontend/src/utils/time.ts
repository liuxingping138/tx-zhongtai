const BEIJING = 'Asia/Shanghai'

/** datetimerange 日期范围选择器默认起止时间：避免选同一天时起止均为 00:00:00 查出 0 条。 */
export const DEFAULT_RANGE_TIME: [Date, Date] = [
  new Date(2000, 1, 1, 0, 0, 0),
  new Date(2000, 1, 1, 23, 59, 59),
]

export function beijingDate(date: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: BEIJING,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

export function localCalendarYmd(day: Date): string {
  const year = day.getFullYear()
  const month = String(day.getMonth() + 1).padStart(2, '0')
  const date = String(day.getDate()).padStart(2, '0')
  return `${year}-${month}-${date}`
}

export function localCalendarDate(ymd: string): Date {
  const parts = ymd.split('-')
  return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]))
}

export function isFutureBeijingDate(day: Date, now: Date = new Date()): boolean {
  return localCalendarYmd(day) > beijingDate(now)
}

export function toBeijingIso(value: string | null | undefined): string {
  if (!value) {
    return ''
  }
  if (/[+-]\d{2}:\d{2}$/.test(value) || value.endsWith('Z')) {
    return value
  }
  return `${value}+08:00`
}

export function formatTime(value: string | null | undefined): string {
  if (!value) {
    return '-'
  }
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)) {
    return value
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value.replace('T', ' ').replace(/\.\d+.*$/, '').replace(/([+-]\d{2}:\d{2}|Z)$/i, '').trim()
  }
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: BEIJING,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const pick = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value ?? ''
  return `${pick('year')}-${pick('month')}-${pick('day')} ${pick('hour')}:${pick('minute')}:${pick('second')}`
}
