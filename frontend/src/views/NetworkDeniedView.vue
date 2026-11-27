<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { networkDeniedMessage } from '@/api/networkDenied'

/**
 * 限定公司网络的模块（智库）被拦下：不在公司网络、也没有自己的有效白名单。写清当前 IP，方便发给管理员开通；
 * 开通后点「重新打开」回到原来的页面。
 */
const route = useRoute()
const router = useRouter()

const message = computed(
  () => networkDeniedMessage.value || '这个模块只能在公司网络下访问。如需在其他地方使用，请把你当前的 IP 发给管理员开通访问白名单。',
)

function retry(): void {
  const raw = route.query.from
  const target = typeof raw === 'string' && raw.startsWith('/') && !raw.startsWith('//') ? raw : '/'
  void router.replace(target)
}
</script>

<template>
  <div class="status-view">
    <div class="status-view__card">
      <el-result
        icon="warning"
        title="当前网络不能访问"
        :sub-title="message"
      >
        <template #extra>
          <el-button
            type="primary"
            @click="retry"
          >
            重新打开
          </el-button>
        </template>
      </el-result>
    </div>
  </div>
</template>

<style scoped>
.status-view {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100dvh - 140px);
  padding: 24px;
}
.status-view__card {
  width: min(520px, 100%);
  padding: 16px 24px;
  border-radius: 16px;
  border: 1px solid var(--zt-border);
  background: var(--zt-panel);
  box-shadow: 0 12px 28px var(--zt-shadow-soft), var(--zt-shadow);
}
</style>
