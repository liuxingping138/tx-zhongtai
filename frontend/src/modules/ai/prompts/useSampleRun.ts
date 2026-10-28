import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'

import type { BatchRun, PromptTemplate } from '@/api/ai'
import { getSampleRun, retrySampleRun, startSampleRun, stopSampleRun, type SampleRunState } from '@/api/aiSamples'
import { errorMessage } from '@/api/errors'
import { isActive } from '../shared/aiText'
import { downloadSampleFile } from '../shared/downloads'

const EMPTY: SampleRunState = { run: null, rows: null, history: [], compare: null }
const POLL_MS = 2000

/**
 * 一个模板的样本试跑：右栏摘要、逐行结果抽屉、试发时的对照共用这一份。
 * 默认看最近一次、和它前一次比；抽屉里可以换着看哪一次、和哪一次比。在跑时每 2 秒刷新一次。
 */
export function useSampleRun(template: Ref<PromptTemplate | null>, changed: (run: BatchRun) => void) {
  const state = ref<SampleRunState>(EMPTY)
  const loading = ref(false)
  const busy = ref(false)
  /** 看哪一次、和哪一次比；空串是默认（最近一次、它的前一次），比较对象 'none' 是不比 */
  const runId = ref('')
  const compareId = ref('')
  let timer: ReturnType<typeof setTimeout> | undefined
  let sequence = 0

  const run = computed(() => state.value.run)
  const running = computed(() => Boolean(run.value && isActive(run.value.status)))

  function apply(next: SampleRunState): void {
    state.value = next
    // 模板上的「最近一次试跑」只跟着最近一次变，翻看旧的不算。
    if (next.run && next.run.id === next.history[0]?.id) changed(next.run)
  }

  async function load(quiet = false): Promise<void> {
    const current = template.value
    clearTimeout(timer)
    if (!current) { state.value = EMPTY; return }
    const token = ++sequence
    loading.value = !quiet
    const next = await getSampleRun(current.id, { runId: runId.value, compareId: compareId.value }).catch((error: unknown) => {
      if (!quiet && token === sequence) ElMessage.error(errorMessage(error, '试跑结果加载失败，请重试'))
      return null
    })
    if (token !== sequence) return
    loading.value = false
    if (next) apply(next)
    if (running.value) timer = setTimeout(() => void load(true), POLL_MS)
  }

  function view(nextRun: string, nextCompare: string): Promise<void> {
    runId.value = nextRun
    compareId.value = nextCompare
    return load()
  }

  async function act(work: () => Promise<SampleRunState>, failure: string): Promise<boolean> {
    if (busy.value) return false
    busy.value = true
    try {
      state.value = await work()
      await load(true)
      return true
    } catch (error) {
      ElMessage.error(errorMessage(error, failure))
      return false
    } finally {
      busy.value = false
    }
  }

  function start(limit: number, thinking: boolean): Promise<boolean> {
    const current = template.value
    if (!current) return Promise.resolve(false)
    runId.value = ''
    compareId.value = ''
    return act(() => startSampleRun(current.id, { thinking, limit }), '试跑没能开始，请重试')
  }

  function stop(): Promise<boolean> {
    const current = template.value
    return current ? act(() => stopSampleRun(current.id), '停止失败，请重试') : Promise.resolve(false)
  }

  /** 只重问这次失败和没跑到的行，用的是这次冻结的提示词。 */
  function retry(): Promise<boolean> {
    const current = template.value
    const target = run.value
    if (!current || !target) return Promise.resolve(false)
    return act(() => retrySampleRun(current.id, target.id), '重跑没能开始，请重试')
  }

  async function download(): Promise<void> {
    const current = template.value
    const target = run.value
    if (!current || !target) return
    try {
      await downloadSampleFile(current.id, target.id, 'result', `${current.title}-第${target.no}次样本试跑结果.xlsx`)
    } catch (error) {
      ElMessage.error(errorMessage(error, '下载失败，请重试'))
    }
  }

  watch(() => template.value?.id, () => {
    runId.value = ''
    compareId.value = ''
    void load()
  }, { immediate: true })
  onBeforeUnmount(() => { sequence++; clearTimeout(timer) })

  return { state, run, running, loading, busy, runId, compareId, load, view, start, stop, retry, download }
}

export type SampleRun = ReturnType<typeof useSampleRun>
