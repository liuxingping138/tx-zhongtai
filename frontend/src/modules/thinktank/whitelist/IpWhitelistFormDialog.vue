<script setup lang="ts">
import { ElMessage, type FormInstance } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { errorMessage } from '@/api/errors'
import { createIpWhitelist, updateIpWhitelist, type IpWhitelistItem } from '@/api/thinktankAccess'
import { useFieldValidation } from '@/composables/useFieldValidation'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { EXPIRY_PRESETS, parseBeijing, presetExpiry, type ExpiryPreset } from './whitelistView'

/** 开通 / 修改一条白名单。修改主要用来续期：到期时间可以重新选。 */
const props = defineProps<{
  item: IpWhitelistItem | null
  /** 新增时预填的 IP（如管理员自己当前的 IP） */
  presetIp?: string
  maxDays: number
}>()

const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ saved: [] }>()

const form = reactive<{ ip_range: string; holder: string; reason: string; preset: ExpiryPreset; custom: string }>({
  ip_range: '',
  holder: '',
  reason: '',
  preset: '7d',
  custom: '',
})
const formRef = ref<FormInstance>()
const saving = ref(false)
const submitError = ref('')
const validation = useFieldValidation(form, formRef)
const guard = useUnsavedForm(visible, () => form, saving)

const isEdit = computed(() => props.item !== null)
const title = computed(() => (isEdit.value ? '修改白名单' : '开通白名单'))

function fillForm(item: IpWhitelistItem | null): void {
  form.ip_range = item ? item.ip_range : (props.presetIp ?? '')
  form.holder = item ? item.holder : ''
  form.reason = item ? item.reason : ''
  form.preset = item ? 'custom' : '7d'
  form.custom = item ? item.expires_at : ''
}

watch(visible, (open) => {
  if (!open) return
  submitError.value = ''
  fillForm(props.item)
  void validation.validate({})
  guard.markSaved()
})

function disabledDate(day: Date): boolean {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  return day < start || day.getTime() > Date.now() + props.maxDays * 86_400_000
}

function expiryValue(): string {
  return form.preset === 'custom' ? form.custom : presetExpiry(form.preset)
}

function fieldErrors(): Record<string, string> {
  const custom = parseBeijing(form.custom)
  let expires = ''
  if (form.preset === 'custom' && !custom) expires = '请选择到期时间'
  else if (form.preset === 'custom' && custom && custom.getTime() <= Date.now()) expires = '到期时间要晚于现在'
  return {
    ip_range: form.ip_range.trim() ? '' : '请填写 IP 地址',
    holder: form.holder.trim() ? '' : '请填写使用人',
    custom: expires,
  }
}

async function onSubmit(): Promise<void> {
  if (saving.value) return
  submitError.value = ''
  if (!await validation.validate(fieldErrors())) return
  saving.value = true
  const payload = {
    ip_range: form.ip_range.trim(),
    holder: form.holder.trim(),
    reason: form.reason.trim(),
    expires_at: expiryValue(),
  }
  try {
    if (props.item) await updateIpWhitelist(props.item.id, payload)
    else await createIpWhitelist(payload)
    guard.markSaved()
    visible.value = false
    ElMessage.success(isEdit.value ? '已保存' : '已开通，对方刷新页面即可使用智库')
    emit('saved')
  } catch (error) {
    submitError.value = errorMessage(error, '保存失败，请检查后重试')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    class="editor-overlay"
    :before-close="guard.beforeClose"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    :title="title"
    width="520px"
  >
    <p class="editor-help">
      公司网络以外的地方要用智库，按对方的公网 IP 开通，到期自动失效。对方打开智库被拦时，页面上会显示他的 IP。
    </p>
    <el-form
      ref="formRef"
      novalidate
      :disabled="saving"
      label-position="top"
      @submit.prevent="onSubmit"
    >
      <el-alert
        v-if="submitError"
        :title="submitError"
        type="error"
        show-icon
        :closable="false"
        class="form-submit-error"
      />
      <el-form-item
        label="IP 地址"
        required
        :error="validation.errors.ip_range"
      >
        <el-input
          v-model="form.ip_range"
          maxlength="64"
          placeholder="如 120.246.18.210，也可写不宽于 /24 的网段"
          :aria-invalid="Boolean(validation.errors.ip_range)"
        />
      </el-form-item>
      <el-form-item
        label="使用人"
        required
        :error="validation.errors.holder"
      >
        <el-input
          v-model="form.holder"
          maxlength="64"
          placeholder="谁在用这个 IP"
          :aria-invalid="Boolean(validation.errors.holder)"
        />
      </el-form-item>
      <el-form-item
        label="有效期"
        required
        :error="validation.errors.custom"
      >
        <div class="whitelist-expiry">
          <el-radio-group
            v-model="form.preset"
            aria-label="有效期"
          >
            <el-radio-button
              v-for="option in EXPIRY_PRESETS"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </el-radio-button>
          </el-radio-group>
          <el-date-picker
            v-if="form.preset === 'custom'"
            v-model="form.custom"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss"
            placeholder="选择到期时间（北京时间）"
            :disabled-date="disabledDate"
            aria-label="到期时间"
          />
          <span class="whitelist-expiry__hint">一次最多 {{ maxDays }} 天，到期后在这里续期。</span>
        </div>
      </el-form-item>
      <el-form-item label="开通原因">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          maxlength="500"
          show-word-limit
          placeholder="如：出差、居家办公"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="whitelist-dialog-footer">
        <span
          v-if="guard.dirty.value"
          class="editor-dirty"
          role="status"
        >有未保存的修改</span>
        <el-button
          :disabled="saving"
          @click="guard.close"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="onSubmit"
        >
          {{ isEdit ? '保存' : '开通' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.whitelist-expiry {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}
.whitelist-expiry__hint {
  color: var(--zt-ink-500);
  font-size: 12px;
}
.whitelist-dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}
</style>
