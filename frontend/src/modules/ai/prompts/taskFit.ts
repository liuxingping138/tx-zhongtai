/** 政策类模板放进三个打标任务前的检查。规则和政策服务的 aitag.domain.contract 一致：页面上按草稿实时提示，保存任务设置时后端再拦一次。 */
import type { ContractTask, TemplateCheck } from '@/api/aiTagging'
import { CODE_TABLE_FIELD } from '../shared/aiText'

const BODY = '政策正文'
const SCENES = '行业场景'

const quoted = (names: string[]) => names.map(name => `@【${name}】`).join('、')

export function checkTemplate(task: ContractTask, variables: string[], fields: string[], systemCode: boolean): TemplateCheck {
  const errors: string[] = []
  const unknown = [...new Set(variables)].filter(name => !task.columns.includes(name) && name !== CODE_TABLE_FIELD)
  if (unknown.length) errors.push(`用了这个任务不提供的列：${quoted(unknown)}。能用的列：${quoted(task.columns)}`)
  const missing = task.required_fields.filter(name => !fields.includes(name))
  if (missing.length) errors.push(`输出字段缺少：${missing.join('、')}，结果写不回表`)
  const warnings: string[] = []
  if (!variables.includes(BODY)) warnings.push(`没有用 @【${BODY}】，模型只看得到标题，判断会不准`)
  if (task.code === 'opportunity' && !variables.includes(SCENES)) {
    warnings.push(`没有用 @【${SCENES}】，模型不知道这条政策解读出了哪些行业场景，市场机会可能对不上解读行`)
  }
  if (variables.includes(CODE_TABLE_FIELD) && !systemCode) {
    warnings.push('码表用的是上传的文件，定时任务按上线时冻结的那份跑；要和系统码表口径一致，请改选系统码表')
  }
  return { errors, warnings }
}

export type FitLevel = 'ok' | 'warn' | 'error' | 'skip'

export interface TaskFitResult {
  code: ContractTask['code']
  name: string
  check: TemplateCheck
  /** 输出字段里一个这个任务要的字段都没有：模板本来就不是给它用的，显示「不适用」，不标红 */
  skip: boolean
  required: string[]
}

export function fitLevel(item: Pick<TaskFitResult, 'check' | 'skip'>): FitLevel {
  if (item.skip) return 'skip'
  return item.check.errors.length ? 'error' : item.check.warnings.length ? 'warn' : 'ok'
}

/** 按草稿逐个任务检查。一个必需输出字段都没有的任务算「不适用」。 */
export function fitResults(tasks: ContractTask[], variables: string[], fields: string[], systemCode: boolean): TaskFitResult[] {
  return tasks.map(task => ({
    code: task.code,
    name: task.name,
    check: checkTemplate(task, variables, fields, systemCode),
    skip: !task.required_fields.some(name => fields.includes(name)),
    required: task.required_fields,
  }))
}

/** 上线确认里的一句话：能用于哪些任务、哪些想用但还有问题。不适用的不提。 */
export function fitSummary(results: Pick<TaskFitResult, 'name' | 'check' | 'skip'>[]): string {
  const usable = results.filter(item => !item.skip && !item.check.errors.length).map(item => item.name)
  const unusable = results.filter(item => !item.skip && item.check.errors.length).map(item => item.name)
  const parts = [usable.length ? `可用于${usable.join('、')}` : '', unusable.length ? `不能用于${unusable.join('、')}` : '']
  return parts.filter(Boolean).join('；')
}

/** 按输出字段猜模板是给哪个任务用的，取测试数据时默认选它；猜不出就是类型判断。 */
export function guessTask(tasks: ContractTask[], fields: string[]): ContractTask['code'] {
  const fit = [...tasks].reverse().find(task => task.required_fields.every(name => fields.includes(name)))
  return fit?.code ?? 'type'
}
