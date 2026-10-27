<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheck, Warning } from '@element-plus/icons-vue'
import { downloadImportReport, importResultUi } from '@/api/excelImport'
const result = computed(() => importResultUi.result)
const hasReport = computed(() => Boolean(result.value?.report_blob || result.value?.skipped_file))
</script>
<template>
  <el-dialog
    v-model="importResultUi.visible"
    :title="result?.rejected ? '导入未通过校验' : '导入完成'"
    width="560px"
    class="import-result"
    :close-on-click-modal="false"
  >
    <template v-if="result">
      <div class="import-result__heading">
        <el-icon
          :class="result.rejected || result.skipped ? 'is-warning' : 'is-success'"
          :size="36"
        >
          <Warning v-if="result.rejected || result.skipped" /><CircleCheck v-else />
        </el-icon>
        <div><strong>{{ result.rejected ? '本次未写入数据' : result.skipped ? '已完成，有部分记录跳过' : '数据已成功导入' }}</strong><p>{{ importResultUi.sourceName }}</p></div>
      </div>
      <dl class="import-result__stats">
        <div><dt>总记录</dt><dd>{{ result.total }}</dd></div>
        <div><dt>新增</dt><dd>{{ result.inserted }}</dd></div>
        <div><dt>更新</dt><dd>{{ result.updated }}</dd></div>
        <div><dt>{{ result.rejected ? '校验问题' : '跳过' }}</dt><dd>{{ result.skipped }}</dd></div>
      </dl>
      <p class="import-result__hint">
        {{ result.rejected ? '请根据校验报告修正文件后重新上传；本次整批数据未入库。' : result.skipped ? '已写入符合要求的记录，重复或未通过校验的记录已跳过。' : '可关闭此窗口，查看和维护导入后的记录。' }}
      </p>
      <p
        v-if="hasReport"
        class="import-result__report"
      >
        {{ result.report_note || '校验报告已自动下载，也可以点击下方按钮再次下载。' }}
      </p>
    </template>
    <template #footer>
      <el-button
        v-if="hasReport"
        @click="downloadImportReport"
      >
        下载校验报告
      </el-button>
      <el-button
        type="primary"
        @click="importResultUi.visible = false"
      >
        {{ result?.rejected ? '知道了' : '完成' }}
      </el-button>
    </template>
  </el-dialog>
</template>
<style scoped>
.import-result__heading { display: flex; align-items: center; gap: 14px; margin: 10px 0 24px; }
.import-result__heading strong { color: var(--zt-ink-900); font-size: 16px; }
.import-result__heading p { margin: 6px 0 0; color: var(--zt-ink-500); font-size: 12px; overflow-wrap: anywhere; }
.is-success { color: var(--zt-success-text); } .is-warning { color: var(--zt-warning-text); }
.import-result__stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 0; padding: 22px 12px; border-radius: 10px; background: var(--zt-soft); text-align: center; }
.import-result__stats dt { color: var(--zt-ink-500); font-size: 12px; }
.import-result__stats dd { margin: 9px 0 0; color: var(--zt-ink-900); font-size: 23px; font-weight: 650; }
.import-result__hint, .import-result__report { color: var(--zt-ink-500); font-size: 13px; line-height: 1.8; }
.import-result__hint { margin: 22px 0 0; }
.import-result__report { margin: 8px 0 0; }
</style>
