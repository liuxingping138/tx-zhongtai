import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { deletePromptFile, savePromptTestRows, uploadPromptFile, type PromptFileKind, type PromptTemplate } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { downloadPromptFile } from '../shared/downloads'

// 码表文本直接用，Excel 由后端转成一行一条、Tab 分隔的文字。
const ACCEPT: Record<PromptFileKind, string> = { excel: '.xlsx', code: '.txt,.csv,.xlsx' }
const UPLOADED: Record<PromptFileKind, string> = { excel: '测试样本已上传', code: '码表已上传' }

interface Options {
  template: Ref<PromptTemplate | null>
  /** 还没有模板时能不能顺便建一个：要有名字和类型，不能就提示原因并返回 false。同步执行，文件框要在点击当下弹出 */
  canCreate: () => boolean
  /** 把当前草稿存成模板并返回它，失败返回 null */
  create: () => Promise<PromptTemplate | null>
  changed: (template: PromptTemplate) => void
  /** 和保存排队执行：上传、删附件也会换版本号，和保存同时发出去会自己撞自己回 409。 */
  inTurn?: <T>(task: () => Promise<T>) => Promise<T>
}

/**
 * 模板的两个附件：测试样本（.xlsx）和上传的码表（.txt）。
 * 新模板不用先点保存：选好文件时顺便把草稿存成模板再上传，先传样本、照着列名写提示词才顺手。
 * 文件框挂在编辑页上（bind / received），编辑器、试跑区、设置区的「上传」都走这里。
 */
/** 码表存的是转好的文字：Excel 上传的下载回来叫 .txt（和后端一致），免得用 Excel 打开一个文本文件。 */
export function codeDownloadName(name: string): string {
  return /\.(txt|csv)$/i.test(name) ? name : `${name.replace(/\.[^.]*$/, '')}.txt`
}

export function useTemplateFiles(options: Options) {
  const busy = ref<PromptFileKind | null>(null)
  const queued = <T>(task: () => Promise<T>): Promise<T> => (options.inTurn ? options.inTurn(task) : task())
  const inputs: Partial<Record<PromptFileKind, HTMLInputElement | null>> = {}

  function bind(kind: PromptFileKind) {
    return (element: unknown) => { inputs[kind] = element as HTMLInputElement | null }
  }

  /** 已有模板，或者能顺便建一个：返回模板；不能建时已经提示过原因。 */
  async function ensure(): Promise<PromptTemplate | null> {
    if (options.template.value) return options.template.value
    return options.canCreate() ? options.create() : null
  }

  function pick(kind: PromptFileKind): void {
    if (busy.value || (!options.template.value && !options.canCreate())) return
    inputs[kind]?.click()
  }

  async function received(kind: PromptFileKind, event: Event): Promise<void> {
    const target = event.target as HTMLInputElement
    const file = target.files?.[0]
    target.value = ''
    if (!file) return
    busy.value = kind
    try {
      const creating = !options.template.value
      const template = await ensure()
      if (!template) return
      options.changed(await queued(() => uploadPromptFile(template.id, kind, file)))
      ElMessage.success(creating ? `模板已保存，${UPLOADED[kind]}` : UPLOADED[kind])
    } catch (error) {
      ElMessage.error(errorMessage(error, '上传失败，请重试'))
    } finally {
      busy.value = null
    }
  }

  /** 删前确认，返回删没删。message 不传时按附件种类说明后果。 */
  async function remove(kind: PromptFileKind, message?: string): Promise<boolean> {
    const template = options.template.value
    if (!template) return false
    const text = message ?? (kind === 'excel'
      ? '删除后试发和样本试跑就没有数据可用，批量任务不受影响。'
      : '删除后模板不再提供这个码表，已发起的任务和线上版本不受影响。')
    const ok = await ElMessageBox.confirm(text, '删除已上传的文件？', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    }).then(() => true, () => false)
    if (!ok) return false
    busy.value = kind
    try {
      options.changed(await queued(() => deletePromptFile(template.id, kind)))
      return true
    } catch (error) {
      ElMessage.error(errorMessage(error, '删除失败，请重试'))
      return false
    } finally {
      busy.value = null
    }
  }

  async function download(kind: PromptFileKind): Promise<void> {
    const template = options.template.value
    if (!template) return
    try {
      await downloadPromptFile(template.id, kind, kind === 'excel' ? template.excel_name : codeDownloadName(template.code_name))
    } catch (error) {
      ElMessage.error(errorMessage(error, '下载失败，请重试'))
    }
  }

  /** 从数据库取来的样本写进模板测试 Excel，同样走 inTurn 串行队列并置 busy，避免与保存/上传/删除并发冲突。 */
  async function saveRows(body: { file_name: string; headers: string[]; rows: string[][] }): Promise<PromptTemplate> {
    const template = options.template.value
    if (!template) throw new Error('模板尚未创建')
    busy.value = 'excel'
    try {
      const updated = await queued(() => savePromptTestRows(template.id, body))
      options.changed(updated)
      return updated
    } finally {
      busy.value = null
    }
  }

  return { busy, accept: ACCEPT, bind, ensure, pick, received, remove, download, saveRows }
}

export type TemplateFiles = ReturnType<typeof useTemplateFiles>
