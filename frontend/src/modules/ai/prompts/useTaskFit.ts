import { computed, ref, type Ref } from 'vue'

import { getTaggingContract, type ContractTask } from '@/api/aiTagging'
import { useAuthStore } from '@/stores/auth'
import { splitFields } from '../shared/aiText'
import { usedVariables } from './promptVariables'
import { fitResults } from './taskFit'

interface Draft {
  category: string
  content: string
  output_fields: string
  code_table: string
}

/**
 * 政策类模板和三个打标任务的适配：按草稿实时检查，取测试数据也用同一份约定。
 * 约定从政策服务取，要「政策基础标签」查看权（取的是政策数据）；没有权限就不显示这一块。
 */
export function useTaskFit(form: Draft) {
  const auth = useAuthStore()
  const tasks: Ref<ContractTask[]> = ref([])
  let loaded = false

  async function load(): Promise<void> {
    if (loaded || !auth.canRead('policy.base_tags')) return
    loaded = true
    try {
      tasks.value = (await getTaggingContract()).tasks
    } catch {
      loaded = false // 政策服务暂时不可用：这一块先不显示，下次切到政策类模板再试
    }
  }

  const isPolicy = computed(() => form.category === 'policy')
  /** 政策类模板、约定也取到了：显示「定时任务适配」这一块 */
  const visible = computed(() => isPolicy.value && tasks.value.length > 0)
  // 空白草稿不检查，只给一句引导，免得新建时满屏「不能用」。
  const results = computed(() => {
    const fields = splitFields(form.output_fields)
    if (!visible.value || (!form.content.trim() && !fields.length)) return []
    const variables = usedVariables(form.content, [], false).map(item => item.name)
    return fitResults(tasks.value, variables, fields, Boolean(form.code_table))
  })
  const sampleTasks = computed(() => (isPolicy.value ? tasks.value : []))
  /** 哪些定时任务在用这个模板：只有政策类会被定时任务选用；政策类但约定没取到（没权限、服务暂时不可用）时是 null，说不清就不乱说。 */
  function usedBy(promptId: string): string[] | null {
    if (!isPolicy.value) return []
    if (!tasks.value.length) return null
    return tasks.value.filter(task => promptId && task.prompt_id === promptId).map(task => task.name)
  }

  return { load, visible, results, sampleTasks, usedBy }
}
