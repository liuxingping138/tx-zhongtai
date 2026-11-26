/** 模板走到哪一步：列表的「上线状态」「样本试跑」两列和编辑页顶栏共用这里的判断。 */
import type { BatchRun, PromptTemplate, SampleSummary } from '@/api/ai'
import { isActive } from '../shared/aiText'

export type ReleaseKind = 'offline' | 'changed' | 'online'
export type SampleKind = 'nosample' | 'none' | 'running' | 'stale' | 'stopped' | 'failed' | 'passed'

export interface StateText<K> { kind: K; text: string; compact: string; detail: string }

export function releaseState(template: Pick<PromptTemplate, 'release'>): StateText<ReleaseKind> {
  const release = template.release
  if (!release) return { kind: 'offline', text: '未上线', compact: '未上线', detail: '' }
  const by = `${release.released_by_name} · ${release.released_at}`
  // 直接写出改了什么：列表和流程条一眼就知道是改了提示词还是换了码表，逐行对比在「看改动」里。
  if (release.unreleased_changes.length) {
    return {
      kind: 'changed',
      text: `第 ${release.release_no} 版在线，草稿改了${release.unreleased_changes.join('、')}`,
      compact: `第 ${release.release_no} 版 · 有改动`,
      detail: by,
    }
  }
  return { kind: 'online', text: `第 ${release.release_no} 版已上线`, compact: `第 ${release.release_no} 版已上线`, detail: by }
}

export function sampleState(template: Pick<PromptTemplate, 'sample' | 'excel_name'>): StateText<SampleKind> {
  const sample = template.sample
  if (!sample) {
    return template.excel_name
      ? { kind: 'none', text: '还没试跑', compact: '未试跑', detail: '' }
      : { kind: 'nosample', text: '还没有测试样本', compact: '无样本', detail: '' }
  }
  const when = `${sample.created_by_name} · ${sample.created_at}`
  if (isActive(sample.status)) {
    const label = `试跑中 ${sample.done_count}/${sample.total_count}`
    return { kind: 'running', text: label, compact: label, detail: when }
  }
  if (!sample.current) return { kind: 'stale', text: '草稿改过，需要重新试跑', compact: '待重跑 · 草稿已改', detail: when }
  if (sample.failed_count) {
    const format = sample.format_failed_count ? `（格式不对 ${sample.format_failed_count}）` : ''
    return {
      kind: 'failed',
      text: `${sample.total_count} 条里 ${sample.failed_count} 条失败${format}`,
      compact: `${sample.total_count} 条 · ${sample.failed_count} 异常`,
      detail: when,
    }
  }
  if (sample.status !== 'done') {
    return {
      kind: 'stopped',
      text: `没跑完（${sample.done_count}/${sample.total_count}）`,
      compact: `已中断 ${sample.done_count}/${sample.total_count}`,
      detail: when,
    }
  }
  // 只说明每条都解析出了字段，内容对不对还要人看。
  return {
    kind: 'passed',
    text: `${sample.total_count} 条全部解析成功`,
    compact: `${sample.total_count}/${sample.total_count} 解析通过`,
    detail: when,
  }
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

export interface ReleaseEntry {
  label: string
  /** primary：待审核改动（醒目主入口）；plain：首次发布上线；subtle：查看线上版或只读看改动 */
  emphasis: 'primary' | 'plain' | 'subtle'
}

function adminReleaseEntry(release: PromptTemplate['release'], changed: boolean, header: boolean): ReleaseEntry {
  if (!release) return { label: header ? '发布上线' : '上线', emphasis: 'plain' }
  if (changed) return { label: `发布 v${release.release_no + 1}`, emphasis: 'primary' }
  return { label: header ? '线上版本' : '版本', emphasis: 'subtle' }
}

/** 列表操作列与编辑页顶栏共用的上线抽屉入口：管理员始终可见明确的上线/发布按钮，不受试跑步骤遮蔽。 */
export function releaseEntry(
  template: Pick<PromptTemplate, 'release'> | null,
  canRelease: boolean,
  scene: 'header' | 'list' = 'header',
): ReleaseEntry | null {
  if (!template) return null
  const header = scene === 'header'
  const release = template.release
  const changed = Boolean(release?.unreleased_changes.length)
  if (canRelease) return adminReleaseEntry(release, changed, header)
  if (!release) return null
  return { label: changed ? (header ? '查看改动' : '改动') : header ? '线上版本' : '版本', emphasis: 'subtle' }
}

/** 试跑开始、结束后把模板上的「最近一次试跑」换成这一次；没变化就原样返回，页面不用重画。 */
export function withSample(template: PromptTemplate, run: BatchRun): PromptTemplate {
  const sample = sampleFromRun(run, template)
  return JSON.stringify(sample) === JSON.stringify(template.sample) ? template : { ...template, sample }
}
