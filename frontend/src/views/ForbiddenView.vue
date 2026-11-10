<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import { useWorkspace } from '@/layouts/workspace'

const router = useRouter()
const { groups } = useWorkspace()
const home = computed(() => groups.value[0]?.entries[0])

function back() {
  if (home.value) void router.push(home.value.path)
}
</script>

<template>
  <div class="status-view">
    <div class="status-view__card">
      <el-result
        icon="warning"
        title="没有访问权限"
        sub-title="这个页面不在当前角色的菜单里。"
      >
        <template #extra>
          <el-button
            v-if="home"
            type="primary"
            @click="back"
          >
            返回{{ home.title }}
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
