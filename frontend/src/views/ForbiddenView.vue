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
</template>
