import { ref } from 'vue'

import { NETWORK_DENIED_CODE } from './ipWhitelist'
import type { ApiError } from './types'

/** 最近一次被网络限制拦下时后端给的说明（里面带着当前 IP），说明页拿来展示。 */
export const networkDeniedMessage = ref('')

/** 是不是「限定公司网络的模块，不在公司网络、也没有自己的有效白名单」的 403；是就记下说明。 */
export function noteNetworkDenied(error: ApiError | undefined): boolean {
  if (!error || error.status !== 403 || error.code !== NETWORK_DENIED_CODE) return false
  networkDeniedMessage.value = error.message
  return true
}
