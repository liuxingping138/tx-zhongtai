import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, ref, type Ref } from 'vue'

import { errorMessage } from '@/api/errors'
import {
  deleteKnowledge,
  favoriteKnowledge,
  unfavoriteKnowledge,
  type KnowledgeItem,
} from '@/api/thinktank'

export interface BatchFailure<T> {
  item: T
  reason: string
}

export interface BatchResult<T> {
  succeeded: T[]
  failed: BatchFailure<T>[]
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

export function formatBatchSummary<T>(verb: string, result: BatchResult<T>): string {
  const ok = result.succeeded.length
  const bad = result.failed.length
  if (bad === 0) return `已${verb} ${ok} 条资料`
  const firstReason = result.failed[0]!.reason
  if (ok === 0) return `批量${verb}失败：${firstReason}`
  return `已${verb} ${ok} 条，${bad} 条失败（${firstReason}）`
}

function notifyBatch<T>(verb: string, result: BatchResult<T>): void {
  const message = formatBatchSummary(verb, result)
  if (result.failed.length === 0) ElMessage.success(message)
  else if (result.succeeded.length > 0) ElMessage.warning(message)
  else ElMessage.error(message)
}

export interface KnowledgeBatchOptions {
  checked: Ref<KnowledgeItem[]>
  clearSelection: () => void
  refresh: () => Promise<void>
}

export function useKnowledgeBatch(options: KnowledgeBatchOptions) {
  const batchBusy = ref(false)
  const unfavorited = computed(() => options.checked.value.filter(row => !row.is_favorited))
  const favorited = computed(() => options.checked.value.filter(row => row.is_favorited))
  const deletable = computed(() => options.checked.value.filter(row => row.can_edit))

  async function onBatchFavorite() {
    const targets = [...unfavorited.value]
    if (!targets.length || batchBusy.value) return
    batchBusy.value = true
    try {
      const result = await runConcurrent(
        targets,
        async (row) => {
          const res = await favoriteKnowledge(row.id)
          row.is_favorited = res.is_favorited
        },
        '收藏失败',
      )
      notifyBatch('收藏', result)
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
          const res = await unfavoriteKnowledge(row.id)
          row.is_favorited = res.is_favorited
        },
        '取消收藏失败',
      )
      notifyBatch('取消收藏', result)
      options.clearSelection()
      if (refreshAfter && result.succeeded.length > 0) await options.refresh()
    } finally {
      batchBusy.value = false
    }
  }

  async function onBatchDelete() {
    const targets = [...deletable.value]
    if (!targets.length || batchBusy.value) return
    const skipped = options.checked.value.length - targets.length
    const skipHint = skipped > 0 ? `（已自动跳过 ${skipped} 条无删除权限的资料）` : ''
    try {
      await ElMessageBox.confirm(
        `确认删除已选的 ${targets.length} 条资料吗？${skipHint}删除后不可恢复，并记入操作审计。`,
        '批量删除确认',
        { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
    batchBusy.value = true
    try {
      const result = await runConcurrent(targets, row => deleteKnowledge(row.id).then(() => {}), '删除失败')
      notifyBatch('删除', result)
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
    deletable,
    onBatchFavorite,
    onBatchUnfavorite,
    onBatchDelete,
  }
}
