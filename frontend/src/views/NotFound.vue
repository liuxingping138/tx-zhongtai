<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="status-view">
    <div class="status-view__card">
      <el-result
        icon="warning"
        title="404"
        sub-title="页面不存在"
      >
        <template #extra>
          <el-button
            type="primary"
            @click="router.replace('/')"
          >
            返回工作台
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
  width: min(460px, 100%);
  padding: 16px 24px;
  border-radius: 16px;
  border: 1px solid var(--zt-border);
  background: var(--zt-panel);
  box-shadow: 0 12px 28px var(--zt-shadow-soft), var(--zt-shadow);
}
</style>
