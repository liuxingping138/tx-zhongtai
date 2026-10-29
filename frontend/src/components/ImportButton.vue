<script setup lang="ts">
import { Upload } from '@element-plus/icons-vue'

import { importUi } from '@/api/excelImport'

defineProps<{
  /** 悬停说明：去重口径、失败时整批退回还是逐行跳过。 */
  hint: string
  /** 交给 el-upload 的 before-upload，自己发请求并返回 false 阻止默认上传。 */
  upload: (file: File) => Promise<boolean> | boolean
  /** 当前角色上传必定失败的原因（如缺另一个模块的权限）：按钮禁用，悬停显示原因而不是用法。 */
  blocked?: string
}>()
</script>

<template>
  <el-upload
    :show-file-list="false"
    accept=".xlsx"
    :before-upload="upload"
    :disabled="Boolean(blocked)"
  >
    <el-tooltip
      :content="blocked || hint"
      placement="bottom"
    >
      <el-button
        :icon="Upload"
        :disabled="importUi.visible || Boolean(blocked)"
      >
        导入
      </el-button>
    </el-tooltip>
  </el-upload>
</template>
