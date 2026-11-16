/** 政策类模板放进各打标任务前的检查。规则和政策服务的 aitag.domain.contract 一致：页面上按草稿实时提示，保存任务设置时后端再拦一次。 */
import type { ContractTask, TemplateCheck } from '@/api/aiTagging'
import { CODE_TABLE_FIELD } from '../shared/aiText'

const BODY = '政策正文'
const SCENES = '行业场景'
const SCENARIO_PATHS = '同行业已有场景'
const FIELD_ALIASES: Record<string, string[]> = {
  政策类型名称: ['政策类型名称', '政策类型'],
}

function hasField(fields: string[], required: string): boolean {
  const aliases = FIELD_ALIASES[required] ?? [required]
  return aliases.some(alias => fields.includes(alias))
}

const quoted = (names: string[]) => names.map(name => `@【${name}】`).join('、')

export function checkTemplate(task: ContractTask, variables: string[], fields: string[], systemCode: boolean): TemplateCheck {
  const errors: string[] = []
  const unknown = [...new Set(variables)].filter(name => !task.columns.includes(name) && name !== CODE_TABLE_FIELD)
  if (unknown.length) errors.push(`用了这个任务不提供的列：${quoted(unknown)}。能用的列：${quoted(task.columns)}`)
  const missing = task.required_fields.filter(name => !hasField(fields, name))
  if (missing.length) errors.push(`输出字段缺少：${missing.join('、')}，结果写不回表`)
  // 顺序、说法和政策服务 aitag.domain.contract 一致。
  const warnings = [
    ...emptyFieldWarnings(task, fields),
    ...bodyWarnings(task, variables),
    ...scenarioWarnings(task, variables),
    ...opportunityWarnings(task, variables, fields),
    ...codeWarnings(variables, systemCode),
  ]
  return { errors, warnings }
}

function bodyWarnings(task: ContractTask, variables: string[]): string[] {
  if (!task.columns.includes(BODY) || variables.includes(BODY)) return []
  return [`没有用 @【${BODY}】，模型只看得到标题，判断会不准`]
}

/** 新增场景找相似：看不到码表清单就找不出相似的。 */
function scenarioWarnings(task: ContractTask, variables: string[]): string[] {
  if (task.code !== 'scenario' || variables.includes(SCENARIO_PATHS)) return []
  return [`没有用 @【${SCENARIO_PATHS}】，模型看不到码表里这个行业下有哪些场景，找不出相似的`]
}

function codeWarnings(variables: string[], systemCode: boolean): string[] {
  if (!variables.includes(CODE_TABLE_FIELD) || systemCode) return []
  return ['码表用的是上传的文件，定时任务按上线时冻结的那份跑；要和系统码表口径一致，请改选系统码表']
}

function emptyFieldWarnings(task: ContractTask, fields: string[]): string[] {
  const empty = task.optional_fields.filter(group => !group.some(name => fields.includes(name))).map(group => group[0] ?? '')
  if (!empty.length) return []
  const names = empty.slice(0, 4).join('、') + (empty.length > 4 ? `等 ${empty.length} 个字段` : '')
  return [`没有输出${names}，写回时这些列会空着`]
}

/** 市场机会这一步特有的提醒。 */
function opportunityWarnings(task: ContractTask, variables: string[], fields: string[]): string[] {
  if (task.code !== 'opportunity') return []
  const warnings: string[] = []
  if (!fields.some(name => name === '行业' || name === '一级行业')) {
    warnings.push('没有输出「行业」「场景」：一条政策有几条市场机会时，分不清各是哪条解读行的')
  }
  if (!variables.includes(SCENES)) {
    warnings.push(`没有用 @【${SCENES}】，模型不知道这条政策解读出了哪些行业场景，市场机会可能对不上解读行`)
  }
  return warnings
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
    skip: !task.required_fields.some(name => hasField(fields, name)),
    required: task.required_fields,
  }))
}

export interface FitSummary { level: 'ok' | 'warn'; text: string }

/** 上线确认里的一句话：能用于哪些任务；有问题、有提醒的把第一条写出来，免得以为能直接顶替正在用的模板。不适用的不提。 */
export function fitSummary(results: Pick<TaskFitResult, 'name' | 'check' | 'skip'>[]): FitSummary | null {
  const relevant = results.filter(item => !item.skip)
  if (!relevant.length) return null
  const parts = relevant.map(({ name, check }) => {
    if (check.errors.length) return `不能用于${name}：${check.errors[0]}`
    return check.warnings.length ? `可用于${name}，但${check.warnings[0]}` : `可用于${name}`
  })
  const clean = relevant.every(({ check }) => !check.errors.length && !check.warnings.length)
  return { level: clean ? 'ok' : 'warn', text: parts.join('；') }
}

/** 按输出字段猜模板是给哪个任务用的，取测试数据时默认选它；猜不出就是类型判断。 */
export function guessTask(tasks: ContractTask[], fields: string[]): ContractTask['code'] {
  const fit = [...tasks].reverse().find(task => task.required_fields.every(name => hasField(fields, name)))
  return fit?.code ?? 'type'
}
