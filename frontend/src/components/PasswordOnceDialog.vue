<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  modelValue: boolean
  password: string
  username?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  cleared: []
}>()

const visible = ref(props.modelValue)

watch(
  () => props.modelValue,
  (value) => {
    visible.value = value
  },
)

function close() {
  visible.value = false
  emit('update:modelValue', false)
  emit('cleared')
}

async function copyPassword() {
  if (!props.password) {
    return
  }
  try {
    await navigator.clipboard.writeText(props.password)
    ElMessage.success('已复制，离开后将不再显示')
  } catch {
    ElMessage.error('复制失败，请手动选中密码复制')
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="请妥善保存临时密码"
    width="420px"
    :close-on-click-modal="false"
    @closed="close"
  >
    <p v-if="username">
      账号 <strong>{{ username }}</strong> 的临时密码仅展示这一次：
    </p>
    <el-input
      :model-value="password"
      readonly
    />
    <template #footer>
      <el-button @click="copyPassword">
        复制
      </el-button>
      <el-button
        type="primary"
        @click="close"
      >
        我已保存
      </el-button>
    </template>
  </el-dialog>
</template>
