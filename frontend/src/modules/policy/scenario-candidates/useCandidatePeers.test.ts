import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

const message = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
const box = vi.hoisted(() => ({ confirm: vi.fn() }))
const api = vi.hoisted(() => ({ getCandidatePeers: vi.fn(), absorbCandidate: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: message, ElMessageBox: box }))
vi.mock('@/api/scenarioCandidates', () => api)

import type { CandidateItem } from '@/api/scenarioCandidates'
import { useCandidatePeers, type Peer } from './useCandidatePeers'

const flush = () => new Promise(resolve => setTimeout(resolve, 0))
const current = { id: 'c1', name: '智慧机场工程建设管理', version: 3 } as CandidateItem
const peer = { id: 'c2', name: '机场建设数字化管理', version: 1, policy_count: 9, score: 0.4, level: '中' } as Peer

describe('相似的其他待审场景', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getCandidatePeers.mockResolvedValue({ items: [peer] })
  })

  it('换到哪个场景就取哪个的相似场景', async () => {
    const candidate = ref<CandidateItem | null>(current)
    const { peers } = useCandidatePeers(candidate, vi.fn())
    await flush()
    expect(api.getCandidatePeers).toHaveBeenCalledWith('c1')
    expect(peers.value).toEqual([peer])
    candidate.value = null
    await nextTick()
    expect(peers.value).toEqual([])
  })

  it('确认后并入并重新载入；取消就不动', async () => {
    const reload = vi.fn(() => Promise.resolve())
    const { absorb } = useCandidatePeers(ref(current), reload)
    box.confirm.mockRejectedValueOnce('cancel')
    await absorb(peer)
    expect(api.absorbCandidate).not.toHaveBeenCalled()
    box.confirm.mockResolvedValueOnce('confirm')
    api.absorbCandidate.mockResolvedValueOnce({})
    await absorb(peer)
    expect(api.absorbCandidate).toHaveBeenCalledWith('c1', { version: 3, peer_id: 'c2', peer_version: 1 })
    expect(reload).toHaveBeenCalledOnce()
    expect(message.success).toHaveBeenCalledWith('已把「机场建设数字化管理」并进来')
  })
})
