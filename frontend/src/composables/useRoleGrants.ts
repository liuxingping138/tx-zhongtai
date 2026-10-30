import { computed, ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { errorMessage, isApiError } from '@/api/errors'
import { getRole, listResourceTree, listRoleGrants, replaceRoleGrants } from '@/api/system'
import type { ResourceNode, RoleItem } from '@/api/types'
import { LEVEL_TEXT, capabilityModules, moduleGroups, moduleNames } from '@/permissions/catalog'
import { grantDiff, grantsFromTree, type GrantLevel } from '@/permissions/levels'

type Grants = Record<string, GrantLevel>

interface RoleGrantsOptions {
  roleId: () => string
  /** 能看授权才去取资源树和授权；否则只加载角色本身（成员页签仍可用）。 */
  canSeeGrants: () => boolean
  /** 当前不允许改（没有权限分配、超级管理员角色、加载或保存中）。 */
  readonly: () => boolean
  /** 刚新建或复制的角色，保存后的提示会引导去「成员」页签。 */
  justCreated: () => string
  /** 保存成功后通知左侧角色列表刷新。 */
  saved: () => void
}

/** 已发布的资源节点在授权表里的当前档位；没有记录按无权限。 */
export function collectGrants(nodes: ResourceNode[], grants: Grants, out: Grants = {}): Grants {
  for (const node of nodes) {
    if (node.node_type === 'resource' && node.published) out[node.code] = grants[node.code] ?? 'NONE'
    if (node.children?.length) collectGrants(node.children, grants, out)
  }
  return out
}

/**
 * 角色的授权草稿：加载、与已保存值比较、保存前逐项确认、版本冲突时重新加载。
 * 页面只管渲染和路由拦截。
 */
export function useRoleGrants(options: RoleGrantsOptions) {
  const role = ref<RoleItem | null>(null) as Ref<RoleItem | null>
  const tree = ref<ResourceNode[]>([])
  const selected = ref<Grants>({})
  const original = ref<Grants>({})
  const loading = ref(false)
  const saving = ref(false)
  const loadError = ref('')

  const groups = computed(() => moduleGroups(tree.value))
  const capabilities = computed(() => capabilityModules(tree.value))
  const names = computed(() => ({
    ...moduleNames(groups.value),
    ...Object.fromEntries(capabilities.value.map(module => [module.code, `分配角色 / ${module.name}`])),
  }))
  const changes = computed(() =>
    grantDiff(grantsFromTree(tree.value, original.value), grantsFromTree(tree.value, selected.value)),
  )
  const openedCount = computed(() => Object.values(selected.value).filter(level => level !== 'NONE').length)

  async function load(): Promise<void> {
    loading.value = true
    loadError.value = ''
    try {
      const id = options.roleId()
      const see = options.canSeeGrants()
      const [detail, resources, grants] = await Promise.all([
        getRole(id),
        see ? (tree.value.length ? { tree: tree.value } : listResourceTree()) : { tree: [] as ResourceNode[] },
        see ? listRoleGrants(id) : null,
      ])
      tree.value = resources.tree
      role.value = detail
      const saved: Grants = {}
      for (const grant of grants?.grants ?? []) saved[grant.resource_code] = grant.level
      const next = collectGrants(tree.value, saved)
      selected.value = next
      original.value = { ...next }
    } catch (error) {
      loadError.value = errorMessage(error, '暂时无法加载这个角色，请稍后重试。')
    } finally {
      loading.value = false
    }
  }

  /** 只刷新成员数、版本号这类统计，失败不打扰。 */
  async function refreshRole(): Promise<void> {
    try {
      role.value = await getRole(options.roleId())
    } catch {
      /* 仅刷新统计数字 */
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

  function reset(): void {
    selected.value = { ...original.value }
  }

  async function save(): Promise<void> {
    const current = role.value
    if (saving.value || !current || !changes.value.length || options.readonly()) return
    const summary = changes.value
      .map(item => `${names.value[item.code] ?? item.code}：${LEVEL_TEXT[item.from]} → ${LEVEL_TEXT[item.to]}`)
      .join('\n')
    saving.value = true
    try {
      await ElMessageBox.confirm(summary, `保存「${current.name}」的 ${changes.value.length} 项权限修改？`, {
        type: 'warning',
        confirmButtonText: '保存',
        cancelButtonText: '再看看',
        customClass: 'confirm-lines',
      })
    } catch {
      saving.value = false
      return
    }
    try {
      const result = await replaceRoleGrants(current.id, {
        version: current.version,
        grants: grantsFromTree(tree.value, selected.value),
      })
      role.value = { ...current, ...result.role }
      original.value = { ...selected.value }
      options.saved()
      ElMessage.success(
        options.justCreated() ? '权限已保存。下一步：到「成员」把角色分给同事' : '权限已保存，成员下次操作时即生效',
      )
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

  return {
    role, tree, selected, original, loading, saving, loadError,
    groups, capabilities, names, changes, openedCount,
    load, refreshRole, confirmDiscard, reset, save,
  }
}
