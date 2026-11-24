import { ref } from 'vue'

import { getTaggingContract, type ContractTask } from '@/api/aiTagging'
import { useAuthStore } from '@/stores/auth'

/** 新建批量任务「从政策库取数」能取哪几步的数据：打标任务契约。取数接口挂 policy.base_tags 的查看档，没有就不取、不显示入口。
 * 取到一次就留着；取失败下次打开再试。 */
export function useSampleTasks() {
  const auth = useAuthStore()
  const tasks = ref<ContractTask[]>([])
  let loaded = false

  async function ensure(): Promise<void> {
    if (loaded || !auth.canRead('policy.base_tags')) return
    loaded = true
    try {
      tasks.value = (await getTaggingContract()).tasks
    } catch {
      loaded = false
    }
  }

  return { tasks, ensure }
}
