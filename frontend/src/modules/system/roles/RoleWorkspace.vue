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
        v-else
        v-loading="loading"
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

<style scoped>
.role-workspace {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.role-nav {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 8px;
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
}

.role-nav__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px;
}

.role-nav__title {
  font-weight: 650;
  color: var(--zt-ink-900);
}

.role-nav__count {
  margin-left: 4px;
  font-weight: 400;
  font-size: 12px;
  color: var(--zt-ink-500);
  font-variant-numeric: tabular-nums;
}

.role-nav__search {
  padding: 0 4px;
}

.role-nav__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 80px;
}

.role-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 2px 8px;
  padding: 8px 10px;
  border: 0;
  border-radius: var(--zt-radius);
  background: none;
  text-align: left;
  font: inherit;
  color: inherit;
  cursor: pointer;
}

.role-item:hover {
  background: var(--zt-soft);
}

.role-item[aria-current="true"] {
  background: var(--el-color-primary-light-9);
}

.role-item[aria-current="true"] .role-item__name {
  color: var(--zt-blue-600);
  font-weight: 600;
}

.role-item:focus-visible {
  outline: 2px solid var(--zt-blue-600);
  outline-offset: -2px;
}

.role-item__name {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  min-width: 0;
  font-weight: 500;
  color: var(--zt-ink-900);
}

.role-item.is-off .role-item__name {
  color: var(--zt-ink-500);
}

.role-item__count {
  grid-row: span 2;
  align-self: center;
  font-size: 12px;
  color: var(--zt-ink-500);
  font-variant-numeric: tabular-nums;
}

.role-item__desc {
  overflow: hidden;
  font-size: 12px;
  color: var(--zt-ink-500);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-nav__empty,
.role-main__empty {
  margin: 0;
  padding: 24px 8px;
  text-align: center;
  color: var(--zt-ink-500);
}

.role-nav__error {
  display: grid;
  gap: 8px;
  justify-items: start;
  padding: 8px;
  font-size: 13px;
  color: var(--zt-ink-700);
}

.role-nav__error p {
  margin: 0;
}

.role-main {
  min-width: 0;
}

@media (max-width: 1100px) {
  .role-workspace {
    grid-template-columns: 208px minmax(0, 1fr);
  }
}

@media (max-width: 767px) {
  .role-workspace {
    grid-template-columns: 1fr;
  }

  .role-nav {
    position: static;
  }
}
</style>
