<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { setSourcesCrawlerStatus } from '@/api/policy'
import { errorMessage } from '@/api/errors'
import { CRAWLER_STATUSES } from './fields'

/** 勾选的信源批量改爬虫状态。改成「已爬」的上线时间记为今天，改成别的不动上线时间。 */
const props = defineProps<{ ids: string[] }>()
const emit = defineEmits<{ done: [] }>()
const open = defineModel<boolean>({ required: true })
const status = ref(CRAWLER_STATUSES[1] ?? '')
const saving = ref(false)

watch(open, value => { if (value) status.value = CRAWLER_STATUSES[1] ?? '' })

async function submit(): Promise<void> {
  saving.value = true
  try {
    const result = await setSourcesCrawlerStatus(props.ids, status.value)
    const same = result.unchanged ? `，${result.unchanged} 个原本就是「${status.value}」` : ''
    ElMessage.success(`已改 ${result.updated} 个${same}`)
    open.value = false
    emit('done')
  } catch (error) {
    ElMessage.error(errorMessage(error, '修改失败，请重试'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="open"
    title="批量改爬虫状态"
    width="min(440px, calc(100vw - 32px))"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
  >
    <p class="batch-status__count">
      已勾选 {{ ids.length }} 个信源，爬虫状态改为：
    </p>
    <el-radio-group
      v-model="status"
      aria-label="爬虫状态"
    >
      <el-radio
        v-for="item in CRAWLER_STATUSES"
        :key="item"
        :value="item"
      >
        {{ item }}
      </el-radio>
    </el-radio-group>
    <p class="batch-status__hint">
      {{ status === '已爬' ? '原来不是已爬的，上线时间记为今天。' : '上线时间保持不变。' }}
    </p>
    <template #footer>
      <el-button
        :disabled="saving"
        @click="open = false"
      >
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        @click="submit"
      >
        确定修改
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.batch-status__count { margin: 0 0 12px; color: var(--zt-ink-900); }
.batch-status__hint { margin: 12px 0 0; color: var(--zt-ink-500); font-size: 13px; }
</style>
