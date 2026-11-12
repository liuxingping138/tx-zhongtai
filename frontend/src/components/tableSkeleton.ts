export const SKELETON_COLUMN_WIDTHS = ['72%', '45%', '85%', '60%', '50%', '68%', '40%', '78%']

export function getSkeletonBarWidth(rowIndex: number, colIndex: number): string {
  const index = (rowIndex + colIndex) % SKELETON_COLUMN_WIDTHS.length
  return SKELETON_COLUMN_WIDTHS[index] ?? '65%'
}
