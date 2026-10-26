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
  if (release.unreleased_changes.length) {
    return { kind: 'changed', text: `第 ${release.release_no} 版在线，有改动未上线`, detail: `草稿改了${release.unreleased_changes.join('、')}` }
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
  return { kind: 'passed', text: `${sample.total_count} 条全部成功`, detail: when }
}

export type StepKey = 'write' | 'test' | 'release'
/** done 完成；warn 完成但有问题；current 下一步该做的；todo 还轮不到 */
export type StepTone = 'done' | 'warn' | 'current' | 'todo'
export interface FlowStep { key: StepKey; title: string; tone: StepTone; text: string }

interface StepState { text: string; finished: boolean; warn: boolean }

function writeStep(template: PromptTemplate | null, dirty: boolean): StepState {
  if (!template) return { text: '写好提示词后保存', finished: false, warn: false }
  if (dirty) return { text: '有未保存的修改', finished: false, warn: false }
  return { text: `已保存 · ${template.updated_by_name} ${template.updated_at}`, finished: true, warn: false }
}

function testStep(template: PromptTemplate | null): StepState {
  if (!template) return { text: '保存后用测试样本试跑', finished: false, warn: false }
  const sample = sampleState(template)
  const release = template.release
  // 已上线、草稿也没再改：线上那一版已经在跑，不用为它再去试跑；有试跑结果时照常显示结果。
  if (release && !release.unreleased_changes.length && !['passed', 'failed', 'running'].includes(sample.kind)) {
    return { text: `和线上第 ${release.release_no} 版一致`, finished: true, warn: false }
  }
  return { text: sample.text, finished: sample.kind === 'passed' || sample.kind === 'failed', warn: sample.kind === 'failed' }
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
  return raw.map(({ key, title, text, finished, warn }) => {
    if (finished) return { key, title, text, tone: warn ? 'warn' : 'done' }
    const tone: StepTone = next ? 'todo' : 'current'
    next = true
    return { key, title, text, tone }
  })
}

/** 样本试跑的任务换成模板上的摘要：试跑开始、进行中、结束时不用重新拉整张模板列表。 */
export function sampleFromRun(run: BatchRun, template: Pick<PromptTemplate, 'content' | 'output_fields' | 'model_id'>): SampleSummary {
  return {
    id: run.id,
    status: run.status,
    total_count: run.total_count,
    done_count: run.done_count,
    failed_count: run.failed_count,
    format_failed_count: run.format_failed_count,
    created_at: run.created_at,
    created_by_name: run.created_by_name,
    current: run.prompt_content === template.content && run.output_fields === template.output_fields
      && (!template.model_id || run.model_id === template.model_id),
  }
}
