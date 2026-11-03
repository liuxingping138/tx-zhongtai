/**
 * 没设输出字段时的提醒：系统只按「输出字段」从回答里取值，一个没填，结果 Excel 里就没有 AI 回答的那几列，
 * 样本试跑也不检查格式（显示全部成功）。提示词里写了返回格式的，顺带把里面的字段名找出来，告诉人该填哪几个。
 * 只提醒、不拦（2026-11-03：招投标「项目筛选」模板没填输出字段，结果表里看不到判断）。
 */
export function missingFieldsWarning(content: string, fields: readonly string[]): string {
  if (fields.length) return ''
  const keys = [...new Set([...content.matchAll(/"([^"\n]{1,40})"\s*[:：]/g)].map(match => match[1]!.trim()).filter(Boolean))]
  const lead = '没设输出字段：结果 Excel 里不会有 AI 回答的那几列'
  return keys.length
    ? `${lead}。提示词里要求返回「${keys.join('、')}」，把这些名字一字不差填进「输出字段」`
    : `${lead}。把要从回答里取的字段名填进「输出字段」`
}
