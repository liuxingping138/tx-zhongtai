import type { CandidateContext, CandidateItem, CandidateSummary } from '@/api/scenarioCandidates'
import type { ScenarioPath } from '@/api/codebook'

export const RESOURCE = 'policy.scenario_candidates'
/** 列表的筛选字段：审核页靠它从地址栏带上筛选，翻上一个、下一个。 */
export const FILTER_KEYS = ['status', 'keyword', 'industry_l1', 'level_label', 'match', 'min_policies'] as const
export const STATUSES = ['待审', '已采纳', '已合并', '已驳回'] as const
export const PENDING = '待审'
export const KIND_NEW = '新场景'
export const REJECT_REASONS = ['不是信息化场景', '太细，属于已有场景的一部分', '说法不对', '其他']

export type Suggestion = 'merge' | 'adopt' | null
export type DecisionMode = 'adopt' | 'rename' | 'merge' | 'reject'

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
export const SIMILAR_LABELS: Record<string, string> = { 高: '名称很像', 中: '名称有点像', 无: '没有' }
export function similarLabel(level: string): string {
  return SIMILAR_LABELS[level] ?? (level || '还没算')
}

const LEVEL_NAMES = ['', '一级', '二级', '三级']
export function levelName(level: number): string {
  return LEVEL_NAMES[level] ?? ''
}

/** AI 和码表里的路径写成「一级 > 二级」，页面上统一用 › */
export function arrow(text: string): string {
  return text.split(' > ').filter(Boolean).join(' › ')
}

type Where = Pick<CandidateItem, 'kind' | 'new_level' | 'level_label' | 'parent' | 'industry' | 'main_industry'>

/** 「新二级」「新一级」「新关联」：几级一眼看清。 */
export function levelTag(candidate: Where): string {
  return candidate.kind === KIND_NEW ? `新${candidate.level_label}` : '新关联'
}

/** 审核页标题旁的一句：AI 新增的是第几级。 */
export function levelTitle(candidate: Where): string {
  return candidate.kind === KIND_NEW ? `AI 新增的${levelName(candidate.new_level)}场景` : '码表已有场景，新挂到这个行业'
}

/** 列表「挂在哪」一格。 */
export function whereText(candidate: Where): string {
  if (candidate.kind !== KIND_NEW) return `挂到 ${candidate.industry}`
  return candidate.parent ? `${candidate.main_industry} › ${candidate.parent} 下` : `${candidate.main_industry} · 新的一级场景`
}

/** 同级已有的几个场景，写成「A、B、C 等 12 个」。下级多的（业务成型的）排前面。 */
export function siblingsText(siblings: { name: string; children: number }[], shown = 3): string {
  const names = [...siblings].sort((a, b) => b.children - a.children).map(item => item.name)
  if (!names.length) return ''
  const more = names.length > shown ? ` 等 ${names.length} 个` : ''
  return `${names.slice(0, shown).join('、')}${more}`
}

export type MatchKind = 'ai' | 'high' | 'medium' | 'none'
export interface Match {
  kind: MatchKind
  label: string
  /** 像它的那个已有场景（路径，› 分隔） */
  name: string
  /** 补一句 AI 怎么看 */
  note: string
}

type MatchFields = 'ai_verdict' | 'ai_similar' | 'similar_level' | 'similar_name'

/**
 * 列表「码表里像它的」一格：AI 说该合并的排在最前，其余按名称相似分。和后端筛选 match 是同一套分法
 * （repositories/scenario_candidates._match_conditions），一个场景只落一类。
 */
export function matchOf(candidate: Pick<CandidateItem, MatchFields>): Match {
  const verdict = candidate.ai_verdict
  if (verdict === AI_SAME || verdict === AI_UNDER) {
    return { kind: 'ai', label: verdict === AI_SAME ? 'AI 认为是同一个' : 'AI 认为应归到这里', name: arrow(candidate.ai_similar), note: '' }
  }
  const aiNote = verdict === AI_NEW ? 'AI 认为是新场景' : verdict ? 'AI 没判断出来' : 'AI 还没看'
  if (candidate.similar_level === '高' || candidate.similar_level === '中') {
    return { kind: candidate.similar_level === '高' ? 'high' : 'medium', label: similarLabel(candidate.similar_level), name: arrow(candidate.similar_name), note: aiNote }
  }
  return { kind: 'none', label: '没有', name: '', note: verdict === AI_NEW ? 'AI 也认为是新场景' : aiNote }
}

/** 审核页「码表里有没有和它是同一个的」列表里的一项。 */
export interface MatchItem {
  /** 码表里对得上的路径，能直接合并；AI 说的名字码表里对不上时为 null */
  path: string[] | null
  text: string
  badge: string
  /** AI 认为是同一个的那项：排第一、加框、按钮用主色 */
  ai: boolean
  /** 几级 · 哪个行业 · 是不是同一个行业 */
  note: string
  /** AI 的理由，或码表里的描述 */
  detail: string
}

type MatchSource = Pick<CandidateItem, MatchFields | 'ai_target' | 'ai_reason' | 'main_industry'>
type Similar = CandidateContext['similar'][number]

function similarNote(item: Similar, industry: string): string {
  const level = `${levelName(item.path.filter(Boolean).length)}场景`
  if (!item.industry) return level
  const same = item.industry.includes(industry)
  return `${level} · ${item.industry} · ${same ? '同一个行业' : '不是同一个行业，多半不是一回事'}`
}

/** AI 认为是同一个的那项；AI 没说该合并时为 null。 */
function aiItem(candidate: MatchSource, similar: Similar[]): MatchItem | null {
  const match = matchOf(candidate)
  if (match.kind !== 'ai' || !match.name) return null
  const path = candidate.ai_target ? candidate.ai_target.split(' > ') : null
  const text = path ? pathText(path) : ''
  const same = text ? similar.find(item => pathText(item.path) === text) : undefined
  return {
    path,
    text: text || match.name,
    badge: match.label,
    ai: true,
    note: same ? similarNote(same, candidate.main_industry) : path ? '' : '码表里没对上这个名字，请自己在码表里选',
    detail: candidate.ai_reason ? `AI：${candidate.ai_reason}` : '',
  }
}

/** AI 认为是同一个的排第一，名称相近的排后面；两边指的是同一个场景时只列一次。 */
export function matchItems(candidate: MatchSource, similar: Similar[]): MatchItem[] {
  const ai = aiItem(candidate, similar)
  const rest = similar
    .filter(item => !ai?.path || pathText(item.path) !== ai.text)
    .map(item => ({ path: item.path, text: pathText(item.path), badge: similarLabel(item.level), ai: false, note: similarNote(item, candidate.main_industry), detail: item.desc }))
  return ai ? [ai, ...rest] : rest
}

/** 列表上方那句「AI 怎么看」：AI 的结论在前，名称相近的只是参考。 */
export function matchHeadline(candidate: Pick<CandidateItem, 'ai_verdict'>, items: MatchItem[]): string {
  const verdict = candidate.ai_verdict
  const rest = items.filter(item => !item.ai).length
  if (verdict === AI_SAME || verdict === AI_UNDER) return `找到 ${items.length} 个，AI 认为是同一个的排在最前`
  const lead = verdict === AI_NEW
    ? 'AI 对照了同一行业的场景，认为码表里没有同样的'
    : verdict ? 'AI 没判断出来' : 'AI 还没看过（任务调度里「新增场景找相似」跑过后才有）'
  return rest ? `${lead}；下面 ${rest} 个只是名称相近，供参考` : `${lead}；名称相近的也没有`
}

/** AI 找相似的结果写成一句话（解读核对页的场景卡片用）；还没让 AI 看过的说明怎么才会有。 */
export function aiText(candidate: Pick<CandidateItem, 'ai_verdict' | 'ai_similar' | 'ai_reason' | 'ai_checked_at'>): string {
  if (!candidate.ai_verdict) return 'AI 还没看过：任务调度里的「新增场景找相似」跑过一批后才有'
  if (candidate.ai_verdict === '判断失败') return `AI 没判断出来：${candidate.ai_reason}`
  const similar = candidate.ai_similar ? `，最像的是「${arrow(candidate.ai_similar)}」` : ''
  const reason = candidate.ai_reason ? `。理由：${candidate.ai_reason}` : ''
  return `AI 判断：${candidate.ai_verdict}${similar}${reason}`
}
