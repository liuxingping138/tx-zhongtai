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
}
