/** 模板走到哪一步：列表的「上线状态」「样本试跑」两列和编辑页顶部的流程条共用这里的判断。 */
import type { BatchRun, PromptTemplate, SampleSummary } from '@/api/ai'
import { isActive } from '../shared/aiText'

export type ReleaseKind = 'offline' | 'changed' | 'online'
export type SampleKind = 'nosample' | 'none' | 'running' | 'stale' | 'stopped' | 'failed' | 'passed'

export interface StateText<K> { kind: K; text: string; detail: string }

export function releaseState(template: Pick<PromptTemplate, 'release'>): StateText<ReleaseKind> {
  const release = template.release
  if (!release) return { kind: 'offline', text: '未上线', detail: '' }
  const by = `${release.released_by_name} · ${release.released_at}`
  // 直接写出改了什么：列表和流程条一眼就知道是改了提示词还是换了码表，逐行对比在「看改动」里。
  if (release.unreleased_changes.length) {
    return { kind: 'changed', text: `第 ${release.release_no} 版在线，草稿改了${release.unreleased_changes.join('、')}`, detail: by }
  }
  return { kind: 'online', text: `第 ${release.release_no} 版已上线`, detail: by }
}

export function sampleState(template: Pick<PromptTemplate, 'sample' | 'excel_name'>): StateText<SampleKind> {
  const sample = template.sample
  if (!sample) {
    return template.excel_name
      ? { kind: 'none', text: '还没试跑', detail: '' }
      : { kind: 'nosample', text: '还没有测试样本', detail: '' }
  }
  const when = `${sample.created_by_name} · ${sample.created_at}`
  if (isActive(sample.status)) return { kind: 'running', text: `试跑中 ${sample.done_count}/${sample.total_count}`, detail: when }
  if (!sample.current) return { kind: 'stale', text: '草稿改过，需要重新试跑', detail: when }
  if (sample.failed_count) {
    const format = sample.format_failed_count ? `（格式不对 ${sample.format_failed_count}）` : ''
    return { kind: 'failed', text: `${sample.total_count} 条里 ${sample.failed_count} 条失败${format}`, detail: when }
  }
  if (sample.status !== 'done') return { kind: 'stopped', text: `没跑完（${sample.done_count}/${sample.total_count}）`, detail: when }
  // 只说明每条都解析出了字段，内容对不对还要人看。
  return { kind: 'passed', text: `${sample.total_count} 条全部解析成功`, detail: when }
}

export type StepKey = 'write' | 'test' | 'release'
/** done 完成；warn 完成但有问题；current 下一步该做的；todo 还轮不到 */
export type StepTone = 'done' | 'warn' | 'current' | 'todo'
export interface FlowStep { key: StepKey; title: string; tone: StepTone; text: string }

/** optional：没做完也不算「下一步」，照实写状态、不高亮、不催 */
interface StepState { text: string; finished: boolean; warn: boolean; optional?: boolean }

function writeStep(template: PromptTemplate | null, dirty: boolean): StepState {
  if (!template) return { text: '写好提示词后保存', finished: false, warn: false }
  if (dirty) return { text: '有未保存的修改', finished: false, warn: false }
  // 先传样本、选码表时模板就存下了，提示词可能还空着。
  if (!template.content.trim()) return { text: '还没写提示词', finished: false, warn: false }
  return { text: `已保存 · ${template.updated_by_name} ${template.updated_at}`, finished: true, warn: false }
}

function testStep(template: PromptTemplate | null): StepState {
  if (!template) return { text: '保存后用测试样本试跑', finished: false, warn: false }
  const sample = sampleState(template)
  const finished = sample.kind === 'passed' || sample.kind === 'failed'
  // 状态只看真实的试跑结果，和列表、上线检查说法一致。已上线且草稿没再改时，线上那一版已经在跑，
  // 没试跑也不把它当成下一步去催；但不能画成完成，那会让人以为测过了。
  const release = template.release
  const optional = Boolean(release && !release.unreleased_changes.length)
  return { text: sample.text, finished, warn: sample.kind === 'failed', optional }
}

function releaseStep(template: PromptTemplate | null, canRelease: boolean): StepState {
  const release = template ? releaseState(template) : null
  if (!release || release.kind === 'offline') {
    return { text: `未上线，${canRelease ? '确认无误后上线' : '确认无误后请管理员上线'}`, finished: false, warn: false }
  }
  return { text: release.text, finished: release.kind === 'online', warn: false }
}

/** 业务人员写好、用样本试跑没问题，管理员上线：三步里第一个没完成的就是「下一步」。 */
export function flowSteps(template: PromptTemplate | null, dirty: boolean, canRelease: boolean): FlowStep[] {
  const raw = [
    { key: 'write' as const, title: '写提示词', ...writeStep(template, dirty) },
    { key: 'test' as const, title: '样本试跑', ...testStep(template) },
    { key: 'release' as const, title: '上线', ...releaseStep(template, canRelease) },
  ]
  let next = false
  return raw.map(({ key, title, text, finished, warn, optional }) => {
    if (finished) return { key, title, text, tone: warn ? 'warn' : 'done' }
    if (optional) return { key, title, text, tone: 'todo' }
    const tone: StepTone = next ? 'todo' : 'current'
    next = true
    return { key, title, text, tone }
  })
}

export interface StepActionContext {
  canEdit: boolean
  canRelease: boolean
  /** 右栏已经在「样本试跑」上：不再给「去试跑」 */
  sampleOpen: boolean
}

/** 流程条上的按钮：试跑那一步是下一步时给「去试跑」；上线那一步按身份和状态给「上线第 N 版」「看改动」「上线管理」「查看上线内容」。 */
export function stepActions(template: PromptTemplate | null, steps: FlowStep[], context: StepActionContext): Partial<Record<StepKey, string>> {
  if (!template) return {}
  const toneOf = (key: StepKey) => steps.find(step => step.key === key)?.tone
  const changed = Boolean(template.release?.unreleased_changes.length)
  if (!context.canEdit) return readOnlyActions(template, toneOf('release') === 'current', changed, context.canRelease)
  const actions: Partial<Record<StepKey, string>> = {}
  const testTone = toneOf('test')
  if ((testTone === 'current' || testTone === 'warn') && !context.sampleOpen) actions.test = '去试跑'
  const label = releaseAction(template, toneOf('release') === 'current', changed, context.canRelease)
  if (label) actions.release = label
  return actions
}

/**
 * 只能看的模板：不引导去试跑。能上线的管理员（上线只要这类模板的查看档）照样给上线入口，
 * 原来直接返回，第一次上线的模板流程条写着「确认无误后上线」却没有按钮；其他人只给看。
 */
function readOnlyActions(template: PromptTemplate, isNext: boolean, changed: boolean, canRelease: boolean): Partial<Record<StepKey, string>> {
  if (canRelease) {
    const label = releaseAction(template, isNext, changed, true)
    return label ? { release: label } : {}
  }
  return template.release ? { release: changed ? '看改动' : '查看上线内容' } : {}
}

function releaseAction(template: PromptTemplate, isNext: boolean, changed: boolean, canRelease: boolean): string {
  // 业务人员不能上线：有改动就「看改动」，知道这次要请管理员上线什么。
  if (!canRelease) return changed ? '看改动' : isNext || template.release ? '查看上线内容' : ''
  // 版本号只增不减：线上那一版就是最新的；下线后不知道下一个号，抽屉里按上线记录写准。
  if (isNext) return template.release ? `上线第 ${template.release.release_no + 1} 版` : '上线'
  // 不是下一步时（比如要先重新试跑）：有没上线的改动叫「看改动」，逐行对比在抽屉里；没有改动时看线上版本、上线记录，在里面下线。
  if (changed) return '看改动'
  return template.release ? '上线管理' : ''
}

/** 样本试跑的任务换成模板上的摘要：试跑开始、进行中、结束时不用重新拉整张模板列表。 */
type DraftStamp = Pick<PromptTemplate, 'content' | 'output_fields' | 'model_id' | 'updated_at'>

/**
 * 这次试跑跑的是不是模板现在的草稿：按试跑时记下的草稿保存时间比（和后端 prompts.sample_current 一致）。
 * 换了码表、重传码表文件、换了测试样本也会改保存时间，只比提示词、字段、模型会漏掉；早期试跑没记时间，退回按内容比。
 */
export function sampleCurrent(run: Pick<BatchRun, 'draft_saved_at' | 'prompt_content' | 'output_fields' | 'model_id'>, template: DraftStamp): boolean {
  if (run.draft_saved_at) return run.draft_saved_at === template.updated_at
  return run.prompt_content === template.content && run.output_fields === template.output_fields
    && (!template.model_id || run.model_id === template.model_id)
}

export function sampleFromRun(run: BatchRun, template: DraftStamp): SampleSummary {
  return {
    id: run.id,
    status: run.status,
    total_count: run.total_count,
    done_count: run.done_count,
    failed_count: run.failed_count,
    format_failed_count: run.format_failed_count,
    cost: run.inference_cost + run.search_cost,
    thinking: run.thinking,
    created_at: run.created_at,
    created_by_name: run.created_by_name,
    current: sampleCurrent(run, template),
  }
}

/** 试跑开始、结束后把模板上的「最近一次试跑」换成这一次；没变化就原样返回，页面不用重画。 */
export function withSample(template: PromptTemplate, run: BatchRun): PromptTemplate {
  const sample = sampleFromRun(run, template)
  return JSON.stringify(sample) === JSON.stringify(template.sample) ? template : { ...template, sample }
}
