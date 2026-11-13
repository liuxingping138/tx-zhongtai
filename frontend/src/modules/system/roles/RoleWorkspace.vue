<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Search } from '@element-plus/icons-vue'

import { listAllRoles } from '@/api/system'
import { errorMessage } from '@/api/errors'
import type { RoleItem } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import RoleDetail from './RoleDetail.vue'
import RoleFormDialog, { type RoleFormMode } from './RoleFormDialog.vue'

/**
 * 角色与权限：左边角色列表，右边当前角色的权限和成员。
 * 角色通常只有十来个，左边一次取全，本地搜索；地址里的 roleId 决定右边显示谁。
 */
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const canManageRoles = computed(() => auth.canFull('system.roles'))

const roles = ref<RoleItem[]>([])
const loading = ref(false)
const loadError = ref('')
const keyword = ref('')
const formVisible = ref(false)
const formMode = ref<RoleFormMode>('create')

const selectedId = computed(() => (typeof route.params.roleId === 'string' ? route.params.roleId : ''))

/** 内置角色在前，其次启用的，停用的放最后。 */
const visibleRoles = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  const sorted = [...roles.value].sort((a, b) =>
    Number(b.is_builtin) - Number(a.is_builtin)
    || Number(a.status !== 'active') - Number(b.status !== 'active'))
  if (!text) return sorted
  return sorted.filter(role => `${role.name} ${role.description ?? ''}`.toLowerCase().includes(text))
})

let sequence = 0
async function load() {
  const current = ++sequence
  loading.value = !roles.value.length
  loadError.value = ''
  try {
    const items = await listAllRoles()
    if (current !== sequence) return
    roles.value = items
    selectDefault()
  } catch (error) {
    if (current === sequence) loadError.value = errorMessage(error, '暂时无法加载角色，请稍后重试。')
  } finally {
    if (current === sequence) loading.value = false
  }
}

/** 进入页面没指定角色时，默认打开第一个，右边不留空白。 */
function selectDefault() {
  const first = visibleRoles.value[0]
  if (selectedId.value || !first) return
  void router.replace({ name: 'system-role-detail', params: { roleId: first.id } })
}

function select(role: RoleItem) {
  if (role.id === selectedId.value) return
  // 未保存的权限修改由右侧详情的路由守卫拦截确认。
  void router.push({ name: 'system-role-detail', params: { roleId: role.id } })
}

function openCreate() {
  formMode.value = 'create'
  formVisible.value = true
}

function onCreated(saved: RoleItem) {
  void load()
  void router.push({ name: 'system-role-detail', params: { roleId: saved.id }, query: { created: 'create' } })
}

watch(() => route.name, (name) => {
  if (name === 'system-roles') selectDefault()
})

onMounted(load)
</script>

<template>
  <div class="role-workspace">
    <h1 class="sr-only">
      角色与权限
    </h1>
    <aside
      class="role-nav"
      aria-label="角色列表"
    >
      <div class="role-nav__head">
        <span class="role-nav__title">角色 <span class="role-nav__count">{{ roles.length }}</span></span>
        <el-button
          v-if="canManageRoles"
          link
          type="primary"
          :icon="Plus"
          @click="openCreate"
        >
          新增
        </el-button>
      </div>
      <el-input
        v-if="roles.length > 6"
        v-model="keyword"
        clearable
        size="small"
        placeholder="搜索角色名称或说明"
        aria-label="搜索角色"
        class="role-nav__search"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <div
        v-if="loadError"
        class="role-nav__error"
        role="alert"
      >
        <p>{{ loadError }}</p>
        <el-button
          size="small"
          @click="load"
        >
          重新加载
        </el-button>
      </div>
      <div
        v-else-if="loading && !roles.length"
        class="role-nav__list"
        role="status"
        aria-label="角色列表正在加载"
      >
        <div
          v-for="i in 6"
          :key="i"
          class="role-skeleton-item"
        >
          <span
            class="skeleton-shimmer role-skeleton-bar"
            :style="{ width: i % 2 === 0 ? '65%' : '80%' }"
          />
        </div>
      </div>
      <div
        v-else
        class="role-nav__list"
      >
        <button
          v-for="role in visibleRoles"
          :key="role.id"
          type="button"
          class="role-item"
          :class="{ 'is-off': role.status !== 'active' }"
          :aria-current="role.id === selectedId ? 'true' : undefined"
          @click="select(role)"
        >
          <span class="role-item__name">
            {{ role.name }}
            <el-tag
              v-if="role.is_builtin"
              size="small"
              type="warning"
              effect="plain"
            >内置</el-tag>
            <el-tag
              v-if="role.status !== 'active'"
              size="small"
              type="info"
            >停用</el-tag>
          </span>
          <span class="role-item__count">{{ role.member_count ?? 0 }} 人</span>
          <span class="role-item__desc">{{ role.description || (role.is_builtin ? '全部权限，唯一能分配角色' : '还没有职责说明') }}</span>
        </button>
        <p
          v-if="!loading && !visibleRoles.length"
          class="role-nav__empty"
        >
          {{ keyword ? '没有匹配的角色' : '还没有角色' }}
        </p>
      </div>
    </aside>
    <section
      class="role-main"
      aria-live="polite"
    >
      <RoleDetail
        v-if="selectedId"
        @changed="load"
      />
      <p
        v-else-if="!loading && !roles.length && !loadError"
        class="role-main__empty"
      >
        还没有角色。{{ canManageRoles ? '点左上角「新增」创建第一个角色。' : '' }}
      </p>
    </section>

    <RoleFormDialog
      v-model="formVisible"
      :mode="formMode"
      :role="null"
      @saved="onCreated"
    />
  </div>
</template>

<style scoped src="./role-workspace.css"></style>
