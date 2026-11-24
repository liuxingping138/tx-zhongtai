import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import type { PromptTemplate } from '@/api/ai'

const message = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
const confirm = vi.hoisted(() => vi.fn<() => Promise<unknown>>())
const api = vi.hoisted(() => ({ uploadPromptFile: vi.fn(), deletePromptFile: vi.fn(), savePromptTestRows: vi.fn() }))
const download = vi.hoisted(() => vi.fn())
vi.mock('element-plus', () => ({ ElMessage: message, ElMessageBox: { confirm } }))
vi.mock('@/api/ai', () => api)
vi.mock('../shared/downloads', () => ({ downloadPromptFile: download }))

import { codeDownloadName, useTemplateFiles } from './useTemplateFiles'

const saved = { id: 't1', excel_name: '样本.xlsx', code_name: '码表.txt' } as PromptTemplate

function setup(template: PromptTemplate | null = null, allowed = true) {
  const current = ref<PromptTemplate | null>(template)
  const canCreate = vi.fn(() => allowed)
  const create = vi.fn(() => { current.value = saved; return Promise.resolve(saved) })
  const changed = vi.fn()
  const files = useTemplateFiles({ template: current, canCreate, create, changed })
  const click = vi.fn()
  files.bind('excel')({ click })
  return { files, current, canCreate, create, changed, click }
}

function chosen(file?: File): Event {
  return { target: { files: file ? [file] : [], value: 'C:\\fakepath\\样本.xlsx' } } as unknown as Event
}

describe('模板附件：新模板上传时顺便保存', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.uploadPromptFile.mockResolvedValue({ ...saved, excel_rows: 3 })
    api.deletePromptFile.mockResolvedValue({ ...saved, code_name: '' })
  })

  it('还不能建模板（没起名字）就不弹文件框；能建或已有模板才弹', () => {
    const blocked = setup(null, false)
    blocked.files.pick('excel')
    expect(blocked.canCreate).toHaveBeenCalledOnce()
    expect(blocked.click).not.toHaveBeenCalled()

    const fresh = setup()
    fresh.files.pick('excel')
    expect(fresh.click).toHaveBeenCalledOnce()

    const existing = setup(saved, false)
    existing.files.pick('excel')
    expect(existing.canCreate).not.toHaveBeenCalled()
    expect(existing.click).toHaveBeenCalledOnce()
  })

  it('选好文件：新模板先存成模板再上传，一句话说清两件事；文件框清空能再选同一个文件', async () => {
    const { files, create, changed } = setup()
    const event = chosen(new File(['x'], '样本.xlsx'))
    await files.received('excel', event)
    expect(create).toHaveBeenCalledOnce()
    expect(api.uploadPromptFile).toHaveBeenCalledWith('t1', 'excel', expect.any(File))
    expect(changed).toHaveBeenCalledWith({ ...saved, excel_rows: 3 })
    expect(message.success).toHaveBeenCalledWith('模板已保存，测试样本已上传')
    expect((event.target as HTMLInputElement).value).toBe('')
    expect(files.busy.value).toBeNull()

    await files.received('code', chosen(new File(['x'], '码表.txt')))
    expect(create).toHaveBeenCalledOnce()
    expect(message.success).toHaveBeenLastCalledWith('码表已上传')
  })

  it('没选文件、保存失败时不上传；上传失败说清楚并恢复按钮', async () => {
    const { files, create } = setup()
    await files.received('excel', chosen())
    expect(create).not.toHaveBeenCalled()

    create.mockReturnValueOnce(Promise.resolve(null) as never)
    await files.received('excel', chosen(new File(['x'], '样本.xlsx')))
    expect(api.uploadPromptFile).not.toHaveBeenCalled()

    api.uploadPromptFile.mockRejectedValueOnce({})
    await files.received('excel', chosen(new File(['x'], '样本.xlsx')))
    expect(message.error).toHaveBeenCalledWith('上传失败，请重试')
    expect(files.busy.value).toBeNull()
  })

  it('ensure：已有模板直接用；没有时能建才建', async () => {
    expect(await setup(saved).files.ensure()).toEqual(saved)
    const blocked = setup(null, false)
    expect(await blocked.files.ensure()).toBeNull()
    expect(blocked.create).not.toHaveBeenCalled()
    expect(await setup().files.ensure()).toEqual(saved)
  })

  it('删除先确认，可以传自己的说明；取消、没有模板、删失败都算没删', async () => {
    const { files, changed } = setup(saved)
    confirm.mockResolvedValueOnce(true)
    expect(await files.remove('code', '不用码表要删掉已上传的「码表.txt」。')).toBe(true)
    expect(confirm).toHaveBeenCalledWith('不用码表要删掉已上传的「码表.txt」。', '删除已上传的文件？', expect.anything())
    expect(api.deletePromptFile).toHaveBeenCalledWith('t1', 'code')
    expect(changed).toHaveBeenCalledWith({ ...saved, code_name: '' })

    confirm.mockRejectedValueOnce('cancel')
    expect(await files.remove('excel')).toBe(false)
    expect(confirm).toHaveBeenLastCalledWith(expect.stringContaining('试发和样本试跑就没有数据可用'), '删除已上传的文件？', expect.anything())

    confirm.mockResolvedValueOnce(true)
    api.deletePromptFile.mockRejectedValueOnce({})
    expect(await files.remove('excel')).toBe(false)
    expect(message.error).toHaveBeenCalledWith('删除失败，请重试')

    expect(await setup().files.remove('excel')).toBe(false)
  })

  it('下载用上传时的文件名；下载失败说清楚', async () => {
    const { files } = setup(saved)
    await files.download('excel')
    await files.download('code')
    expect(download.mock.calls).toEqual([['t1', 'excel', '样本.xlsx'], ['t1', 'code', '码表.txt']])
    download.mockRejectedValueOnce({})
    await files.download('excel')
    expect(message.error).toHaveBeenCalledWith('下载失败，请重试')
    await setup().files.download('excel')
    expect(download).toHaveBeenCalledTimes(3)
  })

  it('saveRows 走 inTurn 串行队列并更新模板，避免与保存并发撞版本号', async () => {
    const order: string[] = []
    const inTurn = async <T>(task: () => Promise<T>): Promise<T> => {
      order.push('queued')
      return task()
    }
    const current = ref<PromptTemplate | null>(saved)
    const changed = vi.fn()
    const files = useTemplateFiles({ template: current, canCreate: () => true, create: () => Promise.resolve(saved), changed, inTurn })
    const updated: PromptTemplate = { ...saved, excel_name: '数据库样本.xlsx', excel_rows: 10, version: 2 }
    api.savePromptTestRows.mockImplementationOnce(() => {
      order.push(`saveRows:${files.busy.value}`)
      return Promise.resolve(updated)
    })
    const payload = { file_name: '数据库样本.xlsx', headers: ['源ID'], rows: [['c1']] }
    expect(await files.saveRows(payload)).toEqual(updated)
    expect(files.busy.value).toBeNull()
    expect(order).toEqual(['queued', 'saveRows:excel'])
    expect(api.savePromptTestRows).toHaveBeenCalledWith('t1', payload)
    expect(changed).toHaveBeenCalledWith(updated)
  })
})

describe('码表下载的文件名', () => {
  it('文本照旧；Excel 上传的存的是转好的文字，下载回来叫 .txt', () => {
    expect(codeDownloadName('码表.txt')).toBe('码表.txt')
    expect(codeDownloadName('码表.CSV')).toBe('码表.CSV')
    expect(codeDownloadName('行业场景.xlsx')).toBe('行业场景.txt')
  })
})
