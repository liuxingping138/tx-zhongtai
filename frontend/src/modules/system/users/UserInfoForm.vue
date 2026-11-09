<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { ManagedUser } from '@/api/system'

const props = defineProps<{
  user: ManagedUser
  canEdit: boolean
  saving: boolean
  saveError: string
}>()

const emit = defineEmits<{
  save: [form: { display_name: string; phone: string; email: string }]
}>()

const form = reactive({ display_name: '', phone: '', email: '' })

watch(() => props.user, (u) => {
  if (u) {
    form.display_name = u.display_name
    form.phone = u.phone ?? ''
    form.email = u.email ?? ''
  }
}, { immediate: true })

const dirty = computed(() =>
  form.display_name.trim() !== props.user.display_name
  || form.phone.trim() !== (props.user.phone ?? '')
  || form.email.trim() !== (props.user.email ?? ''),
)

function onCancel() {
  form.display_name = props.user.display_name
  form.phone = props.user.phone ?? ''
  form.email = props.user.email ?? ''
}

function onSubmit() {
  emit('save', {
    display_name: form.display_name.trim(),
    phone: form.phone.trim(),
    email: form.email.trim(),
  })
}
</script>

<template>
  <div class="user-info-pane">
    <el-alert
      v-if="saveError"
      :title="saveError"
      type="error"
      show-icon
      :closable="false"
      class="user-alert"
    />
    <el-form
      label-position="top"
      :disabled="saving || !canEdit"
      class="user-info-form"
      @submit.prevent="onSubmit"
    >
      <div class="user-form-grid">
        <el-form-item label="用户名">
          <el-input
            :model-value="user.username"
            disabled
          />
        </el-form-item>
        <el-form-item
          label="显示名"
          required
        >
          <el-input
            v-model="form.display_name"
            autocomplete="off"
            maxlength="128"
          />
        </el-form-item>
        <el-form-item label="电话">
          <el-input
            v-model="form.phone"
            autocomplete="off"
            inputmode="tel"
            maxlength="32"
            placeholder="11 位手机号，选填"
          />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input
            v-model="form.email"
            autocomplete="off"
            inputmode="email"
            maxlength="254"
            placeholder="选填"
          />
        </el-form-item>
      </div>
      <div
        v-if="canEdit && dirty"
        class="user-form-actions"
      >
        <span class="user-dirty-hint">有未保存的修改</span>
        <el-button
          :disabled="saving"
          @click="onCancel"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="onSubmit"
        >
          保存基本信息
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<style scoped>
.user-info-pane { display: flex; flex-direction: column; gap: 16px; }
.user-alert { margin-bottom: 8px; }
.user-info-form { display: flex; flex-direction: column; gap: 16px; }
.user-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 24px; }
.user-form-actions { display: flex; align-items: center; justify-content: flex-end; gap: 12px; margin-top: 12px; padding-top: 16px; border-top: 1px solid var(--zt-divider); }
.user-dirty-hint { margin-right: auto; color: var(--zt-warning-text); font-size: 13px; }
</style>
