import type {
  ThinktankFavoriteEntry,
  ThinktankFavoritesResponse,
  ThinktankLibraryKey,
} from '@/api/thinktank'

export type FavoriteTabKey = 'all' | ThinktankLibraryKey

export interface FavoriteTabSpec {
  key: FavoriteTabKey
  label: string
  count: number
}

export interface FavoriteQuickLink {
  library: ThinktankLibraryKey
  label: string
  resource: string
  path: string
}

export type FavoriteCounts = ThinktankFavoritesResponse['counts']

export const EMPTY_FAVORITE_COUNTS: FavoriteCounts = {
  all: 0,
  knowledge: 0,
  reports: 0,
  proposals: 0,
}

const LIBRARY_QUICK_LINKS: readonly FavoriteQuickLink[] = [
  { library: 'knowledge', label: '前往资料库', resource: 'thinktank.knowledge', path: '/thinktank/knowledge' },
  { library: 'reports', label: '前往报告库', resource: 'thinktank.reports', path: '/thinktank/reports' },
  { library: 'proposals', label: '前往方案库', resource: 'thinktank.proposals', path: '/thinktank/proposals' },
]

export function buildFavoriteTabs(counts: FavoriteCounts): FavoriteTabSpec[] {
  return [
    { key: 'all', label: '全部', count: counts.all },
    { key: 'knowledge', label: '资料库', count: counts.knowledge },
    { key: 'reports', label: '报告库', count: counts.reports },
    { key: 'proposals', label: '方案库', count: counts.proposals },
  ]
}

export function libraryTagType(library: ThinktankLibraryKey): 'primary' | 'success' | 'warning' {
  if (library === 'reports') return 'success'
  if (library === 'proposals') return 'warning'
  return 'primary'
}

export function favoriteRowKey(entry: Pick<ThinktankFavoriteEntry, 'library' | 'id'>): string {
  return `${entry.library}:${entry.id}`
}

export function applyUnfavoriteUpdate(
  state: { items: ThinktankFavoriteEntry[]; total: number; counts: FavoriteCounts },
  target: Pick<ThinktankFavoriteEntry, 'library' | 'id'>,
): { items: ThinktankFavoriteEntry[]; total: number; counts: FavoriteCounts } {
  const key = favoriteRowKey(target)
  const exists = state.items.some(item => favoriteRowKey(item) === key)
  if (!exists) return state
  const nextCounts: FavoriteCounts = {
    ...state.counts,
    all: Math.max(0, state.counts.all - 1),
    [target.library]: Math.max(0, state.counts[target.library] - 1),
  }
  return {
    items: state.items.filter(item => favoriteRowKey(item) !== key),
    total: Math.max(0, state.total - 1),
    counts: nextCounts,
  }
}

export function permittedQuickLinks(canRead: (resource: string) => boolean): FavoriteQuickLink[] {
  return LIBRARY_QUICK_LINKS.filter(link => canRead(link.resource))
}
