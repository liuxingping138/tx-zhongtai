import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'

export const TABLE_COLUMNS: DataColumn[] = [
  { prop: 'seq_no', label: '序号', width: 80 },
  { prop: 'type_name', label: '政策类型', width: 160 },
  { prop: 'priority', label: '优先级', width: 80 },
  { prop: 'definition', label: '定义', minWidth: 360, grow: 1, wrap: true },
  { prop: 'created_at', label: '入库时间', time: true, width: 190 },
  { prop: 'created_by_name', label: '入库人', width: 120 },
  { prop: 'updated_at', label: '更新时间', time: true, width: 190 },
  { prop: 'updated_by_name', label: '操作人', width: 120 },
]

/** 窄屏卡片的摘要字段，也是列设置早期「精简默认列」的识别依据。 */
export const SUMMARY_KEYS = ['type_name', 'definition', 'updated_at']

export const EDITOR_GROUPS: EditorGroup[] = [
  {
    title: '类型信息',
    hint: '政策类型为必填项，序号可按现有码表约定填写。',
    fields: [
      { key: 'seq_no', label: '序号', maxLength: 32 },
      { key: 'type_name', label: '政策类型', required: true, maxLength: 64 },
      {
        key: 'priority',
        label: '优先级',
        maxLength: 8,
        hint: '如 P0、P1、P2，P0 最先。AI 给政策打类型时，多个类型同时命中按它排序。',
      },
      { key: 'definition', label: '定义', long: true, hint: '说明此类型的含义和适用范围，方便团队统一理解。' },
    ],
  },
]
