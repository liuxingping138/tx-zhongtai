<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { errorMessage } from '@/api/errors'
import { getUserGrants, listResourceTree, replaceUserGrants } from '@/api/system'
import type { ResourceNode } from '@/api/types'
import { collectGrants } from '@/composables/useRoleGrants'
import { LEVEL_TEXT, moduleGroups, moduleNames } from '@/permissions/catalog'
import { grantDiff, grantsFromTree, type GrantLevel } from '@/permissions/levels'
import PermissionTable from '../roles/PermissionTable.vue'

/**
 * 角色之外单独给一个人授权：和角色同一张「查看 / 导出 / 管理」勾选表。
 * 实际权限 = 这个人所有启用角色加这里，按模块取最高一档；「权限分配」锁着，只跟超级管理员角色走。
 */
type Grants = Record<string, GrantLevel>

const props = defineProps<{ user: { id: string; display_name: string; username: string } | null }>()
const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ saved: [result: { count: number; version: number }] }>()

const tree = ref<ResourceNode[]>([])
const selected = ref<Grants>({})
const original = ref<Grants>({})
const version = ref(0)
const loading = ref(false)
const saving = ref(false)
const loadError = ref('')

const groups = computed(() => moduleGroups(tree.value))
const names = computed(() => moduleNames(groups.value))
const changes = computed(() =>
  grantDiff(grantsFromTree(tree.value, original.value), grantsFromTree(tree.value, selected.value)),
)
const opened = computed(() => Object.values(selected.value).filter(level => level !== 'NONE').length)

async function load(): Promise<void> {
  if (!props.user) return
  loading.value = true
  loadError.value = ''
  try {
    const [resources, current] = await Promise.all([
      tree.value.length ? { tree: tree.value } : listResourceTree(),
      getUserGrants(props.user.id),
    ])
    tree.value = resources.tree
    const saved: Grants = {}
    for (const grant of current.grants) saved[grant.resource_code] = grant.level
    selected.value = collectGrants(tree.value, saved)
    original.value = { ...selected.value }
    version.value = current.version
  } catch (error) {
    loadError.value = errorMessage(error, '单独授权加载失败')
  } finally {
    loading.value = false
  }
}

watch(visible, open => { if (open) void load() })

async function close(): Promise<void> {
  if (changes.value.length) {
    const discard = await ElMessageBox.confirm('改了还没保存，关掉就不保存了。', '放弃修改？', {
      type: 'warning',
      confirmButtonText: '放弃修改',
      cancelButtonText: '继续编辑',
    }).then(() => true, () => false)
    if (!discard) return
  }
  visible.value = false
}

async function save(): Promise<void> {
  const user = props.user
  if (!user || saving.value || !changes.value.length) return
  const summary = changes.value
    .map(item => `${names.value[item.code] ?? item.code}：${LEVEL_TEXT[item.from]} → ${LEVEL_TEXT[item.to]}`)
    .join('\n')
  const sure = await ElMessageBox.confirm(summary, `给「${user.display_name}」单独授权，共 ${changes.value.length} 项修改？`, {
    type: 'warning',
    confirmButtonText: '保存',
    cancelButtonText: '再看看',
    customClass: 'grant-confirm',
  }).then(() => true, () => false)
  if (!sure) return
  saving.value = true
  try {
    const result = await replaceUserGrants(user.id, grantsFromTree(tree.value, selected.value), version.value)
    original.value = { ...selected.value }
    version.value = result.version
    ElMessage.success('单独授权已保存，对方下次操作时即生效')
    emit('saved', { count: result.grants.length, version: result.version })
    visible.value = false
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-drawer
    :model-value="visible"
    :title="user ? `单独授权：${user.display_name}（${user.username}）` : '单独授权'"
    size="min(980px, 100vw)"
    append-to-body
    :before-close="close"
    class="editor-overlay grants-drawer"
  >
    <p class="grants__hint">
      角色之外再给这个人的权限。这个人最终能做什么 = 其所有角色的权限加上这里，每个模块取最高一档；角色已经给到的不用再勾。
      要给多个人同样的权限，建一个角色更好管。
    </p>
    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
    />
    <div
      v-loading="loading"
      class="grants__table"
    >
      <PermissionTable
        v-if="tree.length"
        v-model="selected"
        :groups="groups"
        :original="original"
        :disabled="saving"
      />
    </div>
    <template #footer>
      <span class="grants__count">单独开通 {{ opened }} 个模块</span>
      <span
        v-if="changes.length"
        class="editor-dirty"
        role="status"
      >改了 {{ changes.length }} 处未保存</span>
      <el-button
        :disabled="saving"
        @click="close"
      >
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!changes.length"
        @click="save"
      >
        保存
      </el-button>
    </template>
  </el-drawer>
</template>

<style scoped>
.grants__hint { margin: 0 0 16px; color: var(--zt-ink-500); font-size: 13px; line-height: 1.7; }
.grants__table { min-height: 240px; }
.grants__count { margin-right: auto; color: var(--zt-ink-500); font-size: 13px; }
</style>

<style>
.grants-drawer .el-drawer__footer { display: flex; align-items: center; }
</style>
