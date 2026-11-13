<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CopyDocument, EditPen } from '@element-plus/icons-vue'

import { updateRole } from '@/api/system'
import { errorMessage } from '@/api/errors'
import type { RoleItem } from '@/api/types'
import { useRoleGrants } from '@/composables/useRoleGrants'
import { SUPERADMIN_ROLE_CODE } from '@/permissions/catalog'
import DetailSkeleton from '@/components/DetailSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import PermissionTable from './PermissionTable.vue'
import RoleFormDialog, { type RoleFormMode } from './RoleFormDialog.vue'
import RoleMembersPanel from './RoleMembersPanel.vue'

/**
 * 角色详情：嵌在「角色与权限」右侧。上面是角色信息，下面分「权限设置」「成员」两个页签。
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
const tab = ref<'grants' | 'members'>(route.query.tab === 'members' ? 'members' : 'grants')
const justCreated = ref(typeof route.query.created === 'string' ? route.query.created : '')

const isSuperRole = computed(() => role.value?.code === SUPERADMIN_ROLE_CODE && role.value.is_builtin)
const readonly = computed(() => !canGrant.value || isSuperRole.value || loading.value || saving.value)
const {
  role, groups, capabilities, selected, original, loading, saving, loadError, changes, openedCount,
  load, refreshRole, confirmDiscard, reset: onReset, save: onSave,
} = useRoleGrants({
  roleId: () => roleId.value,
  canSeeGrants: () => canSeeGrants.value,
  readonly: () => readonly.value,
  justCreated: () => justCreated.value,
  saved: () => emit('changed'),
})

const formVisible = ref(false)
const formMode = ref<RoleFormMode>('edit')

function openForm(mode: RoleFormMode) {
  formMode.value = mode
  formVisible.value = true
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
  void router.replace({ query: { ...route.query, tab: value === 'members' ? 'members' : undefined } })
})

watch(roleId, (value, previous) => {
  if (value && value !== previous) {
    justCreated.value = typeof route.query.created === 'string' ? route.query.created : ''
    tab.value = route.query.tab === 'members' ? 'members' : 'grants'
    void load()
  }
})

onBeforeRouteLeave(async () => {
  if (saving.value) return false
  return confirmDiscard('这个角色有未保存的权限修改，离开后将丢弃。')
})

// 同一页面切到另一个角色（如「复制为新角色」）也要拦，只切页签不拦。
onBeforeRouteUpdate(async (to, from) => {
  if (to.params.roleId === from.params.roleId) return true
  if (saving.value) return false
  return confirmDiscard('这个角色有未保存的权限修改，切换后将丢弃。')
})

onMounted(() => {
  if (!canSeeGrants.value) tab.value = 'members'
  void load()
})
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
            <div>
              <dt>成员</dt>
              <dd>{{ role.member_count ?? 0 }} 人</dd>
            </div>
            <div>
              <dt>已开通模块</dt>
              <dd>{{ openedCount }} 个</dd>
            </div>
            <div>
              <dt>角色编码</dt>
              <dd>{{ role.code }}</dd>
            </div>
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
        <el-tabs v-model="tab">
          <el-tab-pane
            name="grants"
            label="权限设置"
          >
            <el-alert
              v-if="!canSeeGrants"
              type="info"
              :closable="false"
              show-icon
              title="你没有查看权限配置的权限，只能管理角色名称与成员。"
            />
            <template v-else>
              <el-alert
                v-if="isSuperRole"
                type="info"
                :closable="false"
                show-icon
                class="role-detail__notice"
                title="超级管理员拥有全部模块的全部权限，也是唯一能分配角色和权限的角色。这里只能查看，防止把所有人锁在门外。"
              />
              <el-alert
                v-else-if="!canGrant"
                type="info"
                :closable="false"
                show-icon
                class="role-detail__notice"
                title="只读查看：只有超级管理员可以修改角色权限。"
              />
              <el-alert
                v-else-if="role.status !== 'active'"
                type="warning"
                :closable="false"
                show-icon
                class="role-detail__notice"
                title="角色已停用：下面的权限暂时对成员不生效，启用后恢复。"
              />
              <p
                v-if="!readonly || saving"
                class="role-body__guide"
              >
                按菜单勾选。分组行的勾选框一次开通整列；最下面的「特殊能力」不是菜单。
              </p>
              <PermissionTable
                v-model="selected"
                :groups="groups"
                :original="original"
                :disabled="readonly"
                :role-code="role.code"
                :capabilities="capabilities"
              />
              <!-- 钉在权限卡片底部：滚动时一直看得到，但不盖住表格内容。 -->
              <div
                v-if="changes.length"
                class="savebar"
                role="status"
              >
                <span class="savebar__text">有 <strong>{{ changes.length }}</strong> 项修改还没保存，保存后成员下次操作即生效</span>
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
            </template>
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
      </section>
    </template>


    <RoleFormDialog
      v-model="formVisible"
      :mode="formMode"
      :role="role"
      @saved="onFormSaved"
    />
  </div>
</template>

<style scoped>
.role-detail { display: flex; flex-direction: column; gap: 16px; min-height: 300px; }
.role-detail__error { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 48px 24px; text-align: center; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); color: var(--zt-ink-700); }
.role-detail__error h2 { margin: 0; font-size: 17px; }
.role-detail__error p { margin: 0; }
.role-detail__notice { margin-bottom: 0; }

.role-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; padding: 20px 24px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); box-shadow: var(--zt-shadow); }
.role-head__main { min-width: 0; }
.role-head__title { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.role-head__title h2 { margin: 0; font-size: 20px; font-weight: 650; line-height: 1.4; color: var(--zt-ink-900); }
.role-head__desc { margin: 6px 0 0; max-width: 72ch; font-size: 14px; line-height: 1.6; color: var(--zt-ink-700); }
.role-head__desc.is-empty { color: var(--zt-ink-500); }
.role-head__stats { display: flex; flex-wrap: wrap; gap: 8px 32px; margin: 14px 0 0; }
.role-head__stats div { display: flex; align-items: baseline; gap: 6px; }
.role-head__stats dt { font-size: 12px; color: var(--zt-ink-500); }
.role-head__stats dd { margin: 0; font-size: 14px; color: var(--zt-ink-900); font-variant-numeric: tabular-nums; }
.role-head__actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; flex: none; }
.role-head__actions .el-button + .el-button { margin-left: 0; }

.role-body { padding: 4px 24px 24px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); box-shadow: var(--zt-shadow); }
.role-body .role-detail__notice { margin-bottom: 12px; }
.role-body__guide { margin: 0 0 12px; font-size: 13px; line-height: 1.6; color: var(--zt-ink-700); }
.role-body__guide strong { color: var(--zt-ink-900); }
.role-body__badge { display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 18px; margin-left: 6px; padding: 0 6px; border-radius: 10px; background: var(--zt-surface-subtle); border: 1px solid var(--zt-border); font-size: 11.5px; line-height: 1; text-align: center; color: var(--zt-ink-700); }

.role-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }
.role-tabs :deep(.el-tabs__nav-wrap::after) { height: 1px; background-color: var(--zt-divider); }
.role-tabs :deep(.el-tabs__item) { font-size: 14px; font-weight: 500; color: var(--zt-ink-700); padding: 0 16px; height: 42px; }
.role-tabs :deep(.el-tabs__item.is-active) { font-weight: 600; color: var(--zt-blue-600); }
.role-tabs :deep(.el-tabs__active-bar) { height: 2.5px; border-radius: 2px 2px 0 0; background-color: var(--zt-blue-600); }

.savebar { position: sticky; bottom: 0; z-index: 5; display: flex; align-items: center; justify-content: flex-end; gap: 12px; margin: 16px -24px -24px; padding: 12px 24px; border-top: 1px solid var(--zt-warning-border); border-radius: 0 0 var(--zt-radius) var(--zt-radius); background: var(--zt-warning-soft); box-shadow: 0 -6px 16px var(--zt-shadow-soft); }
.savebar__text { margin-right: auto; font-size: 14px; color: var(--zt-ink-700); }
.savebar__text strong { color: var(--zt-warning-text); font-variant-numeric: tabular-nums; }
.savebar .el-button + .el-button { margin-left: 0; }
@media (max-width: 1100px) {
  .role-head { flex-direction: column; }
  .role-head__actions { justify-content: flex-start; }
}
</style>
