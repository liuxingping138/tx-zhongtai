import type { AiModel, PromptTemplate, RunVersion } from '@/api/ai'
import { CODE_TABLE_FIELD } from '../shared/aiText'
import { shortTime } from '../prompts/sampleView'

/**
 * 新建批量任务跑模板的哪一版：上线版本，或者已保存的草稿。定时任务只跑上线版本，批量任务两种都行，
 * 业务人员调好模板就能拿本地 Excel 跑，不用等管理员上线。规则和后端 batch_runs._spec 一致。
 */

/** 这一版要跑的内容：数据要有哪些列、用什么模型、输出哪些字段、哪份码表；problem 是跑不了的原因 */
export interface RunSpec {
  version: RunVersion
  /** 「第 3 版」或「当前草稿」 */
  label: string
  content: string
  columns: string[]
  fields: string[]
  modelName: string
  model: AiModel | undefined
  code: string
  problem: string
}

export interface VersionOption {
  value: RunVersion
  title: string
  detail: string
  /** 草稿的样本试跑有问题、没试跑过：提醒但不拦着 */
  warning: string
  disabled: boolean
}

const VARIABLE = /@【([^【】\n]+)】/g

/** 提示词引用的 Excel 列（去重、保持出现顺序），码表不算列。和后端 input_columns 同一套规则。 */
export function inputColumns(content: string): string[] {
  return [...new Set([...content.matchAll(VARIABLE)].map(match => (match[1] ?? '').trim()))].filter(name => name !== CODE_TABLE_FIELD)
}

/** 有上线版本时默认跑线上那一版，没上线就只能跑草稿。 */
export function defaultVersion(template: PromptTemplate | undefined): RunVersion {
  return template?.release ? 'release' : 'draft'
}

function sampleWarning(template: PromptTemplate): string {
  const sample = template.sample
  if (!sample) return '还没做过样本试跑，建议先在模板里试跑几条'
  if (!sample.current) return '最近一次样本试跑之后草稿又改过，建议再试跑一次'
  const problems = sample.failed_count
  return problems ? `样本试跑 ${sample.total_count} 条里 ${problems} 条有问题` : ''
}

export function versionOptions(template: PromptTemplate): VersionOption[] {
  const release = template.release
  const changed = release?.unreleased_changes.length ? `，比第 ${release.release_no} 版改了${release.unreleased_changes.join('、')}` : ''
  return [
    {
      value: 'release',
      title: release ? `线上第 ${release.release_no} 版` : '线上版本',
      detail: release ? `${shortTime(release.released_at)} ${release.released_by_name}上线，定时任务也用这一版` : '还没上线，管理员上线后才有',
      warning: '',
      disabled: !release,
    },
    {
      value: 'draft',
      title: '当前草稿',
      detail: `${shortTime(template.updated_at)} 保存${changed}`,
      warning: sampleWarning(template),
      disabled: false,
    },
  ]
}

function modelProblem(model: AiModel | undefined, name: string, draft: boolean): string {
  const where = draft ? '在模板里换一个模型并保存' : '在模板里换模型并重新上线'
  if (!model) return `「${name}」已停用，${where}`
  return model.available ? '' : `「${model.name}」的接口密钥还没配置，暂时不能跑`
}

export function runSpec(template: PromptTemplate | undefined, version: RunVersion, models: AiModel[]): RunSpec | null {
  if (!template) return null
  const release = template.release
  if (version === 'release' && release) {
    const model = models.find(item => item.id === release.model_id)
    return {
      version, label: `第 ${release.release_no} 版`, content: release.content, columns: release.variables, fields: release.fields,
      modelName: release.model_name, model, code: release.code,
      problem: modelProblem(model, release.model_name, false),
    }
  }
  const model = models.find(item => item.id === template.model_id)
  let problem = ''
  if (version === 'release') problem = '模板还没上线，选「当前草稿」跑，或请管理员先上线'
  else if (!template.content.trim()) problem = '草稿的提示词还是空的，先在模板里写好保存'
  else if (!template.model_id) problem = '草稿还没选模型，先在模板里选好模型并保存'
  else problem = modelProblem(model, template.model_name, true)
  return {
    version, label: '当前草稿', content: template.content, columns: inputColumns(template.content), fields: template.fields,
    modelName: template.model_name, model, code: template.code_table_name || template.code_name, problem,
  }
}
