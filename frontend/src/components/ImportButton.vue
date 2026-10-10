<script setup lang="ts">
import { Upload } from '@element-plus/icons-vue'

import { importUi } from '@/api/excelImport'

defineProps<{
  /** 悬停说明：去重口径、失败时整批退回还是逐行跳过。 */
  hint: string
  /** 交给 el-upload 的 before-upload，自己发请求并返回 false 阻止默认上传。 */
  upload: (file: File) => Promise<boolean> | boolean
}>()
</script>

<template>
  <el-upload
    :show-file-list="false"
    accept=".xlsx"
    :before-upload="upload"
  >
    <el-tooltip
      :content="hint"
      placement="bottom"
    >
      <el-button
        :icon="Upload"
        :disabled="importUi.visible"
      >
        上传 Excel
      </el-button>
    </el-tooltip>
  </el-upload>
</template>
