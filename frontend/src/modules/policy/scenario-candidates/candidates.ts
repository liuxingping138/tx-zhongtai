import type { CandidateDetail, CandidateItem, CandidateSummary } from '@/api/scenarioCandidates'
import type { ScenarioPath } from '@/api/codebook'

export const RESOURCE = 'policy.scenario_candidates'
/** 列表的筛选字段：审核页靠它从地址栏带上筛选，翻上一个、下一个。 */
export const FILTER_KEYS = ['status', 'keyword', 'industry_l1', 'level_label', 'similar_level', 'min_policies'] as const
export const STATUSES = ['待审', '已采纳', '已合并', '已驳回'] as const
export const PENDING = '待审'
export const KIND_NEW = '新场景'
export const REJECT_REASONS = ['不是信息化场景', '太细，属于已有场景的一部分', '说法不对', '其他']

export type Suggestion = 'merge' | 'adopt' | null
export type DecisionMode = 'adopt' | 'merge' | 'reject'

/**
 * 审核页三种处理里给哪一种标「系统建议」。只是提示，人照样可以选别的。
 * - 码表里有字面高度相似的已有场景：多半是同一个场景换了说法，建议合并
 * - 只是把码表里已有的场景挂到一个新行业：建议采纳
 * - 没有相似的、而且不止一两条政策这么说：建议采纳
 * - 其余（只有一两条政策提、或相似度一般）不标，交给人判断
 */
export const ADOPT_MIN_POLICIES = 3
export const AI_SAME = '同一个场景'
export const AI_UNDER = '归到已有场景下'
export const AI_NEW = '新场景'
type SuggestFields = 'kind' | 'similar_level' | 'policy_count' | 'ai_verdict' | 'ai_target'
export function suggest(candidate: Pick<CandidateItem, SuggestFields>): Suggestion {
  // AI 看过的按 AI 的判断：它对照了码表里整个行业的场景，比只看名称字面靠得住
  if (candidate.ai_verdict === AI_SAME || candidate.ai_verdict === AI_UNDER) return candidate.ai_target ? 'merge' : null
  if (candidate.ai_verdict === AI_NEW) return 'adopt'
  if (candidate.similar_level === '高') return 'merge'
  if (candidate.kind !== KIND_NEW) return 'adopt'
  if (candidate.similar_level !== '中' && candidate.policy_count >= ADOPT_MIN_POLICIES) return 'adopt'
  return null
}

export function pathText(names: readonly string[]): string {
  return names.filter(Boolean).join(' › ')
}

/** 候选自己的场景路径，新的那一级单独拿出来，页面上标「新」。 */
export function splitPath(candidate: Pick<CandidateItem, 'scenario_l1' | 'scenario_l2' | 'scenario_l3' | 'new_level' | 'kind'>): { known: string[]; added: string } {
  const names = [candidate.scenario_l1, candidate.scenario_l2, candidate.scenario_l3].filter(Boolean)
  if (candidate.kind !== KIND_NEW) return { known: names, added: '' }
  return { known: names.slice(0, candidate.new_level - 1), added: names[candidate.new_level - 1] ?? '' }
}

/** 已经决定过的候选，结果写成一句话。 */
export function decisionText(candidate: CandidateItem): string {
  const by = candidate.decided_by_name ? `，${candidate.decided_by_name} ${candidate.decided_at}` : ''
  if (candidate.status === '已采纳') {
    return `已采纳进行业场景码表${candidate.adopted_name ? `，名称改为「${candidate.adopted_name}」` : ''}${by}`
  }
  if (candidate.status === '已合并') return `已合并到「${candidate.target}」${by}`
  if (candidate.status === '已驳回') return `已驳回：${candidate.reject_reason}${candidate.note ? `（${candidate.note}）` : ''}${by}`
  return ''
}

/** 列表上方的一句话结论。 */
export function summaryText(summary: CandidateSummary | null): string {
  if (!summary) return ''
  const pending = summary.by_status[PENDING] ?? 0
  if (!pending) return '没有待审的新增场景。'
  const parts = [`待审 ${pending.toLocaleString()} 个新增场景，涉及 ${summary.pending_rows.toLocaleString()} 行政策解读`]
  if (summary.pending_similar) parts.push(`其中 ${summary.pending_similar.toLocaleString()} 个和码表已有场景高度相似`)
  if (summary.new_today) parts.push(`今天新出现 ${summary.new_today.toLocaleString()} 个`)
  return `${parts.join('；')}。`
}

/** 码表路径（选择器选中的那一条）的场景部分，合并、改行用。 */
export function scenarioNames(path: ScenarioPath): string[] {
  return [path.scenario_l1_name, path.scenario_l2_name, path.scenario_l3_name]
}

export function pathLabel(path: ScenarioPath): string {
  const industry = [path.industry_l1, path.industry_l2, path.industry_l3].filter(Boolean).join('/')
  return `${pathText(scenarioNames(path))}（${industry}）`
}

/** 相似程度给业务人员看的说法：后端存高 / 中 / 无。 */
export const SIMILAR_LABELS: Record<string, string> = { 高: '很像', 中: '有点像', 无: '没有' }
export function similarLabel(level: string): string {
  return SIMILAR_LABELS[level] ?? (level || '还没算')
}

const LEVEL_NAMES = ['', '一级', '二级', '三级']
export function levelName(level: number): string {
  return LEVEL_NAMES[level] ?? ''
}

export interface PositionPart {
  name: string
  /** 一级、二级、三级 */
  level: string
  /** 码表里已有的、这次新增的 */
  added: boolean
}

/**
 * 这个场景在码表里的完整位置，逐级标出哪一级码表已有、哪一级是新增的。
 * 新增那一级下面 AI 还写了下级的，一并列出（取行数最多的那个，其余写「等 N 个」）。
 */
export function positionParts(candidate: Pick<CandidateDetail, 'kind' | 'new_level' | 'scenario_l1' | 'scenario_l2' | 'scenario_l3' | 'children'>): PositionPart[] {
  const names = [candidate.scenario_l1, candidate.scenario_l2, candidate.scenario_l3].filter(Boolean)
  const isNew = candidate.kind === KIND_NEW
  const parts = names.map((name, index) => ({ name, level: levelName(index + 1), added: isNew && index + 1 >= candidate.new_level }))
  const child = candidate.children[0]
  if (isNew && child && names.length < 3) {
    const more = candidate.children.length > 1 ? ` 等 ${candidate.children.length} 个` : ''
    parts.push({ name: `${child.path.split(' › ')[0] ?? child.path}${more}`, level: levelName(names.length + 1), added: true })
  }
  return parts
}

/** 合并时预选的目标：AI 说的、码表里对得上的那个；AI 没看过时用名称很像的那个。 */
export function mergeTargetOf(candidate: Pick<CandidateItem, 'ai_target'>, similar: { path: string[]; level: string }[]): string[] | null {
  if (candidate.ai_target) return candidate.ai_target.split(' > ')
  const best = similar[0]
  return best?.level === '高' ? best.path : null
}

/** 系统建议那张卡片上的一句话：为什么建议这么做。 */
export function suggestionText(candidate: Pick<CandidateItem, 'ai_verdict' | 'ai_similar'>, suggestion: Suggestion): string {
  if (!suggestion) return ''
  if (candidate.ai_verdict === AI_SAME) return `AI 判断：和「${candidate.ai_similar}」是同一个场景`
  if (candidate.ai_verdict === AI_UNDER) return `AI 判断：太细，应归到「${candidate.ai_similar}」`
  if (candidate.ai_verdict === AI_NEW) return 'AI 判断：码表里没有同样的场景'
  return suggestion === 'merge' ? '码表里有名称很像的' : '没有相似的，且不止一两条政策这么说'
}

/** AI 找相似的结果写成一句话；还没让 AI 看过的说明怎么才会有。 */
export function aiText(candidate: Pick<CandidateItem, 'ai_verdict' | 'ai_similar' | 'ai_reason' | 'ai_checked_at'>): string {
  if (!candidate.ai_verdict) return 'AI 还没看过：任务调度里的「新增场景找相似」跑过一批后才有'
  if (candidate.ai_verdict === '判断失败') return `AI 没判断出来：${candidate.ai_reason}`
  const similar = candidate.ai_similar ? `，最像的是「${candidate.ai_similar}」` : ''
  const reason = candidate.ai_reason ? `。理由：${candidate.ai_reason}` : ''
  return `AI 判断：${candidate.ai_verdict}${similar}${reason}`
}
