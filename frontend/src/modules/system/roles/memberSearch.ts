/**
 * 角色「添加成员」的候选人查询。按关键词搜：后端同时匹配用户名、显示名（也包括电话、邮箱），
 * 输中文名也搜得到；原来只按用户名搜，输「张三」什么都出不来。不输入时列出最近建的 50 个账号。
 */
export function memberSearchParams(keyword: string): { page: number; page_size: number; keyword?: string[] } {
  const text = keyword.trim()
  return text ? { page: 1, page_size: 50, keyword: [text] } : { page: 1, page_size: 50 }
}
