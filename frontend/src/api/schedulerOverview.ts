import type { ScheduledJob, SchedulerOverview, ServiceOverview, WorkerStatus } from './scheduler'

/** 合并各服务的结果：取不到的服务记成离线并带上原因，不拖累其他服务的任务。全都取不到才算失败。 */
export function mergeOverviews(
  services: readonly { name: string; base: string }[],
  results: PromiseSettledResult<ServiceOverview>[],
  describe: (cause: unknown) => string,
): SchedulerOverview {
  const items: ScheduledJob[] = []
  const workers: WorkerStatus[] = []
  services.forEach(({ name, base }, index) => {
    const result = results[index]
    if (!result) return
    if (result.status === 'fulfilled') {
      items.push(...result.value.items.map(job => ({ ...job, base })))
      workers.push({ service: name, online: result.value.worker_online, heartbeat_at: result.value.heartbeat_at, error: '' })
    } else {
      workers.push({ service: name, online: false, heartbeat_at: null, error: describe(result.reason) })
    }
  })
  const failed = results.find(result => result.status === 'rejected')
  if (failed && results.every(result => result.status === 'rejected')) throw failed.reason
  return { items, workers }
}
