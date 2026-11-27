import type { AxiosResponse } from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, ref, type Ref } from 'vue'

import { downloadBlob } from '@/api/download'
import { errorMessage } from '@/api/errors'
import { parseContentDispositionFilename } from './options'

export interface BatchFailure<T> {
  item: T
  reason: string
}

export interface BatchResult<T> {
  succeeded: T[]
  failed: BatchFailure<T>[]
}

export interface ThinktankBatchItem {
  id: string
  is_favorited: boolean
  can_edit: boolean
  can_export: boolean
}

export interface ThinktankBatchApi<T extends ThinktankBatchItem> {
  favorite: (id: string) => Promise<{ is_favorited: boolean }>
  unfavorite: (id: string) => Promise<{ is_favorited: boolean }>
  remove: (id: string) => Promise<unknown>
  download?: (id: string) => Promise<AxiosResponse<Blob>>
  getTitle?: (row: T) => string
}

export interface ThinktankBatchOptions<T extends ThinktankBatchItem> {
  checked: Ref<T[]>
  clearSelection: () => void
  refresh: () => Promise<void>
  api: ThinktankBatchApi<T>
  itemNoun?: string
}

/** 分批并发执行单项接口，避免单页批量勾选瞬间打满连接或触发限流。 */
export async function runConcurrent<T>(
  items: readonly T[],
  worker: (item: T) => Promise<void>,
  fallbackError: string,
  concurrency = 4,
): Promise<BatchResult<T>> {
  const succeeded: T[] = []
  const failed: BatchFailure<T>[] = []
  const size = Math.max(1, concurrency)
  for (let start = 0; start < items.length; start += size) {
    const chunk = items.slice(start, start + size)
    const settled = await Promise.allSettled(chunk.map(item => worker(item)))
    settled.forEach((outcome, index) => {
      const item = chunk[index]!
      if (outcome.status === 'fulfilled') succeeded.push(item)
      else failed.push({ item, reason: errorMessage(outcome.reason, fallbackError) })
    })
  }
  return { succeeded, failed }
}

export function formatBatchSummary<T>(verb: string, result: BatchResult<T>, noun = '资料'): string {
  const ok = result.succeeded.length
  const bad = result.failed.length
  if (bad === 0) return `已${verb} ${ok} 条${noun}`
  const firstReason = result.failed[0]!.reason
  if (ok === 0) return `批量${verb}失败：${firstReason}`
  return `已${verb} ${ok} 条，${bad} 条失败（${firstReason}）`
}

function notifyBatch<T>(verb: string, result: BatchResult<T>, noun: string): void {
  const message = formatBatchSummary(verb, result, noun)
  if (result.failed.length === 0) ElMessage.success(message)
  else if (result.succeeded.length > 0) ElMessage.warning(message)
  else ElMessage.error(message)
}

export function useThinktankBatch<T extends ThinktankBatchItem>(options: ThinktankBatchOptions<T>) {
  const noun = options.itemNoun ?? '资料'
  const batchBusy = ref(false)
  const unfavorited = computed(() => options.checked.value.filter(row => !row.is_favorited))
  const favorited = computed(() => options.checked.value.filter(row => row.is_favorited))
  const downloadable = computed(() => options.checked.value.filter(row => row.can_export))
  const deletable = computed(() => options.checked.value.filter(row => row.can_edit))

  async function onBatchFavorite() {
    const targets = [...unfavorited.value]
    if (!targets.length || batchBusy.value) return
    batchBusy.value = true
    try {
      const result = await runConcurrent(
        targets,
        async (row) => {
          const res = await options.api.favorite(row.id)
          row.is_favorited = res.is_favorited
        },
        '收藏失败',
      )
      notifyBatch('收藏', result, noun)
      options.clearSelection()
    } finally {
      batchBusy.value = false
    }
  }

  async function onBatchUnfavorite(refreshAfter = false) {
    const targets = [...favorited.value]
    if (!targets.length || batchBusy.value) return
    batchBusy.value = true
    try {
      const result = await runConcurrent(
        targets,
        async (row) => {
          const res = await options.api.unfavorite(row.id)
          row.is_favorited = res.is_favorited
        },
        '取消收藏失败',
      )
      notifyBatch('取消收藏', result, noun)
      options.clearSelection()
      if (refreshAfter && result.succeeded.length > 0) await options.refresh()
    } finally {
      batchBusy.value = false
    }
  }

  async function onBatchDownload() {
    const downloadFn = options.api.download
    const targets = [...downloadable.value]
    if (!downloadFn || !targets.length || batchBusy.value) return
    batchBusy.value = true
    try {
      const result = await runConcurrent(
        targets,
        async (row) => {
          const resp = await downloadFn(row.id)
          const fallback = options.api.getTitle?.(row) || `${row.id}`
          const rawHeader: unknown = resp.headers?.['content-disposition']
          const filename = parseContentDispositionFilename(typeof rawHeader === 'string' ? rawHeader : undefined, fallback)
          downloadBlob(resp.data, filename)
        },
        '下载失败',
        2,
      )
      notifyBatch('下载', result, noun)
      options.clearSelection()
    } finally {
      batchBusy.value = false
    }
  }

  async function onBatchDelete() {
    const targets = [...deletable.value]
    if (!targets.length || batchBusy.value) return
    const skipped = options.checked.value.length - targets.length
    const skipHint = skipped > 0 ? `（已自动跳过 ${skipped} 条无删除权限的${noun}）` : ''
    try {
      await ElMessageBox.confirm(
        `确认删除已选的 ${targets.length} 条${noun}吗？${skipHint}删除后不可恢复，并记入操作审计。`,
        '批量删除确认',
        { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
    batchBusy.value = true
    try {
      const result = await runConcurrent(targets, row => options.api.remove(row.id).then(() => {}), '删除失败')
      notifyBatch('删除', result, noun)
      options.clearSelection()
      if (result.succeeded.length > 0) await options.refresh()
    } finally {
      batchBusy.value = false
    }
  }

  return {
    batchBusy,
    unfavorited,
    favorited,
    downloadable,
    deletable,
    onBatchFavorite,
    onBatchUnfavorite,
    onBatchDownload,
    onBatchDelete,
  }
}
