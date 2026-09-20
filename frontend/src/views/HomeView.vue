<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, Collection, Document, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { pathForRouteName } from '@/router/menu'
const auth = useAuthStore()
const groups = computed(() => {
  const entries = auth.visibleMenus.filter(item => item.route_name && pathForRouteName(item.route_name))
  const grouped = new Map<string, { title: string; items: { title: string; path: string; write: boolean }[] }>()
  for (const item of entries) {
    const path = pathForRouteName(item.route_name) as string
    const parent = auth.visibleMenus.find(parent => parent.id === item.parent_id)
    const key = path.split('/')[1] || 'other'
    if (!grouped.has(key)) grouped.set(key, { title: parent?.title || (key === 'system' ? '系统管理' : key === 'codebook' ? '码表管理' : key === 'policy' ? '政策' : '业务模块'), items: [] })
    grouped.get(key)?.items.push({ title: item.title, path, write: Boolean(item.resource_code && auth.canFull(item.resource_code)) })
  }
  return [...grouped.entries()].sort(([a], [b]) => Number(a === 'system') - Number(b === 'system'))
})
</script>
<template>
  <div class="home">
    <header class="home__heading">
      <h1>工作台</h1><p>{{ auth.user?.display_name || auth.user?.username }}，从业务模块开始今天的工作。</p>
    </header>
    <el-empty
      v-if="!groups.length"
      description="当前没有可访问的模块"
    />
    <section
      v-for="[key, group] in groups"
      :key="key"
      class="workspace-group"
    >
      <h2><el-icon><component :is="key === 'policy' ? Document : key === 'codebook' ? Collection : Setting" /></el-icon>{{ group.title }}<span>{{ group.items.length }} 个模块</span></h2>
      <div class="workspace-links">
        <router-link
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          class="workspace-link"
        >
          <span><strong>{{ item.title }}</strong><small>{{ item.path === '/system/audit' ? '查看操作记录' : item.write ? '查看与维护数据' : '只读访问' }}</small></span>
          <el-icon><ArrowRight /></el-icon>
        </router-link>
      </div>
    </section>
  </div>
</template>
<style scoped>
.home { display: flex; flex-direction: column; gap: 28px; }
.home__heading h1 { margin: 0; font-size: var(--zt-title-size); font-weight: 650; }
.home__heading p { margin: 6px 0 0; color: var(--zt-ink-500); font-size: 14px; }
.workspace-group h2 { display: flex; align-items: center; gap: 10px; font-size: 16px; font-weight: 600; margin: 0 0 12px; }
.workspace-group h2 span { font-size: 12px; color: var(--zt-ink-500); font-weight: 400; margin-left: 4px; }
.workspace-links { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); overflow: hidden; }
.workspace-link { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 22px; text-decoration: none; color: var(--zt-ink-900); border-bottom: 1px solid var(--zt-border); }
.workspace-link:hover { background: var(--el-color-primary-light-9); color: var(--zt-blue-600); }
.workspace-link strong { display: block; font-size: 15px; font-weight: 600; }
.workspace-link small { display: block; margin-top: 5px; font-size: 12px; color: var(--zt-ink-500); }
@media (max-width: 1100px) { .workspace-links { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .workspace-links { grid-template-columns: minmax(0, 1fr); } .home { gap: 22px; } }
</style>
