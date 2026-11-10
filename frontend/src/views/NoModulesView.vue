<template>
  <div class="status-view">
    <div class="status-view__card">
      <el-result
        icon="info"
        title="暂无可用模块"
        sub-title="当前账号没有可访问的已发布资源，请联系管理员分配权限"
      />
    </div>
  </div>
</template>

<style scoped>
.status-view {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100dvh - 140px);
  padding: 24px;
}
.status-view__card {
  width: min(460px, 100%);
  padding: 16px 24px;
  border-radius: 16px;
  border: 1px solid var(--zt-border);
  background: var(--zt-panel);
  box-shadow: 0 12px 28px var(--zt-shadow-soft), var(--zt-shadow);
}
</style>
