<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { listResourceTree, listRoleGrants, replaceRoleGrants } from '@/api/system'
import { errorMessage, isApiError } from '@/api/errors'
import type { ResourceNode, RoleItem } from '@/api/types'
import { applyParentLevel, grantDiff, grantsFromTree, type GrantLevel } from '@/permissions/levels'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const role = ref<RoleItem | null>(null)
const tree = ref<ResourceNode[]>([])
const selected = ref<Record<string, GrantLevel>>({})
const original = ref<Record<string, GrantLevel>>({})

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

async function load() {
  const roleId = String(route.params.roleId)
  loading.value = true
  try {
    const [grantData, resourceData] = await Promise.all([listRoleGrants(roleId), listResourceTree()])
    role.value = grantData.role
    tree.value = resourceData.tree
    const map: Record<string, GrantLevel> = {}
    for (const grant of grantData.grants) {
      map[grant.resource_code] = grant.level
    }
    selected.value = {}
    collect(resourceData.tree, map)
    original.value = { ...selected.value }
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

async function onSave() {
  if (!role.value) {
    return
  }
  const before = grantsFromTree(tree.value, original.value)
  const after = grantsFromTree(tree.value, selected.value)
  const changes = grantDiff(before, after)
  if (!changes.length) {
    ElMessage.info('没有变更')
    return
  }
  const summary = changes.map((item) => `${item.code}：${item.from} → ${item.to}`).join('\n')
  await ElMessageBox.confirm(summary, '确认保存以下授权变更？', { type: 'warning' })
  saving.value = true
  try {
    const result = await replaceRoleGrants(role.value.id, {
      version: role.value.version,
      grants: after,
    })
    role.value = result.role
    original.value = { ...selected.value }
    ElMessage.success('授权已保存')
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert('授权已被他人修改，请重新加载后再保存。', '版本冲突')
      await load()
    } else {
      ElMessage.error(errorMessage(error, '保存失败'))
    }
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div v-loading="loading">
    <el-page-header @back="router.push({ name: 'system-permissions' })">
      <template #content>
        配置角色授权：{{ role?.name }}
      </template>
    </el-page-header>
    <p>未发布业务资源显示为“未开发”，不能授权。父节点批量只作用于当前已发布叶子。</p>
    <el-tree
      :data="tree"
      node-key="id"
      default-expand-all
      :props="{ label: 'name', children: 'children' }"
    >
      <template #default="{ data }">
        <div class="perm-row">
          <span>
            {{ data.name }}
            <el-tag
              v-if="!data.published"
              size="small"
              type="info"
            >
              未开发
            </el-tag>
          </span>
          <el-radio-group
            v-if="data.node_type === 'resource' && data.published"
            :model-value="selected[data.code] || 'NONE'"
            :disabled="!auth.canFull('system.permissions')"
            @change="(value: GrantLevel) => onLeafChange(data.code, value)"
          >
            <el-radio-button value="NONE">
              NONE
            </el-radio-button>
            <el-radio-button value="READ">
              READ
            </el-radio-button>
            <el-radio-button value="FULL">
              FULL
            </el-radio-button>
          </el-radio-group>
          <el-radio-group
            v-else-if="data.node_type === 'directory' && data.published"
            :disabled="!auth.canFull('system.permissions')"
            @change="(value: GrantLevel) => onParentChange(data, value)"
          >
            <el-radio-button value="NONE">
              子级 NONE
            </el-radio-button>
            <el-radio-button value="READ">
              子级 READ
            </el-radio-button>
            <el-radio-button value="FULL">
              子级 FULL
            </el-radio-button>
          </el-radio-group>
        </div>
      </template>
    </el-tree>
    <div style="margin-top: 16px">
      <el-button
        v-if="auth.canFull('system.permissions')"
        type="primary"
        :loading="saving"
        @click="onSave"
      >
        保存授权
      </el-button>
      <el-button @click="router.back()">
        返回
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.perm-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 16px;
  padding-right: 12px;
}
</style>
