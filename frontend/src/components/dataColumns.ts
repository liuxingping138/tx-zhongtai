export interface DataColumn {
  prop: string
  label: string
  /** Original business label, retained for tooltips and full record details. */
  fullLabel?: string
  width?: number
  minWidth?: number
  /** Relative weight for readable text columns to absorb available space. */
  grow?: number
  wrap?: boolean
  time?: boolean
  link?: boolean
  /**
   * 同一格里分两行显示的下级字段：上面一行是本列（如一级行业），下面浅色小字是这几列用 › 连起来（二级 › 三级）。
   * 列表只出这一列，列设置里也只有这一项；详情、编辑、导出仍按各自的字段。
   */
  stack?: string[]
  /** AI 打标写入的列：表头淡紫底、列名前「AI」标记，让人一眼分出哪些要核对。 */
  ai?: boolean
}
