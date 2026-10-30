/**
 * 一个接一个地跑：前一个结束（不论成败）才开始下一个。
 * 模板的保存、上传附件、删附件都会把版本号加一：同时发出去的话后到的那个带着旧版本号，被当成「别人改过」回 409；
 * 新模板连按 Ctrl/⌘+S、上传时顺便保存，还会建出两个同名模板。
 */
export function createTurns(): <T>(task: () => Promise<T>) => Promise<T> {
  let last: Promise<unknown> = Promise.resolve()
  return <T>(task: () => Promise<T>): Promise<T> => {
    const run = last.then(task, task)
    last = run.catch(() => undefined)
    return run
  }
}
