import { computed, ref, shallowRef, triggerRef, type Ref } from 'vue'

import { buildPageText, findInPage, matchLabel, normalizeQuery, type PageMatch, type PageText } from './pdfSearch'

/** 一处匹配：第几页、本页第几处，以及在整页文本里的位置。 */
export interface SearchHit extends PageMatch {
  page: number
  indexInPage: number
}

export interface PdfSearchDeps {
  numPages: Ref<number>
  /** 取某页的文字块（与文字层一致）；文档没打开时返回 null。 */
  pageText: (pageNumber: number) => Promise<string[]> | null
  /** 当前匹配换了：滚到那一页。 */
  onJump: (hit: SearchHit) => void
}

/** 停止输入这么久才开始找：一边打字一边整份翻页取文字会白白多发很多 Range 请求。 */
export const SEARCH_DEBOUNCE_MS = 250

/**
 * 文档内查找，严格按需：没输入查找词之前一页文字都不取，打开文档仍只取第一页和可见页。
 *
 * - 输入后从第 1 页往后逐页取文字（取过的页按本文档缓存），边找边出结果，找到第一处就跳过去。
 * - 换查找词、关掉查找、换文档都立即作废正在进行的这一轮（后面的页不再去取）；换文档还清掉缓存。
 */
export function usePdfSearch(deps: PdfSearchDeps) {
  const open = ref(false)
  const query = ref('')
  const needle = ref('')
  const hits = shallowRef<SearchHit[]>([])
  const current = ref(-1)
  const scanning = ref(false)
  const cache = new Map<number, PageText>()
  let seq = 0
  let timer: ReturnType<typeof setTimeout> | null = null

  const label = computed(() => matchLabel(current.value, hits.value.length, scanning.value))
  const selected = computed(() => hits.value[current.value] ?? null)

  function clearTimer() {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }

  function stop() {
    seq += 1
    clearTimer()
    scanning.value = false
  }

  function clearResults() {
    hits.value = []
    current.value = -1
    needle.value = ''
  }

  async function textOf(pageNumber: number): Promise<PageText | null> {
    const known = cache.get(pageNumber)
    if (known) return known
    try {
      const items = await deps.pageText(pageNumber)
      if (!items) return null
      const page = buildPageText(items)
      cache.set(pageNumber, page)
      return page
    } catch {
      return null // 这一页取不到（网络抖动、文档刚被关掉）：当作没有匹配，下次查找再取
    }
  }

  function collect(pageNumber: number, page: PageText) {
    const found = findInPage(page, needle.value)
    if (!found.length) return
    hits.value.push(...found.map((match, indexInPage) => ({ ...match, page: pageNumber, indexInPage })))
    triggerRef(hits)
    if (current.value === -1) {
      current.value = 0
      deps.onJump(hits.value[0]!)
    }
  }

  async function run(text: string): Promise<void> {
    stop()
    const mine = seq
    clearResults()
    needle.value = normalizeQuery(text)
    if (!needle.value) return
    scanning.value = true
    for (let pageNumber = 1; pageNumber <= deps.numPages.value; pageNumber += 1) {
      const page = await textOf(pageNumber)
      if (mine !== seq) return
      if (page) collect(pageNumber, page)
    }
    scanning.value = false
  }

  /** 输入框每次变化：停一会儿再找。 */
  function setQuery(text: string) {
    query.value = text
    stop()
    timer = setTimeout(() => { void run(text) }, SEARCH_DEBOUNCE_MS)
  }

  /** 回车：不等停顿立刻找；已经找过同一个词就跳到下一处。 */
  function submit(backward = false) {
    if (timer === null && needle.value === normalizeQuery(query.value) && hits.value.length) {
      step(backward ? -1 : 1)
      return
    }
    void run(query.value)
  }

  function step(direction: 1 | -1) {
    const total = hits.value.length
    if (!total) return
    current.value = (current.value + direction + total) % total
    deps.onJump(hits.value[current.value]!)
  }

  /** 某页要画的匹配：查找词和本页第几处是当前匹配（-1 表示不在本页）。 */
  function pageSelection(pageNumber: number): number {
    const hit = selected.value
    return hit && hit.page === pageNumber ? hit.indexInPage : -1
  }

  function show() {
    open.value = true
  }

  /** 关掉查找：作废这一轮、清掉高亮，缓存的文字留着，再打开同一份文档时不用重取。 */
  function close(): boolean {
    if (!open.value) return false
    stop()
    clearResults()
    query.value = ''
    open.value = false
    return true
  }

  /** 换了文档（或令牌过期重开）：作废这一轮、清掉缓存；查找框开着就按原词重找。 */
  function reset() {
    stop()
    cache.clear()
    clearResults()
    if (open.value && query.value.trim()) void run(query.value)
  }

  return { open, query, needle, hits, current, scanning, label, selected, setQuery, submit, step, pageSelection, show, close, reset }
}
