<script setup lang="ts">
import { ElMessage, type FormInstance } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { errorMessage } from '@/api/errors'
import {
  createIpWhitelist,
  searchWhitelistUsers,
  updateIpWhitelist,
  type IpWhitelistItem,
  type WhitelistUser,
} from '@/api/ipWhitelist'
import { useFieldValidation } from '@/composables/useFieldValidation'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import {
  EXPIRY_CHOICES,
  expiryDate,
  expiryError,
  formatBeijing,
  type ExpiryChoice,
  type ExpiryForm,
} from './whitelistView'

/** 给某个人开通 / 修改一条白名单：选人、填他发来的 IP、定有效期。修改主要用来续期。 */
const props = defineProps<{
  item: IpWhitelistItem | null
  /** 新增时预填（如管理员给自己当前的 IP 开通） */
  presetUser?: WhitelistUser | null
  presetIp?: string
  maxDays: number
}>()

const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ saved: [] }>()

const form = reactive({ user_id: '', ip_range: '', reason: '' })
const expiry = reactive<ExpiryForm>({ choice: '2h', amount: null, unit: 'hour', datetime: '', current: '' })
const formRef = ref<FormInstance>()
const saving = ref(false)
const submitError = ref('')
const userOptions = ref<WhitelistUser[]>([])
const searching = ref(false)
const validation = useFieldValidation(form, formRef)
const guard = useUnsavedForm(visible, () => ({ ...form, ...expiry }), saving)
// 有效期不在 form 里，改了要自己清掉它的错误
watch(expiry, () => {
  delete validation.errors.expiry
})

const isEdit = computed(() => props.item !== null)
const title = computed(() => (isEdit.value ? '修改白名单' : '开通白名单'))
const choices = computed<{ value: ExpiryChoice; label: string }[]>(() =>
  isEdit.value ? [{ value: 'keep', label: '保持不变' }, ...EXPIRY_CHOICES] : EXPIRY_CHOICES,
)
const preview = computed(() => {
  const end = expiryDate(expiry)
  return end ? `到期时间：${formatBeijing(end)}（北京时间）` : ''
})

function fillForm(item: IpWhitelistItem | null): void {
  const user = item ? item.user : (props.presetUser ?? null)
  userOptions.value = user ? [user] : []
  form.user_id = user ? user.id : ''
  form.ip_range = item ? item.ip_range : (props.presetIp ?? '')
  form.reason = item ? item.reason : ''
  Object.assign(expiry, {
    choice: item ? 'keep' : '2h',
    amount: null,
    unit: 'hour',
    datetime: '',
    current: item ? item.expires_at : '',
  })
}

watch(visible, (open) => {
  if (!open) return
  submitError.value = ''
  fillForm(props.item)
  void validation.validate({})
  guard.markSaved()
})

async function searchUsers(keyword: string): Promise<void> {
  searching.value = true
  try {
    const result = await searchWhitelistUsers(keyword)
    userOptions.value = result.items
  } catch (error) {
    submitError.value = errorMessage(error, '用户列表加载失败')
  } finally {
    searching.value = false
  }
}

function disabledDate(day: Date): boolean {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  return day < start || day.getTime() > Date.now() + props.maxDays * 86_400_000
}

function fieldErrors(): Record<string, string> {
  return {
    user_id: form.user_id ? '' : '请选择用户',
    ip_range: form.ip_range.trim() ? '' : '请填写 IP 地址',
    expiry: expiryError(expiry, props.maxDays),
  }
}

async function onSubmit(): Promise<void> {
  if (saving.value) return
  submitError.value = ''
  if (!await validation.validate(fieldErrors())) return
  const end = expiryDate(expiry)
  if (!end) return
  saving.value = true
  const payload = {
    user_id: form.user_id,
    ip_range: form.ip_range.trim(),
    reason: form.reason.trim(),
    expires_at: end.toISOString(),
  }
  try {
    if (props.item) await updateIpWhitelist(props.item.id, payload)
    else await createIpWhitelist(payload)
    guard.markSaved()
    visible.value = false
    ElMessage.success(isEdit.value ? '已保存' : '已开通，对方刷新页面即可使用')
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
    width="560px"
  >
    <p class="editor-help">
      对方在公司网络以外打开智库被拦时，页面上会显示他的 IP。按他发来的 IP 给他本人开通，只对这个账号生效，到期自动失效。
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
        label="用户"
        required
        :error="validation.errors.user_id"
      >
        <el-select
          v-model="form.user_id"
          filterable
          remote
          :remote-method="searchUsers"
          :loading="searching"
          placeholder="输入姓名或账号搜索"
          class="whitelist-full"
          aria-label="用户"
          @visible-change="(open: boolean) => open && userOptions.length <= 1 && searchUsers('')"
        >
          <el-option
            v-for="user in userOptions"
            :key="user.id"
            :label="`${user.display_name}（${user.username}）`"
            :value="user.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item
        label="IP 地址"
        required
        :error="validation.errors.ip_range"
      >
        <el-input
          v-model="form.ip_range"
          maxlength="64"
          placeholder="对方发来的 IP，如 120.246.18.210；也可写不宽于 /24 的网段"
          :aria-invalid="Boolean(validation.errors.ip_range)"
        />
      </el-form-item>
      <el-form-item
        label="有效期"
        required
        :error="validation.errors.expiry"
      >
        <div class="whitelist-expiry">
          <el-radio-group
            v-model="expiry.choice"
            aria-label="有效期"
            class="whitelist-expiry__choices"
          >
            <el-radio-button
              v-for="option in choices"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </el-radio-button>
          </el-radio-group>
          <div
            v-if="expiry.choice === 'duration'"
            class="whitelist-expiry__custom"
          >
            <el-input-number
              v-model="expiry.amount"
              :min="1"
              :max="expiry.unit === 'hour' ? maxDays * 24 : maxDays"
              :precision="0"
              placeholder="时长"
              aria-label="时长"
            />
            <el-select
              v-model="expiry.unit"
              class="whitelist-expiry__unit"
              aria-label="单位"
            >
              <el-option
                label="小时"
                value="hour"
              />
              <el-option
                label="天"
                value="day"
              />
            </el-select>
          </div>
          <el-date-picker
            v-if="expiry.choice === 'datetime'"
            v-model="expiry.datetime"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss"
            format="YYYY-MM-DD HH:mm"
            placeholder="选择到期时间（北京时间）"
            :disabled-date="disabledDate"
            aria-label="到期时间"
          />
          <span class="whitelist-expiry__hint">
            {{ preview || '选好有效期后这里显示到期时间' }}。最短 10 分钟，一次最多 {{ maxDays }} 天。
          </span>
        </div>
      </el-form-item>
      <el-form-item label="开通原因">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          maxlength="500"
          show-word-limit
          placeholder="如：出差、居家办公、临时外出"
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
.whitelist-full { width: 100%; }
.whitelist-expiry {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
}
.whitelist-expiry__choices { flex-wrap: wrap; row-gap: 6px; }
.whitelist-expiry__custom { display: flex; align-items: center; gap: 8px; }
.whitelist-expiry__unit { width: 96px; }
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
