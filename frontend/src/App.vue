<script setup lang="ts">
// 根组件只承载路由出口；具体布局在各路由的 layout 组件中实现，
// 便于登录页等无侧边栏页面复用不同布局。
</script>

<template>
  <router-view />
</template>
