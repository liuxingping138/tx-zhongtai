<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { errorMessage } from '@/api/errors'
import { getUserGrants, listResourceTree, replaceUserGrants } from '@/api/system'
import type { ResourceNode } from '@/api/types'
import { collectGrants } from '@/composables/useRoleGrants'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { LEVEL_TEXT, moduleGroups, moduleNames } from '@/permissions/catalog'
import { grantDiff, grantsFromTree, type GrantLevel } from '@/permissions/levels'
import {
  collapseScopeDiffs,
  isThinktankScopeCode,
  syncThinktankScopesWithMenu,
  thinktankLibraries,
  thinktankScopeNames,
} from '@/permissions/thinktankScopes'
import TableSkeleton from '@/components/TableSkeleton.vue'
import PermissionTable from '../roles/PermissionTable.vue'
import ThinktankDataScopePanel from '../roles/ThinktankDataScopePanel.vue'

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
const activeTab = ref<'menu' | 'data-scopes'>('menu')

const groups = computed(() => moduleGroups(tree.value))
const thinktankLibs = computed(() => thinktankLibraries(tree.value))
const names = computed(() => ({
  ...moduleNames(groups.value),
  ...thinktankScopeNames(thinktankLibs.value),
}))
const changes = computed(() =>
  collapseScopeDiffs(
    thinktankLibs.value,
    grantDiff(grantsFromTree(tree.value, original.value), grantsFromTree(tree.value, selected.value)),
  ),
)
const opened = computed(
  () =>
    Object.entries(selected.value).filter(([code, level]) => level !== 'NONE' && !isThinktankScopeCode(code)).length,
)

function updateSelected(next: Grants): void {
  selected.value = syncThinktankScopesWithMenu(thinktankLibs.value, selected.value, next)
}

let loadSeq = 0
const { markSaved, close: closeDrawer, beforeClose } = useUnsavedForm(visible, () => selected.value, saving)

async function load(): Promise<void> {
  const target = props.user
  if (!target) return
  const seq = ++loadSeq
  loading.value = true
  loadError.value = ''
  try {
    const [resources, current] = await Promise.all([
      tree.value.length ? { tree: tree.value } : listResourceTree(),
      getUserGrants(target.id),
    ])
    if (seq !== loadSeq) return
    tree.value = resources.tree
    const saved: Grants = {}
    for (const grant of current.grants) saved[grant.resource_code] = grant.level
    selected.value = collectGrants(tree.value, saved)
    original.value = { ...selected.value }
    version.value = current.version
    markSaved()
  } catch (error) {
    if (seq === loadSeq) loadError.value = errorMessage(error, '单独授权加载失败')
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

watch(visible, open => { if (open) void load() })

async function save(): Promise<void> {
  const user = props.user
  if (!user || saving.value || !changes.value.length) return
  const summary = changes.value
    .map(item => `${item.label ?? names.value[item.code] ?? item.code}：${LEVEL_TEXT[item.from]} → ${LEVEL_TEXT[item.to]}`)
    .join('\n')
  const sure = await ElMessageBox.confirm(summary, `给「${user.display_name}」单独授权，共 ${changes.value.length} 项修改？`, {
    type: 'warning',
    confirmButtonText: '保存',
    cancelButtonText: '再看看',
    customClass: 'confirm-lines',
  }).then(() => true, () => false)
  if (!sure) return
  saving.value = true
  try {
    const result = await replaceUserGrants(user.id, grantsFromTree(tree.value, selected.value), version.value)
    original.value = { ...selected.value }
    version.value = result.version
    markSaved()
    ElMessage.success('单独授权已保存，对方下次操作时即生效')
    emit('saved', { count: opened.value, version: result.version })
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
    v-model="visible"
    :title="user ? `单独授权：${user.display_name}（${user.username}）` : '单独授权'"
    size="min(980px, 100vw)"
    append-to-body
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    :before-close="beforeClose"
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
    <TableSkeleton
      v-if="loading && !tree.length"
      :columns="4"
    />
    <div
      v-else
      class="grants__table"
      :class="{ 'is-refreshing': loading }"
    >
      <el-tabs
        v-if="tree.length"
        v-model="activeTab"
      >
        <el-tab-pane
          name="menu"
          label="菜单权限"
        >
          <PermissionTable
            :model-value="selected"
            :groups="groups"
            :original="original"
            :disabled="saving"
            @update:model-value="updateSelected"
          />
        </el-tab-pane>
        <el-tab-pane
          name="data-scopes"
          label="智库数据权限"
        >
          <ThinktankDataScopePanel
            :libraries="thinktankLibs"
            :model-value="selected"
            :original="original"
            :disabled="saving"
            @update:model-value="updateSelected"
          />
        </el-tab-pane>
      </el-tabs>
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
        @click="closeDrawer"
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
