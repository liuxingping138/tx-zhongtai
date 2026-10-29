/** 用户列表的彩色头像：取显示名第一个字（英文转大写），颜色按用户 ID 固定，换页、刷新都不变。 */

export const AVATAR_TONES = 6

export function avatarText(user: { display_name: string; username: string }): string {
  const name = user.display_name.trim() || user.username.trim()
  return (Array.from(name)[0] ?? '?').toUpperCase()
}

export function avatarTone(id: string): number {
  let hash = 0
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return (hash % AVATAR_TONES) + 1
}
