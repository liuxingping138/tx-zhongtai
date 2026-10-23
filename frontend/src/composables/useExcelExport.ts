import { ElMessage } from 'element-plus'
import { ref } from 'vue'

import { downloadFile } from '@/api/download'
import { errorMessage } from '@/api/errors'

interface ExcelExportOptions {
  /** 导出接口路径，如 /policy/sources/export。 */
  path: string
  /** 下载的中文文件名；随页面状态变的（如带周次）传函数。 */
  filename: string | (() => string)
  /** 导出用的筛选条件：传已生效的 applied，不传用户还没点查询的输入。 */
  filters: () => Record<string, string | string[]>
}

/** 按当前已生效的筛选导出 Excel；导出进行中再次点击不会重复下载。 */
export function useExcelExport(options: ExcelExportOptions) {
  const exporting = ref(false)

  async function onExport(): Promise<void> {
    if (exporting.value) return
    exporting.value = true
    try {
      const filename = typeof options.filename === 'function' ? options.filename() : options.filename
      await downloadFile(options.path, filename, options.filters())
      ElMessage.success('下载已开始，请查看浏览器下载列表')
    } catch (error) {
      ElMessage.error(errorMessage(error, '下载失败，请重试'))
    } finally {
      exporting.value = false
    }
  }

  return { exporting, onExport }
}
