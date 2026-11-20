import { describe, expect, it } from 'vitest'
import source from './SamplePreviewTable.vue?raw'

// 单测跑在 node 环境、不挂组件，这里按模板源码守住 P3-25 引入过的键盘回归：
// 整行 role="button" 带 @keydown.enter.prevent 时，焦点在行内「试发」按钮上按回车会冒泡到行、被 preventDefault，
// 打开的是详情而不是试发；按钮套在 role="button" 里读屏也说不清。
const template = source.slice(source.indexOf('<template>'), source.indexOf('</template>'))
const rowTag = template.slice(template.indexOf('<tr\n          v-for'), template.indexOf('>', template.indexOf('<tr\n          v-for')))

describe('SamplePreviewTable 键盘操作', () => {
  it('数据行不是按钮，不拦截行内按钮的回车和空格', () => {
    expect(rowTag).toContain('v-for="row in items"')
    expect(rowTag).not.toContain('role="button"')
    expect(rowTag).not.toContain('@keydown')
    expect(rowTag).not.toContain('tabindex')
  })

  it('键盘用行号按钮打开详情，试发是独立的原生按钮', () => {
    expect(template).toMatch(/<button\s+type="button"\s+class="matrix__no"[\s\S]*?@click\.stop="emit\('pick', row\.row\)"/)
    expect(template).toMatch(/<button\s+v-if="canRun"\s+type="button"\s+class="matrix__btn"\s+@click="emit\('trial', row\.row\)"/)
    expect(template.match(/role="button"/g)).toBeNull()
  })
})
