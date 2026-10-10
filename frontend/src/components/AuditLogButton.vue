<script setup lang="ts">
import { Clock } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

/** 跳到操作日志并按本模块筛选；没有操作日志查看权限时不显示。 */
const props = defineProps<{ module: string }>()
const auth = useAuthStore()
const router = useRouter()
const visible = computed(() => auth.canRead('system.audit'))

function open() {
  void router.push({ name: 'system-audit', query: { module_code: props.module } })
}
</script>

<template>
  <el-button
    v-if="visible"
    :icon="Clock"
    @click="open"
  >
    操作记录
  </el-button>
</template>
