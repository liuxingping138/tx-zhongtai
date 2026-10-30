<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'

/** 依赖服务暂时不可用：部署时 IAM 重启那十几秒里刷新页面会到这里，会话还在，点重试回到原来的页面。 */
const route = useRoute()
const router = useRouter()

function retry(): void {
  const target = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/'
  void router.replace(target)
}
</script>

<template>
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
</template>
