<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'

/** 依赖服务暂时不可用：部署时 IAM 重启那十几秒里刷新页面会到这里，会话还在，点重试回到原来的页面。 */
const route = useRoute()
const router = useRouter()

function retry(): void {
  const raw = route.query.redirect
  const target = typeof raw === 'string' && raw.startsWith('/') && !raw.startsWith('//') ? raw : '/'
  void router.replace(target)
}
</script>

<template>
  <div class="status-view status-view--full">
    <div class="status-view__card">
      <el-result
        icon="error"
        title="服务不可用"
        sub-title="依赖服务暂时不可用，请稍后重试"
      >
        <template #extra>
          <el-button
            type="primary"
            @click="retry"
          >
            重试
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
  min-height: 100dvh;
  padding: 24px;
  background: var(--zt-soft);
}
.status-view__card {
  width: min(460px, 100%);
  padding: 16px 24px;
  border-radius: 16px;
  border: 1px solid var(--zt-border);
  background: var(--zt-panel);
  box-shadow: 0 12px 28px var(--zt-shadow-soft), var(--zt-shadow);
}
</style>
