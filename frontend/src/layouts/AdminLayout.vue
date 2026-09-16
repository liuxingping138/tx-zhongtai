<script setup lang="ts">
// 管理端公共布局：顶栏 + 侧边菜单 + 内容区。
// 侧边菜单当前为空占位，真实的可见菜单由 P4 阶段接入 `/auth/permissions` 后按权限生成，
// 不在此处硬编码任何业务菜单项。
</script>

<template>
  <el-container class="admin-layout">
    <el-header class="admin-layout__header">
      <span class="admin-layout__title">中台管理端</span>
    </el-header>
    <el-container>
      <el-aside
        width="220px"
        class="admin-layout__aside"
      >
        <!-- P4 阶段：按 /auth/permissions 返回的可见菜单渲染 el-menu -->
      </el-aside>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin-layout {
  height: 100vh;
}

.admin-layout__header {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--el-border-color);
}

.admin-layout__title {
  font-size: 16px;
  font-weight: 600;
}

.admin-layout__aside {
  border-right: 1px solid var(--el-border-color);
}
</style>
