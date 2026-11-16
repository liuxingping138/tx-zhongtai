import { http, request } from './http'

/** 政策 AI 打标的几个任务，在任务调度里各是一个任务（调度编码 = job_code）。scenario 是给新增场景找相似，enrich 是给采纳进码表的新场景补描述。 */
export type AiTaskCode = 'type' | 'interpret' | 'opportunity' | 'scenario' | 'enrich'

/** 正在跑的那一批：在做什么、AI 答到第几条（ai-service 暂时取不到时 done、total 为空） */
export interface AiTaggingCurrent {
  id: string
  stage: string
  stage_name: string
  started_at: string
  cost: string
  done: number | null
  total: number | null
}

/** 一个打标任务的设置和今天的花费。读取进度只有类型判断有：采集日期 + 该日已读到的正文ID。 */
export interface AiTask {
  code: AiTaskCode
  job_code: string
  name: string
  prompt_id: string
  batch_size: number
  content_max_chars: number
  daily_cost_limit: string
  cursor_date: string
  cursor_content_id: string
  /** 类型判断只读这几个省份的源政策，空为不限；其余任务为空 */
  provinces: string[]
  version: number
  updated_at: string
  updated_by_name: string
  spent_today: string
  spent_month: string
  current: AiTaggingCurrent | null
  /** 待办条数：类型判断是等着重新判断的，解读、市场机会是等着做的 */
  pending: number
}

/** 模板放进某个打标任务的检查结果：errors 必须改（写不回表），warnings 能跑但结果可能不理想。 */
export interface TemplateCheck {
  errors: string[]
  warnings: string[]
}

/** 可以给打标任务用的模板：政策类、已上线。checks 是放进三个任务各自的检查结果。 */
export interface OnlineTemplate {
  prompt_id: string
  title: string
  release_no: number
  released_at: string
  model_id: string
  output_fields: string[]
  code: string
  variables: string[]
  system_code: boolean
  checks: Record<AiTaskCode, TemplateCheck>
}

/** 打标任务给模板哪些列（@【列名】能引用的）、要模板输出哪些字段、现在用的哪个模板。 */
export interface ContractTask {
  code: AiTaskCode
  name: string
  columns: string[]
  required_fields: string[]
  /** 不输出也能写回、只是对应列空着的字段；同一列的几种写法放一组，第一种是提示里说的名字 */
  optional_fields: string[][]
  /** 任务设置里选的模板 ID，没选是空串 */
  prompt_id: string
}

/** 从数据库取的测试数据：和正式打标交给模板的一模一样。 */
export interface TaggingSamples {
  task: AiTaskCode
  file_name: string
  note: string
  headers: string[]
  rows: string[][]
}

export type AiTaskBody = Pick<AiTask, 'prompt_id' | 'batch_size' | 'content_max_chars' | 'daily_cost_limit' | 'cursor_date' | 'provinces' | 'version'>

const base = '/policy/ai-tagging'
export const listAiTasks = () => request<{ items: AiTask[] }>(http.get(`${base}/tasks`))
export const listAiTemplates = () => request<{ items: OnlineTemplate[]; error: string }>(http.get(`${base}/templates`))
/** 基础标签列表上勾选政策重新打标：放回某个任务的待办，下次执行那个任务时处理。 */
export interface RetagResult {
  step: AiTaskCode
  task: string
  queued: number
  skipped: { reason: string; count: number }[]
}
export const requestRetag = (ids: string[], step: AiTaskCode) => request<RetagResult>(http.post(`${base}/retag`, { ids, step }))
export const getTaggingContract = () => request<{ tasks: ContractTask[] }>(http.get(`${base}/contract`))
export const getTaggingSamples = (task: AiTaskCode, day: string, limit: number) =>
  request<TaggingSamples>(http.get(`${base}/samples`, { params: { task, limit, ...(task === 'type' ? { day } : {}) }, timeout: 120_000 }))
export type AiTaskUpdate = Omit<AiTask, 'spent_today' | 'spent_month' | 'current' | 'pending'>

export const updateAiTask = (code: AiTaskCode, body: AiTaskBody) =>
  request<AiTaskUpdate>(http.put(`${base}/tasks/${code}`, body))
