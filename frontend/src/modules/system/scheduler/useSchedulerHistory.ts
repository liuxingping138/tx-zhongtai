import { ref } from 'vue'

import { errorMessage } from '@/api/errors'
import { listRuns, type ScheduledJob, type ScheduledRun } from '@/api/scheduler'

/** 某个任务的执行记录抽屉：分页加载，连续触发时只采用最后一次请求的结果。 */
export function useSchedulerHistory() {
  const job = ref<ScheduledJob | null>(null)
  const visible = ref(false)
  const records = ref<ScheduledRun[]>([])
  const loading = ref(false)
  const error = ref('')
  const page = ref(1)
  const total = ref(0)
  let sequence = 0

  /** quiet 用于后台轮询：不闪加载动画。 */
  async function load(quiet = false): Promise<void> {
    if (!job.value) return
    const current = ++sequence
    loading.value = !quiet
    try {
      const data = await listRuns(job.value.code, page.value, { base: job.value.base })
      if (current !== sequence) return
      records.value = data.items
      total.value = data.total
      error.value = ''
    } catch (e) {
      if (current === sequence) error.value = errorMessage(e, '执行记录加载失败')
    } finally {
      if (current === sequence) loading.value = false
    }
  }

  function open(target: ScheduledJob): void {
    job.value = target
    page.value = 1
    records.value = []
    total.value = 0
    visible.value = true
    void load()
  }

  /** 页面卸载时让还在路上的请求作废。 */
  function stop(): void {
    sequence++
  }

  return { job, visible, records, loading, error, page, total, load, open, stop }
}

export type SchedulerHistory = ReturnType<typeof useSchedulerHistory>
