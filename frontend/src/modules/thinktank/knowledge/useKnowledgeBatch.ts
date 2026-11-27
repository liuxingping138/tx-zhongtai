import type { Ref } from 'vue'

import {
  deleteKnowledge,
  downloadKnowledgeBlob,
  favoriteKnowledge,
  unfavoriteKnowledge,
  type KnowledgeItem,
} from '@/api/thinktank'
import {
  formatBatchSummary,
  runConcurrent,
  useThinktankBatch,
  type BatchFailure,
  type BatchResult,
} from '../shared/useThinktankBatch'

export type { BatchFailure, BatchResult }
export { formatBatchSummary, runConcurrent }

export interface KnowledgeBatchOptions {
  checked: Ref<KnowledgeItem[]>
  clearSelection: () => void
  refresh: () => Promise<void>
}

export function useKnowledgeBatch(options: KnowledgeBatchOptions) {
  return useThinktankBatch({
    checked: options.checked,
    clearSelection: options.clearSelection,
    refresh: options.refresh,
    itemNoun: '资料',
    api: {
      favorite: favoriteKnowledge,
      unfavorite: unfavoriteKnowledge,
      remove: deleteKnowledge,
      download: downloadKnowledgeBlob,
      getTitle: row => row.file_name,
    },
  })
}
