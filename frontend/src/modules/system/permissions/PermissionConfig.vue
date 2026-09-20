<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { listResourceTree, listRoleGrants, listAllRoles, replaceRoleGrants } from '@/api/system'
import { errorMessage, isApiError } from '@/api/errors'
import type { ResourceNode, RoleItem } from '@/api/types'
import { applyParentLevel, grantDiff, grantsFromTree, type GrantLevel } from '@/permissions/levels'
import { useAuthStore } from '@/stores/auth'

const LEVEL_LABEL: Record<GrantLevel, string> = {
  NONE: '无权限',
  READ: '只读',
  FULL: '可管理',
}

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const roleKeyword = ref('')
const roles = ref<RoleItem[]>([])
const currentRoleId = ref('')
const role = ref<RoleItem | null>(null)
const tree = ref<ResourceNode[]>([])
const selected = ref<Record<string, GrantLevel>>({})
const original = ref<Record<string, GrantLevel>>({})

const canWrite = computed(() => auth.canFull('system.permissions'))

const filteredRoles = computed(() => {
  const text = roleKeyword.value.trim().toLowerCase()
  if (!text) {
    return roles.value
  }
  return roles.value.filter(
    (item) => item.name.toLowerCase().includes(text) || item.code.toLowerCase().includes(text),
  )
})

const changes = computed(() =>
  grantDiff(grantsFromTree(tree.value, original.value), grantsFromTree(tree.value, selected.value)),
)

const grantSummary = computed(() => {
  let read = 0
  let full = 0
  for (const level of Object.values(selected.value)) {
    if (level === 'READ') {
      read += 1
    }
    if (level === 'FULL') {
      full += 1
    }
  }
  return { read, full }
})

function routeRoleId(): string {
  const fromParam = route.params.roleId
  if (typeof fromParam === 'string' && fromParam) {
    return fromParam
  }
  const fromQuery = route.query.roleId
  return typeof fromQuery === 'string' ? fromQuery : ''
}

function collect(nodes: ResourceNode[], grants: Record<string, GrantLevel>) {
  for (const node of nodes) {
    if (node.node_type === 'resource' && node.published) {
      selected.value[node.code] = grants[node.code] ?? 'NONE'
    }
    if (node.children?.length) {
      collect(node.children, grants)
    }
  }
}

function publishedCodes(node: ResourceNode, codes: string[] = []): string[] {
  if (node.node_type === 'resource' && node.published) {
    codes.push(node.code)
  }
  for (const child of node.children ?? []) {
    publishedCodes(child, codes)
  }
  return codes
}

function parentLevel(node: ResourceNode): GrantLevel | '' {
  const codes = publishedCodes(node)
  if (!codes.length) {
    return ''
  }
  const first = selected.value[codes[0]] ?? 'NONE'
  return codes.every((code) => (selected.value[code] ?? 'NONE') === first) ? first : ''
}

function syncUrl(roleId: string) {
  if (route.name === 'system-role-grants') {
    if (route.params.roleId !== roleId) {
      void router.replace({ name: 'system-role-grants', params: { roleId } })
    }
    return
  }
  if (route.query.roleId !== roleId) {
    void router.replace({ name: 'system-permissions', query: { roleId } })
  }
}

async function loadRolesAndTree() {
  const [rolePage, resourceData] = await Promise.all([
    listAllRoles(),
    tree.value.length ? Promise.resolve({ tree: tree.value }) : listResourceTree(),
  ])
  roles.value = rolePage
  tree.value = resourceData.tree
}

async function loadGrants(roleId: string) {
  const grantData = await listRoleGrants(roleId)
  role.value = grantData.role
  const map: Record<string, GrantLevel> = {}
  for (const grant of grantData.grants) {
    map[grant.resource_code] = grant.level
  }
  selected.value = {}
  collect(tree.value, map)
  original.value = { ...selected.value }
}

async function activateRole(roleId: string, force = false) {
  if (saving.value || loading.value) return
  if (!roleId || (roleId === currentRoleId.value && !force)) {
    return
  }
  if (!force && changes.value.length) {
    try {
      await ElMessageBox.confirm('当前角色有未保存的授权变更，切换后将丢弃。', '切换角色', { type: 'warning' })
    } catch {
      return
    }
  }
  loading.value = true
  try {
    await loadGrants(roleId)
    currentRoleId.value = roleId
    syncUrl(roleId)
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载授权失败'))
  } finally {
    loading.value = false
  }
}

async function bootstrap() {
  loading.value = true
  try {
    await loadRolesAndTree()
    const preferred = routeRoleId()
    const next =
      roles.value.find((item) => item.id === preferred)?.id ?? roles.value.find((item) => item.status === 'active')?.id ?? roles.value[0]?.id ?? ''
    if (!next) {
      role.value = null
      return
    }
    currentRoleId.value = next
    syncUrl(next)
    await loadGrants(next)
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载授权失败'))
  } finally {
    loading.value = false
  }
}

function onLeafChange(code: string, level: GrantLevel) {
  selected.value = { ...selected.value, [code]: level }
}

function onParentChange(node: ResourceNode, level: GrantLevel) {
  selected.value = applyParentLevel(node, level, selected.value)
}

function onReset() {
  selected.value = { ...original.value }
}

async function onSave() {
  if (saving.value || loading.value || !canWrite.value) return
  if (!role.value) {
    return
  }
  if (!changes.value.length) {
    ElMessage.info('没有变更')
    return
  }
  const summary = changes.value
    .map((item) => `${item.code}：${LEVEL_LABEL[item.from]} → ${LEVEL_LABEL[item.to]}`)
    .join('\n')
  saving.value = true
  try {
    await ElMessageBox.confirm(summary, '确认保存以下授权变更？', { type: 'warning' })
  } catch {
    saving.value = false
    return
  }
  try {
    const result = await replaceRoleGrants(role.value.id, {
      version: role.value.version,
      grants: grantsFromTree(tree.value, selected.value),
    })
    role.value = result.role
    original.value = { ...selected.value }
    ElMessage.success('授权已保存')
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert('授权已被他人修改，请重新加载后再保存。', '版本冲突')
      await loadGrants(currentRoleId.value)
    } else {
      ElMessage.error(errorMessage(error, '保存失败'))
    }
  } finally {
    saving.value = false
  }
}

watch(
  () => routeRoleId(),
  (value) => {
    if (value && value !== currentRoleId.value) {
      void activateRole(value)
    }
  },
)

onBeforeRouteLeave(async () => {
  if (saving.value) return false
  if (!changes.value.length) return true
  try {
    await ElMessageBox.confirm('授权变更尚未保存，离开后将丢弃。', '离开权限分配', { type: 'warning' })
    return true
  } catch {
    return false
  }
})

onMounted(() => {
  void bootstrap()
})
</script>

<template>
  <div
    v-loading="loading"
    class="iam-page"
  >
    <section class="iam-page__heading">
      <div class="iam-page__title-block">
        <div>
          <h1 class="iam-page__title">
            权限分配
          </h1>
          <p class="iam-page__hint">
            选择角色，设置模块访问权限；修改后保存生效。
          </p>
        </div>
      </div>
      <div class="iam-page__actions">
        <el-tag
          v-if="changes.length"
          type="warning"
          effect="plain"
        >
          {{ changes.length }} 项待保存
        </el-tag>
        <el-button
          :disabled="loading || saving || !changes.length"
          @click="onReset"
        >
          还原
        </el-button>
        <el-button
          v-if="canWrite"
          type="primary"
          :loading="saving"
          :disabled="loading || saving || !changes.length"
          @click="onSave"
        >
          保存授权
        </el-button>
      </div>
    </section>

    <div class="iam-page__body">
      <aside class="panel iam-roles">
        <div class="iam-roles__head">
          <strong>角色</strong>
          <el-input
            v-model="roleKeyword"
            clearable
            size="small"
            placeholder="搜索名称 / 编码"
            aria-label="搜索角色名称或编码"
          />
        </div>
        <button
          v-for="item in filteredRoles"
          :key="item.id"
          :disabled="loading || saving"
          type="button"
          class="iam-role"
          :class="{ 'is-active': item.id === currentRoleId }"
          @click="activateRole(item.id)"
        >
          <span class="iam-role__name">{{ item.name }}</span>
          <span class="iam-role__code">{{ item.code }}</span>
          <span class="iam-role__tags">
            <el-tag
              :type="item.status === 'active' ? 'success' : 'info'"
              size="small"
            >
              {{ item.status === 'active' ? '启用' : '停用' }}
            </el-tag>
            <el-tag
              v-if="item.is_builtin"
              size="small"
              type="warning"
              effect="plain"
            >
              内置
            </el-tag>
          </span>
        </button>
        <el-empty
          v-if="!filteredRoles.length"
          description="没有匹配的角色"
          :image-size="64"
        />
      </aside>

      <section class="iam-detail">
        <div class="panel iam-detail__meta">
          <div>
            <h2>{{ role?.name || '请选择角色' }}</h2>
            <p v-if="role">
              {{ role.code }} · 当前 {{ grantSummary.full }} 个可管理，{{ grantSummary.read }} 个只读
            </p>
          </div>
          <div class="iam-legend">
            <span><i class="perm-dot perm-dot--none" />无权限</span>
            <span><i class="perm-dot perm-dot--read" />只读</span>
            <span><i class="perm-dot perm-dot--full" />可管理</span>
          </div>
        </div>

        <div class="panel perm-tree-card">
          <el-empty
            v-if="!role"
            description="先在左侧选择一个角色"
          />
          <el-tree
            v-else
            :data="tree"
            node-key="id"
            default-expand-all
            :props="{ label: 'name', children: 'children' }"
            class="perm-tree"
          >
            <template #default="{ data }">
              <div
                class="perm-row"
                :class="{ 'perm-row--dir': data.node_type === 'directory' }"
              >
                <div class="perm-row__meta">
                  <span class="perm-row__name">{{ data.name }}</span>
                  <span class="perm-row__code">{{ data.code }}</span>
                  <el-tag
                    v-if="!data.published"
                    size="small"
                    type="info"
                  >
                    未开发
                  </el-tag>
                  <el-tag
                    v-else-if="data.node_type === 'directory' && !parentLevel(data)"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    部分授权
                  </el-tag>
                </div>
                <el-radio-group
                  v-if="data.node_type === 'resource' && data.published"
                  class="perm-levels"
                  size="small"
                  :model-value="selected[data.code] || 'NONE'"
                  :disabled="!canWrite || loading || saving"
                  @change="(value: GrantLevel) => onLeafChange(data.code, value)"
                >
                  <el-radio-button value="NONE">
                    无权限
                  </el-radio-button>
                  <el-radio-button value="READ">
                    只读
                  </el-radio-button>
                  <el-radio-button value="FULL">
                    可管理
                  </el-radio-button>
                </el-radio-group>
                <el-radio-group
                  v-else-if="data.node_type === 'directory' && data.published"
                  class="perm-levels"
                  size="small"
                  :model-value="parentLevel(data)"
                  :disabled="!canWrite || loading || saving"
                  @change="(value: GrantLevel) => onParentChange(data, value)"
                >
                  <el-radio-button value="NONE">
                    全部无权限
                  </el-radio-button>
                  <el-radio-button value="READ">
                    全部只读
                  </el-radio-button>
                  <el-radio-button value="FULL">
                    全部可管理
                  </el-radio-button>
                </el-radio-group>
              </div>
            </template>
          </el-tree>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.iam-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);

}

.iam-page__heading,
.iam-detail__meta,
.iam-roles__head {
  display: flex;
  align-items: center;
  gap: 16px;
}

.iam-page__heading,
.iam-detail__meta {
  min-height: 72px;
  padding: 16px 24px;
}

.iam-page__heading { padding: 0 0 16px; border-bottom: 1px solid var(--zt-border); }
.iam-page__heading h1 { font-size: var(--zt-title-size); }
.iam-page__title-block {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.iam-page__bar {
  width: 4px;
  height: 22px;
  margin-top: 3px;
  border-radius: 4px;
  background: var(--zt-blue-600);
  flex: 0 0 auto;
}

.iam-page__title,
.iam-detail__meta h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.iam-page__hint,
.iam-detail__meta p,
.iam-role__code {
  margin: 6px 0 0;
  color: var(--zt-ink-500);
  font-size: 13px;
  line-height: 1.5;
}

.iam-page__actions,
.iam-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin-left: auto;
}

.iam-page__body {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.iam-roles {
  padding: 16px 12px;
}

.iam-roles__head {
  padding: 0 8px 12px;
}

.iam-roles__head strong {
  flex: 0 0 auto;
}

.iam-role {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
  margin-bottom: 6px;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: var(--zt-radius);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.iam-role:hover,
.iam-role.is-active {
  background: #edf5ff;
  border-color: #d6e6fb;
}

.iam-role__name {
  color: var(--zt-ink-900);
  font-size: 14px;
  font-weight: 700;
}

.iam-role__tags {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.iam-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.iam-legend {
  color: var(--zt-ink-700);
  font-size: 13px;
}

.iam-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.perm-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.perm-dot--none {
  background: #9aa4b5;
}

.perm-dot--read {
  background: #2d76e5;
}

.perm-dot--full {
  background: #2f9461;
}

.perm-tree-card {
  padding: 8px 8px 16px;
}

.perm-tree {
  background: transparent;
}

.perm-tree :deep(.el-tree-node__content) {
  height: auto;
  min-height: 48px;
  padding: 6px 16px 6px 8px;
  border-bottom: 1px solid #f0f3f8;
}

.perm-tree :deep(.el-tree-node__content:hover) {
  background: #f7f9fc;
}

.perm-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
}

.perm-row--dir .perm-row__name {
  font-weight: 700;
}

.perm-row__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.perm-row__name {
  color: var(--zt-ink-900);
  font-size: 14px;
}

.perm-row__code {
  color: var(--zt-ink-500);
  font-size: 12px;
}

.perm-levels :deep(.el-radio-button__inner) {
  padding: 6px 12px;
}

@media (max-width: 1100px) {
  .iam-page__body {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 760px) {
  .iam-page__heading,
  .iam-detail__meta,
  .perm-row {
    flex-wrap: wrap;
  }

  .iam-page__actions {
    margin-left: 0;
  }

  .perm-row__code {
    overflow-wrap: anywhere;
  }
}
</style>
