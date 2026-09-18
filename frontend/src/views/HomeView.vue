<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, Collection, Document, Setting } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { pathForRouteName } from '@/router/menu'

const auth = useAuthStore()
const router = useRouter()

const modules = computed(() =>
  auth.visibleMenus
    .filter((item) => item.route_name && pathForRouteName(item.route_name))
    .map((item) => ({
      title: item.title,
      path: pathForRouteName(item.route_name) as string,
      level: item.resource_code ? auth.resourceLevel(item.resource_code) : null,
    })),
)

function open(path: string) {
  void router.push(path)
}
</script>

<template>
  <div class="home">
    <section class="home__heading">
      <span class="home__bar" />
      <div>
        <h2>欢迎，{{ auth.user?.display_name || auth.user?.username }}</h2>
        <p>从常用模块开始今天的工作。</p>
      </div>
    </section>
    <el-empty
      v-if="!modules.length"
      description="当前没有可访问的模块"
    />
    <el-row
      v-else
      :gutter="16"
    >
      <el-col
        v-for="item in modules"
        :key="item.path"
        :xs="24"
        :sm="12"
        :lg="8"
      >
        <button
          type="button"
          class="home-card"
          @click="open(item.path)"
        >
          <span class="home-card__icon"><el-icon><component :is="item.path.startsWith('/policy') ? Document : item.path.startsWith('/codebook') ? Collection : Setting" /></el-icon></span>
          <span class="home-card__text"><strong>{{ item.title }}</strong><small>{{ item.level === 'FULL' ? '可管理' : '只读访问' }}</small></span>
          <el-icon class="home-card__arrow">
            <ArrowRight />
          </el-icon>
        </button>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.home__heading {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-height: 72px;
  padding: 16px 24px;
  background: #fff;
  border: 1px solid var(--zt-border);
  border-radius: 10px;
  box-shadow: var(--zt-shadow);
}

.home__bar {
  width: 4px;
  height: 22px;
  margin-top: 4px;
  border-radius: 4px;
  background: var(--zt-blue-600);
}

.home__heading h2 {
  margin: 0;
  font-size: 18px;
}

.home__heading p {
  margin: 6px 0 0;
  color: var(--zt-ink-500);
  font-size: 13px;
}

.home-card { display: flex; align-items: center; gap: 16px; width: 100%; margin-bottom: 16px; padding: 24px; border: 1px solid var(--zt-border); border-radius: 10px; background: #fff; text-align: left; font: inherit; cursor: pointer; transition: border-color .18s, box-shadow .18s; }
.home-card:hover { border-color: #b6cae4; box-shadow: 0 5px 18px #223c5810; }
.home-card:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 3px; }
.home-card__icon { display: grid; place-items: center; flex: 0 0 42px; height: 42px; background: #eef3fa; color: #446b9e; border-radius: 12px; font-size: 20px; }
.home-card__text { display: flex; flex-direction: column; gap: 9px; }
.home-card__text strong { color: var(--zt-ink-900); font-size: 15px; font-weight: 600; }
.home-card__text small { color: var(--zt-ink-500); font-size: 12px; }
.home-card__arrow { margin-left: auto; color: #9aaec5; }
</style>
