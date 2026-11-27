<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { errorMessage } from '@/api/errors'
import { getUserGrants, listResourceTree, replaceUserGrants } from '@/api/system'
import type { ResourceNode } from '@/api/types'
import { collectGrants } from '@/composables/useRoleGrants'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { formatGrantLevel, isThinktankDownloadCode, moduleGroups, moduleNames } from '@/permissions/catalog'
import { grantDiff, grantsFromTree, type GrantLevel } from '@/permissions/levels'
import {
  buildScopeBadges,
  collapseScopeDiffs,
  findIncompleteThinktankLibraries,
  isThinktankScopeCode,
  splitGrantDiffs,
  syncThinktankScopesWithMenu,
  thinktankLibraries,
  thinktankScopeNames,
} from '@/permissions/thinktankScopes'
import TableSkeleton from '@/components/TableSkeleton.vue'
import PermissionTable from '../roles/PermissionTable.vue'
import RoleGrantDiffDialog from '../roles/RoleGrantDiffDialog.vue'
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
const scopeFocusLib = ref('')
const diffDialogVisible = ref(false)

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
const scopeBadges = computed(() => buildScopeBadges(thinktankLibs.value, selected.value))
const splitDiffs = computed(() => splitGrantDiffs(thinktankLibs.value, changes.value))
const opened = computed(
  () =>
    Object.entries(selected.value).filter(
      ([code, level]) => level !== 'NONE' && !isThinktankScopeCode(code) && !isThinktankDownloadCode(code),
    ).length,
)

function onOpenScope(code: string): void {
  scopeFocusLib.value = code
  activeTab.value = 'data-scopes'
}

function updateSelected(next: Grants): void {
  selected.value = syncThinktankScopesWithMenu(thinktankLibs.value, selected.value, next)
}

function replaceSelected(next: Grants): void {
  selected.value = next
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

async function guardIncompleteScopes(): Promise<boolean> {
  const incomplete = findIncompleteThinktankLibraries(thinktankLibs.value, selected.value)
  if (!incomplete.length) return true
  const first = incomplete[0]!
  const namesText = incomplete.map(lib => `「${lib.name}」`).join('、')
  try {
    await ElMessageBox.confirm(
      `已开通${namesText}，但文件类型或行业类型尚未勾选任何项。保存后用户进入该库将看不到任何文件，建议先配置数据范围。`,
      '尚未选定智库数据范围',
      {
        type: 'warning',
        confirmButtonText: '去配置范围',
        cancelButtonText: '仍然保存',
        distinguishCancelAndClose: true,
      },
    )
    onOpenScope(first.code)
    return false
  } catch (action) {
    return action === 'cancel'
  }
}

async function save(): Promise<void> {
  const user = props.user
  if (!user || saving.value || !changes.value.length) return
  if (!await guardIncompleteScopes()) return
  const summary = changes.value
    .map(
      item =>
        `${item.label ?? names.value[item.code] ?? item.code}：${formatGrantLevel(item.code, item.from)} → ${formatGrantLevel(item.code, item.to)}`,
    )
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
        class="grants__tabs"
      >
        <el-tab-pane name="menu">
          <template #label>
            菜单权限<span
              v-if="splitDiffs.menuDiffs.length"
              class="grants__tab-badge"
              :title="`菜单与下载权限有 ${splitDiffs.menuDiffs.length} 项待保存修改`"
            >+{{ splitDiffs.menuDiffs.length }}</span>
          </template>
          <PermissionTable
            :model-value="selected"
            :groups="groups"
            :original="original"
            :disabled="saving"
            :scope-badges="scopeBadges"
            @update:model-value="updateSelected"
            @open-scope="onOpenScope"
          />
        </el-tab-pane>
        <el-tab-pane name="data-scopes">
          <template #label>
            智库数据权限<span
              v-if="splitDiffs.scopeDiffs.length"
              class="grants__tab-badge"
              :title="`智库数据范围有 ${splitDiffs.scopeDiffs.length} 项待保存修改（整组同档位变化会自动合并计数）`"
            >+{{ splitDiffs.scopeDiffs.length }}</span>
          </template>
          <ThinktankDataScopePanel
            :libraries="thinktankLibs"
            :model-value="selected"
            :original="original"
            :disabled="saving"
            :initial-lib-code="scopeFocusLib"
            @update:model-value="replaceSelected"
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
        v-if="changes.length"
        size="small"
        link
        type="primary"
        :disabled="saving"
        @click="diffDialogVisible = true"
      >
        查看修改明细
      </el-button>
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
    <RoleGrantDiffDialog
      v-model="diffDialogVisible"
      :changes="changes"
      :names="names"
      :saving="saving"
      @save="save"
    />
  </el-drawer>
</template>

<style scoped>
.grants__hint { margin: 0 0 10px; color: var(--zt-ink-500); font-size: 12.5px; line-height: 1.55; }
.grants__table { --perm-sticky-top: -20px; min-height: 240px; }
.grants__tabs :deep(.el-tabs__header) { margin-bottom: 10px; }
.grants__tabs :deep(.el-tabs__content) { overflow: visible; }
.grants__tab-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 18px; height: 17px; margin-left: 6px; padding: 0 5px; border-radius: 999px; background: var(--zt-warning-soft); border: 1px solid var(--zt-warning-border); color: var(--zt-warning-text); font-size: 11px; font-weight: 600; line-height: 1; }
.grants__count { margin-right: auto; color: var(--zt-ink-500); font-size: 13px; }
</style>

<style>
.grants-drawer .el-drawer__footer { display: flex; align-items: center; }
</style>
