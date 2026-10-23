<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { offlinePrompt, publishPrompt, type PromptTemplate } from '@/api/ai'
import { errorMessage } from '@/api/errors'

/** 模板的上线状态和上线 / 下线按钮。定时任务只跑上线版本：之后改模板只改草稿，重新上线才生效。 */
/** fit：政策类模板放进三个打标任务的结论（如「可用于政策类型判断；不能用于政策解读」），上线确认里一并写明。 */
const props = defineProps<{ template: PromptTemplate; canRelease: boolean; dirty: boolean; fit?: string }>()
const emit = defineEmits<{ changed: [template: PromptTemplate] }>()
const busy = ref(false)

const release = computed(() => props.template.release)
const pending = computed(() => release.value?.unreleased_changes ?? [])
const status = computed(() => {
  if (!release.value) return { type: 'info' as const, text: '未上线' }
  if (pending.value.length) return { type: 'warning' as const, text: `第 ${release.value.release_no} 版已上线，草稿改了${pending.value.join('、')}，未上线` }
  return { type: 'success' as const, text: `第 ${release.value.release_no} 版已上线` }
})

async function confirm(message: string, title: string, action: string): Promise<boolean> {
  return ElMessageBox.confirm(message, title, { type: 'warning', confirmButtonText: action, cancelButtonText: '取消' }).then(() => true, () => false)
}

async function publish(): Promise<void> {
  if (props.dirty) {
    ElMessage.warning('有未保存的修改，先保存模板再上线')
    return
  }
  // 后端也会拦；先在这里说，免得用户点完确认才被退回。
  if (!props.template.model_id) {
    ElMessage.warning('上线前要在模板上选定模型（标题下面的「模型」），定时任务不会替你挑')
    return
  }
  const next = (release.value?.release_no ?? 0) + 1
  const tip = release.value ? `第 ${next} 版会替换正在生效的第 ${release.value.release_no} 版，` : ''
  const fit = props.fit ? `定时任务适配：${props.fit}。` : ''
  if (!await confirm(`${tip}定时任务之后按这一版的提示词、输出字段、模型和码表跑真实数据，会产生模型费用。${fit}`, `上线第 ${next} 版？`, '上线')) return
  busy.value = true
  try {
    emit('changed', await publishPrompt(props.template.id))
    ElMessage.success(`第 ${next} 版已上线`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '上线失败，请重试'))
  } finally {
    busy.value = false
  }
}

async function takeOffline(): Promise<void> {
  if (!await confirm('下线后定时任务不再使用这个模板，历史版本保留，可以重新上线。', '下线模板？', '下线')) return
  busy.value = true
  try {
    emit('changed', await offlinePrompt(props.template.id))
    ElMessage.success('已下线')
  } catch (error) {
    ElMessage.error(errorMessage(error, '下线失败，请重试'))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="release-bar">
    <span
      class="release-bar__status"
      :class="`is-${status.type}`"
    >{{ status.text }}</span>
    <span
      v-if="release"
      class="release-bar__meta"
    >{{ release.released_by_name }} · {{ release.released_at }}</span>
    <span class="release-bar__spacer" />
    <template v-if="canRelease">
      <el-button
        v-if="release"
        size="small"
        :disabled="busy"
        @click="takeOffline"
      >
        下线
      </el-button>
      <el-button
        v-if="!release || pending.length"
        size="small"
        type="primary"
        plain
        :loading="busy"
        @click="publish"
      >
        {{ release ? '重新上线' : '上线' }}
      </el-button>
    </template>
  </div>
</template>

<style scoped>
.release-bar { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 8px; padding-left: 4px; }
.release-bar .el-button { margin: 0; }
.release-bar__meta { color: var(--zt-ink-500); font-size: 12px; }
.release-bar__spacer { display: none; }
.release-bar__status { display: inline-flex; align-items: center; gap: 6px; color: var(--zt-ink-700); font-size: 12px; }
.release-bar__status::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #b3bdca; }
.release-bar__status.is-success::before { background: #3d8c6e; }
.release-bar__status.is-warning::before { background: #c4842a; }
</style>
