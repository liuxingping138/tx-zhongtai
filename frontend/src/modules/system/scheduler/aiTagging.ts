/** 政策 AI 打标批次的状态文案和金额格式。 */

const STATUS: Record<string, [string, 'primary' | 'success' | 'danger' | 'info']> = {
  running: ['执行中', 'primary'],
  success: ['完成', 'success'],
  failed: ['失败', 'danger'],
}

export function runStatusText(status: string): string {
  return STATUS[status]?.[0] ?? status
}

export function runStatusType(status: string): 'primary' | 'success' | 'danger' | 'info' {
  return STATUS[status]?.[1] ?? 'info'
}

/** 费用到分；不足一分的小额（试跑几条）保留 4 位，免得显示成 ¥0.00。 */
export function formatYuan(value: string | number | null | undefined): string {
  const amount = Number(value ?? 0)
  if (!Number.isFinite(amount)) return '—'
  return `¥${amount !== 0 && Math.abs(amount) < 0.01 ? amount.toFixed(4) : amount.toFixed(2)}`
}
