/** 和 iam-service `validate_password_policy` 同一套规则：至少 8 位，同时有字母和数字。 */
export function passwordError(password: string): string {
  if (password.length < 8) return '新密码至少 8 位'
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return '新密码要同时包含字母和数字'
  return ''
}
