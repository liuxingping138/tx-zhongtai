<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { pendingNewScenarios, syncNewScenarios } from '@/api/policy'
import { errorMessage } from '@/api/errors'

/** 把人工验证过的新增场景写进行业场景码表。编码按现有规则生成并回填到解读行。 */
const emit = defineEmits<{ synced: [] }>()
const pending = ref(0)
const busy = ref(false)

async function refresh(): Promise<void> {
  try {
    pending.value = (await pendingNewScenarios()).pending
  } catch {
    pending.value = 0
  }
}
onMounted(refresh)
defineExpose({ refresh })

async function sync(): Promise<void> {
  if (!pending.value) {
    ElMessage.info('没有待同步的新增场景：先在列表里筛出「是否新增场景 = 是」的行，核对后把数据状态改为「人工验证」')
    return
  }
  const ok = await ElMessageBox.confirm(
    `把 ${pending.value} 条人工验证过的新增场景写进行业场景码表，按现有规则生成编码并回填到这些行。码表里已有同名同路径的场景只回填编码，不重复建。`,
    '同步新增场景到码表？',
    { type: 'warning', confirmButtonText: '同步', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!ok) return
  busy.value = true
  try {
    const result = await syncNewScenarios()
    const head = `已同步 ${result.synced} 条，其中码表新建 ${result.created} 个场景`
    if (result.failed.length) {
      const lines = result.failed.slice(0, 10).map(item => `「${item.policy_title}」：${item.reason}`)
      await ElMessageBox.alert(`${head}。以下 ${result.failed.length} 条没有同步：\n${lines.join('\n')}`, '同步结果', { type: 'warning' })
    } else {
      ElMessage.success(head)
    }
    emit('synced')
  } catch (error) {
    ElMessage.error(errorMessage(error, '同步失败，请重试'))
  } finally {
    busy.value = false
    await refresh()
  }
}
</script>

<template>
  <el-button
    :loading="busy"
    @click="sync"
  >
    同步新增场景{{ pending ? `（${pending}）` : '' }}
  </el-button>
</template>
