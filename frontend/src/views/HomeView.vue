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
  <div>
    <h2>欢迎，{{ auth.user?.display_name || auth.user?.username }}</h2>
    <p>以下是你当前可以访问的公共模块。未发布的业务目录不会出现在这里。</p>
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
.home-card {
  cursor: pointer;
  margin-bottom: 16px;
}
</style>
