<script setup lang="ts">
import { Download } from '@element-plus/icons-vue'

/** 导出单独一档：只读角色能看不能导，按钮保留但禁用并说明原因。 */
withDefaults(defineProps<{
  allowed: boolean
  loading: boolean
  /** 有权限但暂时不能导出（如列表为空）时置为 true。 */
  disabled?: boolean
  hint?: string
}>(), {
  disabled: false,
  hint: '按当前已生效的筛选条件下载；未筛选时下载全表。',
})
defineEmits<{ click: [] }>()
const NO_EXPORT_HINT = '你的角色没有导出权限，如需下载 Excel 请联系管理员开通「导出」。'
</script>

<template>
  <el-tooltip
    :content="allowed ? hint : NO_EXPORT_HINT"
    placement="bottom"
  >
    <span>
      <el-button
        :icon="Download"
        :loading="loading"
        :disabled="!allowed || disabled"
        @click="$emit('click')"
      >
        <slot>下载 Excel</slot>
      </el-button>
    </span>
  </el-tooltip>
</template>
