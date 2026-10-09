<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Search, User } from '@element-plus/icons-vue'
import UserAccountMenu from '@/layouts/UserAccountMenu.vue'
import { useWorkspace } from './workspace'
import logoUrl from '@/assets/brand/telelands-logo.svg'
import '@/styles/workspace.css'

const { groups } = useWorkspace()
const route = useRoute()
const router = useRouter()
const activePath = computed(() => String(route.meta.menuPath || route.path))
const activeGroup = computed(() => groups.value.find(group => group.entries.some(entry => entry.path === activePath.value)))
// 403 不在任何菜单下。侧栏继续显示这个角色能进的菜单，避免只剩「个人设置」。
const sidebarGroup = computed(() => activeGroup.value ?? (route.name === 'forbidden' ? groups.value[0] : undefined))
const firstModulePath = computed(() => groups.value[0]?.entries[0]?.path || '/no-modules')
const searchOpen = ref(false)
const search = ref('')
const searchInput = ref<HTMLInputElement>()
const matches = computed(() => groups.value.flatMap(group => group.entries.map(entry => ({ ...entry, group: group.title })))
  .filter(entry => `${entry.title} ${entry.description} ${entry.group}`.includes(search.value.trim())))
async function openSearch() {
  search.value = ''
  searchOpen.value = true
  await nextTick()
}
function onSearchEnter(event: KeyboardEvent) {
  if (event.isComposing) return
  event.preventDefault()
  if (matches.value[0]) navigate(matches.value[0].path)
}
function focusSearch() { searchInput.value?.focus() }
function navigate(path: string) { searchOpen.value = false; void router.push(path) }
</script>

<template>
  <div class="workspace-shell">
    <a
      class="workspace-skip"
      href="#workspace-main"
    >跳到内容</a>
    <header class="workspace-masthead">
      <router-link
        :to="{ path: firstModulePath }"
        class="workspace-brand"
        aria-label="腾信睿德，进入业务模块"
      >
        <img
          :src="logoUrl"
          alt="腾信睿德"
          width="300"
          height="83"
        >
      </router-link>
      <strong class="workspace-platform-name">业务数据运营平台</strong>
      <nav
        class="workspace-domains"
        aria-label="一级模块"
      >
        <router-link
          v-for="group in groups"
          :key="group.key"
          :to="{ path: group.entries[0]!.path }"
          :class="{ 'is-active': activeGroup?.key === group.key }"
          :aria-current="activeGroup?.key === group.key ? 'true' : undefined"
        >
          {{ group.title }}
        </router-link>
      </nav>
      <div class="workspace-header-actions">
        <button
          class="workspace-search-trigger"
          type="button"
          aria-label="查找模块"
          title="查找模块"
          @click="openSearch"
        >
          <el-icon><Search /></el-icon><span>查找模块</span>
        </button>
      </div>
    </header>
    <div class="workspace-body">
      <aside
        class="workspace-rail"
        :aria-label="(sidebarGroup?.title || '工作空间') + '子模块'"
      >
        <nav
          class="workspace-module-nav"
          aria-label="子模块导航"
        >
          <template v-if="sidebarGroup">
            <router-link
              v-for="entry in sidebarGroup.entries"
              :key="entry.path"
              :to="{ path: entry.path }"
              :class="{ 'is-active': activePath === entry.path }"
              :aria-current="activePath === entry.path ? 'page' : undefined"
            >
              <el-icon aria-hidden="true">
                <component :is="entry.icon" />
              </el-icon>
              <span>{{ entry.title }}</span>
            </router-link>
          </template>
          <template v-else>
            <router-link
              :to="{ name: 'profile' }"
              :class="{ 'is-active': route.name === 'profile' }"
              :aria-current="route.name === 'profile' ? 'page' : undefined"
            >
              <el-icon><User /></el-icon><span>个人设置</span>
            </router-link>
          </template>
        </nav>
        <div class="workspace-rail-footer">
          <div class="workspace-account">
            <UserAccountMenu />
          </div>
        </div>
      </aside>
      <main
        id="workspace-main"
        class="workspace-main"
        tabindex="-1"
      >
        <router-view />
      </main>
    </div>

    <el-dialog
      v-model="searchOpen"
      title="查找模块"
      width="560px"
      class="workspace-search-dialog"
      @opened="focusSearch"
    >
      <div class="workspace-search-field">
        <el-icon><Search /></el-icon><input
          ref="searchInput"
          v-model="search"
          aria-label="模块名称或用途"
          placeholder="输入模块名称或用途"
          @keydown.enter="onSearchEnter"
        >
      </div>
      <div class="workspace-search-results">
        <button
          v-for="entry in matches"
          :key="entry.path"
          type="button"
          @click="navigate(entry.path)"
        >
          <span class="workspace-search-result-label"><el-icon aria-hidden="true"><component :is="entry.icon" /></el-icon><span><strong>{{ entry.title }}</strong><small>{{ entry.group }} · {{ entry.description }}</small></span></span><el-icon aria-hidden="true">
            <ArrowRight />
          </el-icon>
        </button>
        <p
          v-if="!matches.length"
          role="status"
        >
          没有找到匹配模块，试试其他关键词。
        </p>
      </div>
    </el-dialog>
  </div>
</template>
