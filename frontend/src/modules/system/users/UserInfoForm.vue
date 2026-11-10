<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Edit } from '@element-plus/icons-vue'
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

const editing = ref(false)
const form = reactive({ display_name: '', phone: '', email: '' })

watch(() => props.user, (u, prev) => {
  if (!u) return
  const switchedUser = prev && u.id !== prev.id
  if (switchedUser) editing.value = false
  if (!editing.value || switchedUser) {
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
  editing.value = false
}

function onSubmit() {
  emit('save', {
    display_name: form.display_name.trim(),
    phone: form.phone.trim(),
    email: form.email.trim(),
  })
}

watch(() => props.saving, (cur, prev) => {
  if (prev && !cur && !props.saveError) {
    editing.value = false
  }
})
</script>

<template>
  <div class="user-info-pane">
    <div class="user-info-head">
      <h3 class="user-info-title">
        基本资料
      </h3>
      <el-button
        v-if="canEdit && !editing"
        size="small"
        :icon="Edit"
        class="user-edit-btn"
        @click="editing = true"
      >
        编辑资料
      </el-button>
    </div>

    <el-alert
      v-if="saveError"
      :title="saveError"
      type="error"
      show-icon
      :closable="false"
      class="user-alert"
    />

    <!-- Google 风格只读展示 -->
    <div
      v-if="!editing"
      class="user-view"
    >
      <div class="user-kv-list">
        <div class="user-kv">
          <span class="user-kv__label">登录账号</span>
          <span class="user-kv__val user-kv__val--mono">{{ user.username }}</span>
        </div>
        <div class="user-kv">
          <span class="user-kv__label">用户姓名</span>
          <span class="user-kv__val">{{ user.display_name }}</span>
        </div>
        <div class="user-kv">
          <span class="user-kv__label">联系电话</span>
          <span class="user-kv__val">{{ user.phone || '未填写' }}</span>
        </div>
        <div class="user-kv">
          <span class="user-kv__label">电子邮箱</span>
          <span class="user-kv__val user-kv__val--email">{{ user.email || '未填写' }}</span>
        </div>
      </div>
    </div>

    <!-- 行内编辑表单 -->
    <el-form
      v-else
      label-position="top"
      :disabled="saving"
      class="user-info-form"
      @submit.prevent="onSubmit"
    >
      <div class="user-form-grid">
        <div class="user-form-grid__row">
          <el-form-item label="登录账号">
            <el-input
              :model-value="user.username"
              disabled
            />
          </el-form-item>
          <el-form-item
            label="用户姓名"
            required
          >
            <el-input
              v-model="form.display_name"
              autocomplete="off"
              maxlength="128"
            />
          </el-form-item>
        </div>
        <div class="user-form-grid__row">
          <el-form-item label="联系电话">
            <el-input
              v-model="form.phone"
              autocomplete="off"
              inputmode="tel"
              maxlength="32"
              placeholder="11 位手机号，选填"
            />
          </el-form-item>
          <el-form-item label="电子邮箱">
            <el-input
              v-model="form.email"
              autocomplete="off"
              inputmode="email"
              maxlength="254"
              placeholder="常用邮箱，选填"
            />
          </el-form-item>
        </div>
      </div>
      <div class="user-form-actions">
        <span
          v-if="dirty"
          class="user-dirty-hint"
        >未保存的修改</span>
        <el-button
          :disabled="saving"
          size="small"
          @click="onCancel"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          size="small"
          :loading="saving"
          @click="onSubmit"
        >
          保存
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<style scoped>
.user-info-pane { display: flex; flex-direction: column; gap: 12px; }
.user-info-head { display: flex; align-items: center; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid var(--zt-divider); }
.user-info-title { margin: 0; font-size: 15px; font-weight: 650; color: var(--zt-ink-900); }
.user-edit-btn { border-radius: 6px; }
.user-alert { margin-bottom: 4px; }

.user-view { display: flex; flex-direction: column; }
.user-kv-list { display: flex; flex-direction: column; }
.user-kv { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 0; border-bottom: 1px solid var(--zt-divider); font-size: 13px; }
.user-kv:last-child { border-bottom: none; padding-bottom: 2px; }
.user-kv__label { color: var(--zt-ink-500); flex-shrink: 0; font-size: 12.5px; }
.user-kv__val { color: var(--zt-ink-900); font-weight: 500; text-align: right; word-break: break-all; }
.user-kv__val--mono { font-family: var(--zt-font-mono, monospace); }
.user-kv__val--email { color: var(--zt-primary-text); }

.user-info-form { display: flex; flex-direction: column; gap: 10px; }
.user-form-grid { display: flex; flex-direction: column; gap: 10px; }
.user-form-grid__row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.user-form-grid :deep(.el-form-item) { margin-bottom: 0; }
.user-form-grid :deep(.el-form-item__label) { padding-bottom: 4px; font-size: 12.5px; color: var(--zt-ink-600); line-height: 1.3; }
.user-form-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 6px; padding-top: 10px; border-top: 1px solid var(--zt-divider); }
.user-dirty-hint { margin-right: auto; color: var(--zt-warning-text); font-size: 12px; }
</style>
