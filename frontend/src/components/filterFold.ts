/** 筛选框在筛选区里的位置：top、height 相对筛选区，filled 表示框里已经填了值。 */
export interface FilterFieldBox {
  top: number
  height: number
  filled: boolean
}

export interface FilterFold {
  /** 落在第一行之后、收起时要藏起来的框的下标。 */
  folded: number[]
  /** 收起的框里填了值的个数，显示在「展开」旁边，免得条件藏起来没人看见。 */
  foldedFilled: number
  /** 第一行底边到筛选区顶部的距离，收起时按它截高度。 */
  firstRowBottom: number
}

/**
 * 一行能放几个框由屏幕宽度决定，所以按实际排版判断：底边比第一个框低的就在第一行之后。
 * 同一行的框底边对齐（有的框没有标题会矮一截），所以比底边不比顶边。
 */
export function foldFilterFields(fields: readonly FilterFieldBox[]): FilterFold {
  const first = fields[0]
  if (!first) return { folded: [], foldedFilled: 0, firstRowBottom: 0 }
  const firstRowBottom = first.top + first.height
  const folded = fields.flatMap((field, index) => field.top + field.height > firstRowBottom + 1 ? [index] : [])
  return {
    folded,
    foldedFilled: folded.filter(index => fields[index]!.filled).length,
    firstRowBottom,
  }
}
