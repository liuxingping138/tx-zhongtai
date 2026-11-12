<script setup lang="ts">
import { computed } from 'vue'
import { Moon, Operation, Sunny } from '@element-plus/icons-vue'
import { useTableDensity, type TableDensity } from '@/composables/useTableDensity'
import { useTheme, type ThemeMode } from '@/composables/useTheme'

const { theme, setTheme } = useTheme()
const { isCompact, setDensity } = useTableDensity()

const currentDensityVal = computed<'comfortable' | 'compact'>({
  get: () => (isCompact.value ? 'compact' : 'comfortable'),
  set: (val: TableDensity) => setDensity(val),
})
</script>

<template>
  <section class="profile-card">
    <div class="card-head">
      <span class="card-head__badge"><el-icon><Operation /></el-icon></span>
      <div class="card-head__text">
        <h2>界面偏好设置</h2>
        <span class="card-head__sub">外观主题与表格信息密度即时切换</span>
      </div>
    </div>
    <div class="pref-group-list">
      <div class="pref-item">
        <div class="pref-item__label">
          <strong>外观主题</strong>
          <p>支持浅色、深色或随系统设定自动适应</p>
        </div>
        <el-radio-group
          :model-value="theme"
          size="small"
          @update:model-value="(val: any) => setTheme(val as ThemeMode)"
        >
          <el-radio-button value="light">
            <el-icon><Sunny /></el-icon> 浅色
          </el-radio-button>
          <el-radio-button value="dark">
            <el-icon><Moon /></el-icon> 深色
          </el-radio-button>
          <el-radio-button value="auto">
            跟随系统
          </el-radio-button>
        </el-radio-group>
      </div>
      <div class="pref-item">
        <div class="pref-item__label">
          <strong>表格显示密度</strong>
          <p>紧凑模式可在同屏查看更多数据行</p>
        </div>
        <el-radio-group
          v-model="currentDensityVal"
          size="small"
        >
          <el-radio-button value="comfortable">
            舒适 (44px)
          </el-radio-button>
          <el-radio-button value="compact">
            紧凑 (32px)
          </el-radio-button>
        </el-radio-group>
      </div>
    </div>
  </section>
</template>

<style scoped>
.profile-card {
  padding: 22px 24px;
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: 12px;
  box-shadow: var(--zt-shadow);
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--zt-divider);
}
.card-head__badge {
  display: grid;
  place-items: center;
  flex: 0 0 38px;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--zt-card-icon-bg);
  color: var(--zt-blue-600);
  font-size: 18px;
}
.card-head h2 {
  margin: 0;
  font-size: 15.5px;
  font-weight: 650;
  color: var(--zt-ink-900);
  line-height: 1.3;
}
.card-head__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.card-head__sub {
  font-size: 12px;
  color: var(--zt-ink-500);
  margin: 0;
}
.pref-group-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.pref-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  background: var(--zt-surface-subtle);
  border: 1px solid var(--zt-border);
  border-radius: 10px;
}
.pref-item__label strong {
  display: block;
  font-size: 13.5px;
  color: var(--zt-ink-900);
}
.pref-item__label p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--zt-ink-500);
}
</style>
