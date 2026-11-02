import { ref, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { errorMessage } from '@/api/errors'
import { absorbCandidate, getCandidatePeers, type CandidateItem } from '@/api/scenarioCandidates'

export type Peer = CandidateItem & { score: number; level: string }

/**
 * 别的待审场景里名称和这个相似的（同一个场景换了说法），以及「并入本场景」：
 * 它的解读行改成这个说法搬过来，以后 AI 再写它也归到这里。并完重新载入这一个。
 */
export function useCandidatePeers(candidate: Ref<CandidateItem | null>, reload: () => Promise<void>) {
  const peers = ref<Peer[]>([])
  const absorbing = ref(false)

  async function load(id: string) {
    try {
      const found = await getCandidatePeers(id)
      if (candidate.value?.id === id) peers.value = found.items
    } catch {
      if (candidate.value?.id === id) peers.value = []
    }
  }
  watch(() => candidate.value?.id, (id) => {
    peers.value = []
    if (id) void load(id)
  }, { immediate: true })

  async function absorb(peer: Peer): Promise<void> {
    const current = candidate.value
    if (!current || absorbing.value) return
    const ok = await ElMessageBox.confirm(
      `把「${peer.name}」（${peer.policy_count} 条政策）并到「${current.name}」？它的解读行改成这个说法，以后 AI 再写「${peer.name}」也归到这里。`,
      '并成一个场景',
      { type: 'warning', confirmButtonText: '并入', cancelButtonText: '取消' },
    ).then(() => true, () => false)
    if (!ok) return
    absorbing.value = true
    try {
      await absorbCandidate(current.id, { version: current.version, peer_id: peer.id, peer_version: peer.version })
      ElMessage.success(`已把「${peer.name}」并进来`)
      await reload()
    } catch (error) {
      ElMessage.error(errorMessage(error, '没有并成，请刷新后重试'))
    } finally {
      absorbing.value = false
    }
  }

  return { peers, absorbing, absorb }
}
