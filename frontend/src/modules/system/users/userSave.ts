import { errorMessage, isApiError } from '@/api/errors'

/**
 * 用户详情保存失败时的说明。先存基本信息、再存角色：第一步存上了、第二步没存上时要说清楚，
 * 不然用户以为都没存，改回去再点保存还会被版本号拦下。
 */
export function saveFailureText(error: unknown, infoSaved: boolean): string {
  const reason = isApiError(error) && error.status === 409
    ? '该用户刚被其他人修改过，请关闭后重新打开再改。'
    : errorMessage(error, '保存失败，请检查后重试')
  return infoSaved ? `基本信息已保存，角色没保存：${reason}` : reason
}
