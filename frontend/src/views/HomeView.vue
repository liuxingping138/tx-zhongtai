<script setup lang="ts">
import { computed } from 'vue'
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
        <p>以下是你当前可以访问的模块。未发布的业务目录不会出现在这里。</p>
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
        :span="8"
      >
        <el-card
          shadow="hover"
          class="home-card"
          @click="open(item.path)"
        >
          <h3>{{ item.title }}</h3>
          <p>{{ item.level === 'FULL' ? '可管理' : '只读' }}</p>
        </el-card>
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
  border-radius: 6px;
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

.home-card {
  margin-bottom: 16px;
  cursor: pointer;
}

.home-card h3 {
  margin: 0 0 8px;
  color: var(--zt-ink-900);
  font-size: 16px;
}

.home-card p {
  margin: 0;
  color: var(--zt-ink-500);
  font-size: 13px;
}
</style>
