<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CopyDocument, EditPen } from '@element-plus/icons-vue'

import { updateRole } from '@/api/system'
import { errorMessage } from '@/api/errors'
import type { RoleItem } from '@/api/types'
import { useRoleGrants } from '@/composables/useRoleGrants'
import { SUPERADMIN_ROLE_CODE } from '@/permissions/catalog'
import { buildScopeBadges, splitGrantDiffs } from '@/permissions/thinktankScopes'
import DetailSkeleton from '@/components/DetailSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import PermissionTable from './PermissionTable.vue'
import RoleFormDialog, { type RoleFormMode } from './RoleFormDialog.vue'
import RoleGrantDiffDialog from './RoleGrantDiffDialog.vue'
import RoleMembersPanel from './RoleMembersPanel.vue'
import ThinktankDataScopePanel from './ThinktankDataScopePanel.vue'

/**
 * 角色详情：嵌在「角色与权限」右侧。上面是角色信息，下面分「菜单权限」「智库数据权限」「成员」三个页签。
 * 名称、状态、成员数、权限变化后通知左侧列表刷新。授权草稿和保存在 useRoleGrants。
 */
const emit = defineEmits<{ changed: [] }>()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const canManageRoles = computed(() => auth.canFull('system.roles'))
const canSeeGrants = computed(() => auth.canRead('system.permissions'))
const canGrant = computed(() => auth.canFull('system.permissions'))

const roleId = computed(() => String(route.params.roleId ?? ''))
function initialTab(): 'grants' | 'data-scopes' | 'members' {
  if (!canSeeGrants.value || route.query.tab === 'members') return 'members'
  return route.query.tab === 'data-scopes' ? 'data-scopes' : 'grants'
}
const tab = ref<'grants' | 'data-scopes' | 'members'>(initialTab())
const scopeFocusLib = ref('')
const diffDialogVisible = ref(false)
const justCreated = ref(typeof route.query.created === 'string' ? route.query.created : '')

const isSuperRole = computed(() => role.value?.code === SUPERADMIN_ROLE_CODE && role.value.is_builtin)
const readonly = computed(() => !canGrant.value || isSuperRole.value || loading.value || saving.value)
const grantNotice = computed<{ type: 'info' | 'warning'; title: string } | null>(() => {
  if (isSuperRole.value) {
    return { type: 'info', title: '超级管理员拥有全部模块的全部权限，也是唯一能分配角色和权限的角色。这里只能查看，防止把所有人锁在门外。' }
  }
  if (!canGrant.value) return { type: 'info', title: '只读查看：只有超级管理员可以修改角色权限。' }
  if (role.value && role.value.status !== 'active') {
    return { type: 'warning', title: '角色已停用：下面的权限暂时对成员不生效，启用后恢复。' }
  }
  return null
})
const {
  role, groups, capabilities, thinktankLibs, names, selected, original, loading, saving, loadError, changes, openedCount,
  updateSelected, load, refreshRole, confirmDiscard, reset: onReset, save: onSave,
} = useRoleGrants({
  roleId: () => roleId.value,
  canSeeGrants: () => canSeeGrants.value,
  readonly: () => readonly.value,
  justCreated: () => justCreated.value,
  saved: () => emit('changed'),
})

const scopeBadges = computed(() => buildScopeBadges(thinktankLibs.value, selected.value))
const splitDiffs = computed(() => splitGrantDiffs(thinktankLibs.value, changes.value))

const formVisible = ref(false)
const formMode = ref<RoleFormMode>('edit')

function openForm(mode: RoleFormMode) {
  formMode.value = mode
  formVisible.value = true
}

function onOpenScope(code: string) {
  scopeFocusLib.value = code
  tab.value = 'data-scopes'
}

function onFormSaved(saved: RoleItem, mode: RoleFormMode) {
  if (mode === 'copy') {
    emit('changed')
    void router.push({ name: 'system-role-detail', params: { roleId: saved.id }, query: { created: 'copy' } })
    return
  }
  role.value = { ...role.value, ...saved }
  ElMessage.success('角色信息已保存')
  emit('changed')
  void refreshRole()
}

function confirmStatusChange(current: RoleItem, disabling: boolean): Promise<boolean> {
  const verb = disabling ? '停用' : '启用'
  const message = disabling
    ? `停用后，${current.member_count ?? 0} 位成员会立即失去这个角色带来的权限（其他角色不受影响），可随时重新启用。`
    : '启用后，成员会重新获得这个角色的权限。'
  return ElMessageBox.confirm(message, `${verb}「${current.name}」`, {
    type: 'warning',
    confirmButtonText: verb,
    cancelButtonText: '取消',
  }).then(() => true, () => false)
}

async function onToggleStatus() {
  const current = role.value
  if (!current || current.is_builtin) return
  const next = current.status === 'active' ? 'disabled' : 'active'
  if (!await confirmStatusChange(current, next === 'disabled')) return
  try {
    const saved = await updateRole(current.id, { status: next, version: current.version })
    role.value = { ...current, ...saved }
    emit('changed')
    ElMessage.success(next === 'disabled' ? '角色已停用' : '角色已启用')
  } catch (error) {
    ElMessage.error(errorMessage(error, '操作失败'))
  }
}

function onMembersChanged(count: number) {
  if (role.value) role.value = { ...role.value, member_count: count }
  emit('changed')
}

watch(tab, (value) => {
  void router.replace({
    query: { ...route.query, tab: value === 'grants' ? undefined : value },
  })
})

watch(roleId, (value, previous) => {
  if (value && value !== previous) {
    justCreated.value = typeof route.query.created === 'string' ? route.query.created : ''
    scopeFocusLib.value = ''
    diffDialogVisible.value = false
    tab.value = initialTab()
    void load()
  }
})

onBeforeRouteLeave(async () => (saving.value ? false : confirmDiscard('这个角色有未保存的权限修改，离开后将丢弃。')))
// 同一页面切到另一个角色（如「复制为新角色」）也要拦，只切页签不拦。
onBeforeRouteUpdate(async (to, from) => {
  if (to.params.roleId === from.params.roleId) return true
  return saving.value ? false : confirmDiscard('这个角色有未保存的权限修改，切换后将丢弃。')
})
function onBeforeUnload(event: BeforeUnloadEvent) {
  if (changes.value.length || saving.value) { event.preventDefault(); event.returnValue = '' }
}
onMounted(() => { window.addEventListener('beforeunload', onBeforeUnload); void load() })
onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))
</script>

<template>
  <div class="role-detail">
    <DetailSkeleton
      v-if="loading && !role"
      :sections="2"
      :fields-per-section="4"
    />

    <div
      v-else-if="loadError && !role"
      class="role-detail__error"
      role="alert"
    >
      <h2>暂时无法加载这个角色</h2>
      <p>{{ loadError }}</p>
      <el-button
        type="primary"
        :loading="loading"
        @click="load"
      >
        重新加载
      </el-button>
    </div>

    <template v-else-if="role">
      <header class="role-head">
        <div class="role-head__main">
          <div class="role-head__title">
            <h2>{{ role.name }}</h2>
            <el-tag
              v-if="role.is_builtin"
              size="small"
              type="warning"
              effect="plain"
            >
              内置
            </el-tag>
            <el-tag
              size="small"
              :type="role.status === 'active' ? 'success' : 'info'"
            >
              {{ role.status === 'active' ? '启用' : '已停用' }}
            </el-tag>
          </div>
          <p
            class="role-head__desc"
            :class="{ 'is-empty': !role.description }"
          >
            {{ role.description || (role.is_builtin ? '内置角色：拥有全部模块的全部权限，也是唯一能给人分配角色的角色。' : '还没有职责说明。补一句说明，给同事分配角色时更容易选对。') }}
          </p>
          <dl class="role-head__stats">
            <div><dt>成员</dt><dd>{{ role.member_count ?? 0 }} 人</dd></div>
            <div><dt>已开通模块</dt><dd>{{ openedCount }} 个</dd></div>
            <div><dt>角色编码</dt><dd>{{ role.code }}</dd></div>
          </dl>
        </div>
        <!-- 内置角色不能改名，也不能复制：复制超级管理员等于造出一个几乎全权限的普通角色。 -->
        <div
          v-if="canManageRoles && !role.is_builtin"
          class="role-head__actions"
        >
          <el-button
            :icon="EditPen"
            @click="openForm('edit')"
          >
            编辑名称和说明
          </el-button>
          <el-tooltip
            :disabled="canGrant"
            content="复制会连同权限一起复制，只有超级管理员可以操作"
            placement="top"
          >
            <span>
              <el-button
                :icon="CopyDocument"
                :disabled="!canGrant"
                @click="openForm('copy')"
              >
                复制为新角色
              </el-button>
            </span>
          </el-tooltip>
          <el-tooltip
            :disabled="role.status === 'active' || canGrant"
            content="启用会把这个角色的权限还给它的全部成员，只有超级管理员可以操作"
            placement="top"
          >
            <span>
              <el-button
                :disabled="role.status !== 'active' && !canGrant"
                @click="onToggleStatus"
              >
                {{ role.status === 'active' ? '停用' : '启用' }}
              </el-button>
            </span>
          </el-tooltip>
        </div>
      </header>

      <el-alert
        v-if="justCreated && tab === 'grants' && !isSuperRole"
        type="success"
        :closable="true"
        show-icon
        class="role-detail__notice"
        :title="justCreated === 'copy' ? '已复制，权限与原角色相同。可以按需调整，保存后到「成员」分配给同事。' : '角色已创建。现在勾选它能用的模块并保存，然后到「成员」把角色分给同事。'"
        @close="justCreated = ''"
      />

      <section class="role-body">
        <el-tabs
          v-model="tab"
          class="role-tabs"
        >
          <el-tab-pane name="grants">
            <template #label>
              菜单权限<span
                v-if="splitDiffs.menuDiffs.length"
                class="role-body__badge is-dirty"
              >+{{ splitDiffs.menuDiffs.length }}</span>
            </template>
            <el-alert
              v-if="!canSeeGrants"
              type="info"
              :closable="false"
              show-icon
              title="你没有查看权限配置的权限，只能管理角色名称与成员。"
            />
            <template v-else>
              <el-alert
                v-if="grantNotice"
                :type="grantNotice.type"
                :closable="false"
                show-icon
                class="role-detail__notice"
                :title="grantNotice.title"
              />
              <PermissionTable
                :model-value="selected"
                :groups="groups"
                :original="original"
                :disabled="readonly"
                :role-code="role.code"
                :capabilities="capabilities"
                :scope-badges="scopeBadges"
                @update:model-value="updateSelected"
                @open-scope="onOpenScope"
              />
            </template>
          </el-tab-pane>
          <el-tab-pane
            v-if="canSeeGrants"
            name="data-scopes"
          >
            <template #label>
              智库数据权限<span
                v-if="splitDiffs.scopeDiffs.length"
                class="role-body__badge is-dirty"
              >+{{ splitDiffs.scopeDiffs.length }}</span>
            </template>
            <ThinktankDataScopePanel
              :libraries="thinktankLibs"
              :model-value="selected"
              :original="original"
              :disabled="readonly"
              :initial-lib-code="scopeFocusLib"
              @update:model-value="updateSelected"
            />
          </el-tab-pane>
          <el-tab-pane name="members">
            <template #label>
              成员 <span class="role-body__badge">{{ role.member_count ?? 0 }}</span>
            </template>
            <RoleMembersPanel
              v-if="tab === 'members'"
              :role="role"
              :can-grant="canGrant"
              @changed="onMembersChanged"
            />
          </el-tab-pane>
        </el-tabs>

        <!-- 钉在权限卡片底部：在「菜单权限」或「智库数据权限」页签下滚动时一直看得到。 -->
        <div
          v-if="canSeeGrants && tab !== 'members' && changes.length"
          class="savebar"
          role="status"
        >
          <div class="savebar__left">
            <span class="savebar__text">有 <strong>{{ changes.length }}</strong> 项修改还没保存，保存后成员下次操作即生效</span>
            <el-button
              size="small"
              :disabled="saving"
              @click="diffDialogVisible = true"
            >
              查看修改明细
            </el-button>
          </div>
          <el-button
            :disabled="saving"
            @click="onReset"
          >
            放弃修改
          </el-button>
          <el-button
            type="primary"
            :loading="saving"
            @click="onSave"
          >
            保存权限
          </el-button>
        </div>
      </section>
    </template>

    <RoleGrantDiffDialog
      v-model="diffDialogVisible"
      :changes="changes"
      :names="names"
      :saving="saving"
      @save="onSave"
    />

    <RoleFormDialog
      v-model="formVisible"
      :mode="formMode"
      :role="role"
      @saved="onFormSaved"
    />
  </div>
</template>

<style scoped src="./role-detail.css"></style>
