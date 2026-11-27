<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowDown, ArrowRight, Moon, Sunny, User } from '@element-plus/icons-vue'
import UserAccountMenu from '@/layouts/UserAccountMenu.vue'
import { useWorkspace } from './workspace'
import { useMenuBadges } from './menuBadges'
import { useTheme } from '@/composables/useTheme'
import logoUrl from '@/assets/brand/telelands-logo.svg'
import '@/styles/workspace.css'

const { groups } = useWorkspace()
const { counts: badges } = useMenuBadges()
const { isDark, toggleTheme } = useTheme()
const route = useRoute()
const activePath = computed(() => (typeof route.meta.menuPath === 'string' && route.meta.menuPath) || route.path)
const activeGroup = computed(() => groups.value.find(group => group.entries.some(entry => entry.path === activePath.value)))
// 403、个人设置不在任何菜单下。侧栏继续显示这个角色能进的菜单，避免只剩「个人设置」。
const sidebarGroup = computed(() => activeGroup.value ?? groups.value[0])
const firstModulePath = computed(() => groups.value[0]?.entries[0]?.path || '/no-modules')
const collapsed = ref<Record<string, boolean>>({})
function toggleSection(id: string) {
  collapsed.value[id] = !collapsed.value[id]
}
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
      <span class="workspace-platform-name">鲲宇数智</span>
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
          <el-icon
            class="domain-icon"
            aria-hidden="true"
          >
            <component :is="group.icon" />
          </el-icon>
          <span>{{ group.title }}</span>
        </router-link>
      </nav>
      <div class="workspace-masthead-actions">
        <button
          type="button"
          class="theme-toggle-btn"
          :title="isDark ? '切换到浅色模式' : '切换到深色模式'"
          :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
          @click="toggleTheme"
        >
          <el-icon :size="16">
            <Sunny v-if="isDark" />
            <Moon v-else />
          </el-icon>
        </button>
        <UserAccountMenu tone="header" />
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
          <template v-if="sidebarGroup?.sections?.length">
            <div
              v-for="sec in sidebarGroup.sections"
              :key="sec.id"
              class="workspace-section"
            >
              <button
                type="button"
                class="workspace-section-title"
                :aria-expanded="!collapsed[sec.id]"
                @click="toggleSection(sec.id)"
              >
                <el-icon aria-hidden="true">
                  <ArrowRight v-if="collapsed[sec.id]" />
                  <ArrowDown v-else />
                </el-icon>
                <span>{{ sec.title }}</span>
              </button>
              <div
                v-show="!collapsed[sec.id]"
                class="workspace-section-items"
              >
                <router-link
                  v-for="entry in sec.entries"
                  :key="entry.path"
                  :to="{ path: entry.path }"
                  :class="{ 'is-active': activePath === entry.path }"
                  :aria-current="activePath === entry.path ? 'page' : undefined"
                >
                  <el-icon aria-hidden="true">
                    <component :is="entry.icon" />
                  </el-icon>
                  <span>{{ entry.title }}</span>
                  <span
                    v-if="badges[entry.path]"
                    class="workspace-badge"
                    :title="`待审 ${badges[entry.path]} 个`"
                  >
                    <span class="sr-only">待审</span>{{ badges[entry.path]?.toLocaleString() }}
                  </span>
                </router-link>
                <div
                  v-if="sec.entries.length === 0"
                  class="workspace-section-empty"
                >
                  {{ sec.emptyHint || '暂无模块' }}
                </div>
              </div>
            </div>
          </template>
          <template v-else-if="sidebarGroup">
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
              <span
                v-if="badges[entry.path]"
                class="workspace-badge"
                :title="`待审 ${badges[entry.path]} 个`"
              >
                <span class="sr-only">待审</span>{{ badges[entry.path]?.toLocaleString() }}
              </span>
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
      </aside>
      <main
        id="workspace-main"
        class="workspace-main"
        tabindex="-1"
      >
        <router-view v-slot="{ Component }">
          <transition
            name="page-fade"
            mode="out-in"
          >
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>
