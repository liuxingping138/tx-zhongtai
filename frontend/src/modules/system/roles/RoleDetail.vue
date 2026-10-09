<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, CopyDocument, EditPen } from '@element-plus/icons-vue'

import { getRole, listResourceTree, listRoleGrants, replaceRoleGrants, updateRole } from '@/api/system'
import { errorMessage, isApiError } from '@/api/errors'
import type { ResourceNode, RoleItem } from '@/api/types'
import { LEVEL_TEXT, capabilityModules, moduleGroups, moduleNames, SUPERADMIN_ROLE_CODE } from '@/permissions/catalog'
import { grantDiff, grantsFromTree, type GrantLevel } from '@/permissions/levels'
import { useAuthStore } from '@/stores/auth'
import PermissionTable from './PermissionTable.vue'
import RoleFormDialog, { type RoleFormMode } from './RoleFormDialog.vue'
import RoleMembersPanel from './RoleMembersPanel.vue'

/**
 * 角色详情：上面是角色信息，下面分「权限设置」「成员」两个页签（参考 Strapi 的角色编辑页）。
 * 从列表进来只处理这一个角色，不必在左右两栏之间找当前选中的是谁。
 */
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const canManageRoles = computed(() => auth.canFull('system.roles'))
const canSeeGrants = computed(() => auth.canRead('system.permissions'))
const canGrant = computed(() => auth.canFull('system.permissions'))

const roleId = computed(() => String(route.params.roleId ?? ''))
const role = ref<RoleItem | null>(null)
const tree = ref<ResourceNode[]>([])
const selected = ref<Record<string, GrantLevel>>({})
const original = ref<Record<string, GrantLevel>>({})
const loading = ref(false)
const saving = ref(false)
const loadError = ref('')
const tab = ref<'grants' | 'members'>(route.query.tab === 'members' ? 'members' : 'grants')
const justCreated = ref(typeof route.query.created === 'string' ? route.query.created : '')

const formVisible = ref(false)
const formMode = ref<RoleFormMode>('edit')

const groups = computed(() => moduleGroups(tree.value))
const capabilities = computed(() => capabilityModules(tree.value))
const names = computed(() => ({
  ...moduleNames(groups.value),
  ...Object.fromEntries(capabilities.value.map(module => [module.code, `分配角色 / ${module.name}`])),
}))
const isSuperRole = computed(() => role.value?.code === SUPERADMIN_ROLE_CODE && role.value.is_builtin)
const readonly = computed(() => !canGrant.value || isSuperRole.value || loading.value || saving.value)
const changes = computed(() =>
  grantDiff(grantsFromTree(tree.value, original.value), grantsFromTree(tree.value, selected.value)),
)
const openedCount = computed(() => Object.values(selected.value).filter(level => level !== 'NONE').length)

function collect(nodes: ResourceNode[], grants: Record<string, GrantLevel>, out: Record<string, GrantLevel>) {
  for (const node of nodes) {
    if (node.node_type === 'resource' && node.published) out[node.code] = grants[node.code] ?? 'NONE'
    if (node.children?.length) collect(node.children, grants, out)
  }
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [detail, resources, grants] = await Promise.all([
      getRole(roleId.value),
      canSeeGrants.value ? (tree.value.length ? { tree: tree.value } : listResourceTree()) : { tree: [] as ResourceNode[] },
      canSeeGrants.value ? listRoleGrants(roleId.value) : null,
    ])
    tree.value = resources.tree
    role.value = detail
    const map: Record<string, GrantLevel> = {}
    for (const grant of grants?.grants ?? []) map[grant.resource_code] = grant.level
    const next: Record<string, GrantLevel> = {}
    collect(tree.value, map, next)
    selected.value = next
    original.value = { ...next }
  } catch (error) {
    loadError.value = errorMessage(error, '暂时无法加载这个角色，请稍后重试。')
  } finally {
    loading.value = false
  }
}

async function refreshRole() {
  try {
    role.value = await getRole(roleId.value)
  } catch {
    /* 仅刷新统计数字，失败不打扰 */
  }
}

async function confirmDiscard(message: string): Promise<boolean> {
  if (!changes.value.length) return true
  return ElMessageBox.confirm(message, '放弃未保存的权限修改？', {
    type: 'warning',
    confirmButtonText: '放弃修改',
    cancelButtonText: '继续编辑',
  }).then(() => true, () => false)
}

function onReset() {
  selected.value = { ...original.value }
}

async function onSave() {
  if (saving.value || !role.value || !changes.value.length || readonly.value) return
  const summary = changes.value
    .map(item => `${names.value[item.code] ?? item.code}：${LEVEL_TEXT[item.from]} → ${LEVEL_TEXT[item.to]}`)
    .join('\n')
  saving.value = true
  try {
    await ElMessageBox.confirm(summary, `保存「${role.value.name}」的 ${changes.value.length} 项权限修改？`, {
      type: 'warning',
      confirmButtonText: '保存',
      cancelButtonText: '再看看',
      customClass: 'grant-confirm',
    })
  } catch {
    saving.value = false
    return
  }
  try {
    const result = await replaceRoleGrants(role.value.id, {
      version: role.value.version,
      grants: grantsFromTree(tree.value, selected.value),
    })
    role.value = { ...role.value, ...result.role }
    original.value = { ...selected.value }
    ElMessage.success(justCreated.value ? '权限已保存。下一步：到「成员」把角色分给同事' : '权限已保存，成员下次操作时即生效')
    void refreshRole()
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert('这个角色的权限刚被其他人修改过，将为你加载最新内容，请重新调整后再保存。', '权限已被修改')
      await load()
    } else {
      ElMessage.error(errorMessage(error, '保存失败'))
    }
  } finally {
    saving.value = false
  }
}

function openForm(mode: RoleFormMode) {
  formMode.value = mode
  formVisible.value = true
}

async function onFormSaved(saved: RoleItem, mode: RoleFormMode) {
  if (mode === 'copy') {
    void router.push({ name: 'system-role-detail', params: { roleId: saved.id }, query: { created: 'copy' } })
    return
  }
  role.value = { ...role.value, ...saved }
  ElMessage.success('角色信息已保存')
  void refreshRole()
}

async function onToggleStatus() {
  const current = role.value
  if (!current || current.is_builtin) return
  const next = current.status === 'active' ? 'disabled' : 'active'
  const confirmed = await ElMessageBox.confirm(
    next === 'disabled'
      ? `停用后，${current.member_count ?? 0} 位成员会立即失去这个角色带来的权限（其他角色不受影响），可随时重新启用。`
      : '启用后，成员会重新获得这个角色的权限。',
    `${next === 'disabled' ? '停用' : '启用'}「${current.name}」`,
    { type: 'warning', confirmButtonText: next === 'disabled' ? '停用' : '启用', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!confirmed) return
  try {
    const saved = await updateRole(current.id, { status: next, version: current.version })
    role.value = { ...current, ...saved }
    ElMessage.success(next === 'disabled' ? '角色已停用' : '角色已启用')
  } catch (error) {
    ElMessage.error(errorMessage(error, '操作失败'))
  }
}

function onMembersChanged(count: number) {
  if (role.value) role.value = { ...role.value, member_count: count }
}

function backToList() {
  void router.push({ name: 'system-roles' })
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
  <div
    v-loading="loading && !role"
    class="role-detail"
  >
    <el-button
      link
      :icon="ArrowLeft"
      class="role-detail__back"
      @click="backToList"
    >
      返回角色列表
    </el-button>

    <div
      v-if="loadError && !role"
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
            <h1>{{ role.name }}</h1>
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
            {{ role.description || '还没有职责说明。补一句说明，给同事分配角色时更容易选对。' }}
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
        <div
          v-if="canManageRoles"
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
          <el-button
            v-if="!role.is_builtin"
            @click="onToggleStatus"
          >
            {{ role.status === 'active' ? '停用' : '启用' }}
          </el-button>
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
                按菜单授权。每一项选一档：<strong>查看</strong>能进入，<strong>导出</strong>还能下载，<strong>管理</strong>还能新增、编辑、导入。选中的档已经包含它左边的能力。「开通整组」会把这一组开到各自最高档。最下面的「分配角色」不是菜单。
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
.role-detail__back { align-self: flex-start; margin-left: -4px; color: var(--zt-ink-700); }
.role-detail__error {
  display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 48px 24px; text-align: center;
  border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); color: var(--zt-ink-700);
}
.role-detail__error h2 { margin: 0; font-size: 17px; }
.role-detail__error p { margin: 0; }
.role-detail__notice { margin-bottom: 0; }

.role-head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 24px;
  padding: 20px 24px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel);
}
.role-head__main { min-width: 0; }
.role-head__title { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.role-head__title h1 { margin: 0; font-size: var(--zt-title-size); font-weight: 650; line-height: 1.4; color: var(--zt-ink-900); }
.role-head__desc { margin: 6px 0 0; max-width: 72ch; font-size: 14px; line-height: 1.6; color: var(--zt-ink-700); }
.role-head__desc.is-empty { color: var(--zt-ink-500); }
.role-head__stats { display: flex; flex-wrap: wrap; gap: 8px 32px; margin: 14px 0 0; }
.role-head__stats div { display: flex; align-items: baseline; gap: 6px; }
.role-head__stats dt { font-size: 12px; color: var(--zt-ink-500); }
.role-head__stats dd { margin: 0; font-size: 14px; color: var(--zt-ink-900); font-variant-numeric: tabular-nums; }
.role-head__actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; flex: none; }
.role-head__actions .el-button + .el-button { margin-left: 0; }

.role-body { padding: 4px 24px 24px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); }
.role-body .role-detail__notice { margin-bottom: 12px; }
.role-body__guide { margin: 0 0 12px; font-size: 13px; line-height: 1.6; color: var(--zt-ink-700); }
.role-body__guide strong { color: var(--zt-ink-900); }
.role-body__badge {
  display: inline-block; min-width: 20px; margin-left: 4px; padding: 0 6px; border-radius: 10px;
  background: var(--zt-soft); font-size: 12px; line-height: 18px; text-align: center; color: var(--zt-ink-700);
}

.savebar {
  position: sticky; bottom: 0; z-index: 5; display: flex; align-items: center; justify-content: flex-end; gap: 12px;
  margin: 16px -24px -24px; padding: 12px 24px; border-top: 1px solid #f3d19e;
  border-radius: 0 0 var(--zt-radius) var(--zt-radius); background: #fffaf0; box-shadow: 0 -6px 16px rgb(15 35 70 / 6%);
}
.savebar__text { margin-right: auto; font-size: 14px; color: var(--zt-ink-700); }
.savebar__text strong { color: #b26a00; font-variant-numeric: tabular-nums; }
.savebar .el-button + .el-button { margin-left: 0; }
@media (max-width: 1100px) {
  .role-head { flex-direction: column; }
  .role-head__actions { justify-content: flex-start; }
}
</style>

<style>
/* 保存确认里逐行列出修改，按行显示，不挤成一段。 */
.grant-confirm { --el-messagebox-width: 520px; }
.grant-confirm .el-message-box__message p { white-space: pre-line; line-height: 1.8; }
</style>
