# UI 开发与复用指南

适用于已发布模块及未来的客户、招投标等模块。以用户最终确认、业务字段定义、[DESIGN.md](../../DESIGN.md)、[UX-CONTRACT.md](../../UX-CONTRACT.md) 为依据。

## 0. 适配范围

**只适配电脑端，下限 1024px。** 大中小屏按 1920 / 1440 / 1280 / 1024 四档验收，宽屏另查 2560px 避免表格只占半幅。

代码里仍保留 767px 以下的移动端分支（双行顶栏、窄侧栏、`BusinessTable` 摘要卡片、`FilterBar` 折叠），本文与 DESIGN.md、UX-CONTRACT.md 中描述它们的段落如实反映现有实现，**但手机端不再是验收目标，也不保证可用**。不必为手机端新增适配，也不要因为"手机上不好看"去改桌面行为。

## 1. 不得改变的规则

1. 一列对应一个字段。单元格只显示该字段，不在名称下加部门、行业、编码等其他字段。同一字段可换行、截断，详情提供完整值。
2. 页面顺序为：筛选 → 总数与操作栏 → 结果 → 分页；监测类页面可在筛选前展示真实概览。列表标题只作辅助技术定位，不可见；不要另加重复页面大标题/泛化说明，详情和编辑保留对象名称。桌面一次展示全部筛选项；手机字段多于 1 个才收起为「更多筛选」。操作栏顺序为新增、上传 Excel、下载 Excel、操作记录、列设置；根据实际权限显示。已有特殊业务动作保留原有权限和确认。
3. 上传和下载均保留清晰文字入口，不另建占据页面顶部的大块导入区域。不改 Excel 主键、去重、覆盖、导出范围。
4. 列设置使用“列设置 已选/全部”文字按钮，支持逐列勾选、显示全部列（全选）、恢复默认列；至少一个数据列，固定操作列不参与计数。
5. 当前页全部字段必须能在列设置和详情里找到。隐藏字段不从数据对象、编辑表单或导出中删除。列全选不等于记录全选。
6. 业务工作台不添加无实际含义的状态、统计卡片、营销插画或装饰英文。登录左侧可使用用户确认的客群关系图介绍完整产品范围；未完成模块继续受发布和权限门禁控制。

## 导航接入

顶部只展示当前账号可见的一级模块，左侧只展示当前模块的子菜单。一级模块顺序只由 iam 菜单 `sort_order` 决定（系统管理、政策、码表管理、AI提问），前端不要再排序；根地址进入首个可见模块，无菜单沿用空权限页，不提供工作台。新增页面需登记路由及 `router/menu.ts`，并在 `layouts/workspace.ts` 配置用途说明和独立语义图标；统一 Element Plus Icons、17px、继承菜单颜色，禁止按父模块复用同一个图标。详情页用 `meta.menuPath` 关联所属列表。标志使用 `assets/brand/telelands-logo.svg`，不重绘或改变比例。

顶栏76px，品牌/侧栏共用216px（1100px及以下200px）。账号固定左下角。基础色与宽高 token 由 theme.css 管理；外壳/列表适配由 workspace.css 管理，不新增页面专属基础色板。不存在设计预览分支；旧预览 URL 会清理参数并进入正式界面。

## 2. 公共组件所有权

路径均相对仓库根目录。

| 能力 | 复用位置 | 页面负责 |
|---|---|---|
| 页面结构、总数、分页、加载失败 | `frontend/src/components/ListPage.vue` | title/hint、total/page/pageSize/loading/error，retry/change处理；结果区必须用 ScrollPort；概览区走 `summary` 插槽（筛选之前，不参与拉伸） |
| 结果区滚动 | `frontend/src/components/ScrollPort.vue` | 常显横/纵滑槽；两指分轴；默认每页 20 条时未露出的行必须能上下滚到 |
| 查询 | `frontend/src/components/FilterBar.vue`、`FilterSelect.vue` | query 与 applied；桌面展开全部字段，advanced 只作字段分组，桌面不折叠。`FilterSelect` 一律多选，query 里筛选字段默认值是 `[]`（不是 `''`），重置也赋 `[]`；状态卡片这类「点一下筛选、再点取消」的入口用 `toggleValue`。几百万行的名称、标题字段用 `FilterKeyword.vue`（关键词输入框，同样以 `string[]` 做 v-model，回车 emit search），后端照旧 `ilike_any`，并给该列建 pg_trgm 的 GIN 索引；不要再放进 `*_OPTION_COLUMNS` 去重取候选 |
| 业务表格/详情/手机摘要 | `frontend/src/components/BusinessTable.vue` | items、完整columns、selected、titleKey、可选summaryKeys、canWrite/loading/filtered，edit/reset；详情抽屉底部的动作用 `#detail-actions="{ row, close }"` 插槽；批量操作传 `selectable`，用 `useTableSelection`：`:ref="selection.bindTable"`、`@selection-change="checked = $event"`，操作完 `selection.clear()`；选一个选项的批量操作用 `BatchChoiceDialog`（选项带后果说明，跳过的原因弹窗列出） |
| 账号菜单 | `frontend/src/layouts/UserAccountMenu.vue` | 侧栏底部；显示名 + `/me.roles` |
| 浮层焦点 | `frontend/src/layouts/AdminLayout.vue` | 打开时把焦点送进浮层、关闭后送回触发按钮；落回 body 会让键盘用户从头 Tab |
| 键盘焦点描边 | `frontend/src/styles/workspace.css` | 全局描边只给链接、按钮、复选框和单选框。能打字的输入框鼠标点一下也算 `:focus-visible`，不要给 `input` 加全局 outline：Element Plus 输入框靠外框变色表示聚焦，再描一圈就是框里套框；自己写的原生输入框自带聚焦样式 |
| 显示列与浏览器记忆 | `frontend/src/components/ColumnPicker.vue` | 与表格共享 selected；完整columns与defaults |
| 字段列类型 | `frontend/src/components/dataColumns.ts` | prop与API字段对应；label简明、fullLabel保留原名；可选width/minWidth/grow/wrap/time/link |
| 列顺序与宽度计算 | `frontend/src/components/dataColumnLayout.ts` | layoutDataColumns固定短字段、让长字段吸收余量；不按首列特殊处理 |
| 分组业务表单 | `frontend/src/components/GroupedFields.vue` | 完整字段groups、表单model、submitError，保存前validate；字段可设 `choices`（下拉单选）、`date`（日期选择器，值为 YYYY-MM-DD）或 `disabled`（只读，如编辑时不能改的编号） |
| 业务记录新增/编辑 | `frontend/src/components/RecordEditorDrawer.vue` + `composables/useRecordEditor.ts` | `useRecordEditor({ noun, groups, defaults?, create, update, check?, refresh })`，`update` 自己带上 `version`；列表行 `@edit="editor.openEdit"`、新增按钮 `editor.openCreate`。抽屉内置分组表单、必填与跨字段校验（`check`）、409 冲突保留草稿并提示、未保存离开确认，页面不自己拼抽屉 |
| 表格列 + 编辑字段合成完整列 | `frontend/src/composables/useDetailColumns.ts` | `useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)` 返回 `columns/defaults/selected`：编辑表单里有、表格里没有的字段追加到列设置和详情，ColumnPicker 与 BusinessTable 共用这一份 |
| 列表加载 | `frontend/src/composables/useListLoader.ts` | 传 `requested/commitPage`（来自 useListQuery）、`fetch`、`errorText`；返回 items/total/loading/loadError/resultFiltered/load。只采用最后一次请求的结果，不要在页面里再写请求序号 |
| 系统字段验证 | `frontend/src/composables/useFieldValidation.ts` | 字段错误、提交验证，不覆盖业务规则 |
| 未保存保护 | `frontend/src/composables/useUnsavedForm.ts` | visible、表单快照、saving；接close/beforeClose。业务记录抽屉已由 useRecordEditor 接好，系统表单单独用 |
| 上传入口 | `frontend/src/components/ImportButton.vue` | `hint` 写去重口径和失败时整批退回还是逐行跳过；`upload` 自己调导入接口并返回 false |
| 下载入口 | `frontend/src/components/ExportButton.vue` + `composables/useExcelExport.ts` | `useExcelExport({ path, filename, filters: () => filtersForExport(listQuery.applied) })` 给出 `exporting/onExport`；按钮 `:allowed="auth.canExport(资源)"`，没有导出档时保留但禁用并悬停说明（工具栏入口必须保留） |
| 操作记录入口 | `frontend/src/components/AuditLogButton.vue` | `module` 填资源编码，点击跳到操作日志并按该模块筛选；没有操作日志查看权限时自动隐藏 |
| Excel 下载底层 | `frontend/src/api/download.ts` | `downloadFile` 负责 401 续期和统一中文错误；页面一般经 useExcelExport 调用，不要用裸 fetch。导出传 applied 不传 query |
| 权限展示 | `frontend/src/permissions/catalog.ts`、`permissions/matrix.ts`、`modules/system/roles/PermissionTable.vue` | 按菜单分组，名称与菜单一致，一项一档。有导出动作才出现「导出」，有写操作才出现「管理」。「分配角色」单独放在菜单列表下面。说明从资源树推导，不在页面里手写模块清单。勾选联动、整组勾选、锁定、搜索等纯逻辑在 `matrix.ts`（有单测），组件只渲染。新增模块只需在 iam 目录登记动作并给导出动作标 `EXPORT` |
| 详情子页 | `router/routes.ts` 的 `meta.menuPath` | 不在菜单里的详情页填所属列表路径，面包屑与侧栏高亮自动挂到列表下 |
| 筛选项候选值 | `frontend/src/composables/useFilterOptions.ts` | `v-bind="filters.bind('字段')"`；候选少的字段整份预发、本地过滤，候选多的自动转服务端搜索。不要再自己 reactive 一份 options |
| 查询与 URL 恢复 | `frontend/src/composables/useListQuery.ts` | `useListQuery(query, load, 私有字段?)`；FilterBar 直接接 `@search="listQuery.search"`（回第一页、生效草稿、加载）和 `@reset="listQuery.resetFilters"`（筛选恢复初始值，每页条数不变）。状态卡片这类单列切换用 `replaceApplied` + `toggleValue` |
| 上传状态与结果 | `frontend/src/components/ExcelImportProgress.vue`、`ExcelImportResult.vue` | 原模块导入接口及结果，不复制业务去重逻辑；结果文件不是校验报告时（如用户导入的初始密码）用 `report_note` 换掉默认说明 |
| 导航/基础色/字体/间距 | `frontend/src/layouts/AdminLayout.vue`、`layouts/workspace.ts`、`frontend/src/styles/theme.css`、`styles/workspace.css` | 路由、发布配置、资源权限；账号放侧栏底部，不复制导航或另建色板 |
| 登录品牌区/认证 | `frontend/src/views/LoginView.vue`、`frontend/src/assets/login/customer-hub.webp` | 左侧客群关系图；爬虫监测独立无连线；800px及以下隐藏图并保留简介；右侧沿用认证表单 |

系统用户、角色、审计等专门二维表目前复用 ListPage，但不强行迁移为业务记录表；原有专门操作和权限语义必须保留。

## 3. 当前默认列清单

默认即完整字段集合，由 `useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)` 生成（表格列在前，编辑表单里多出来的字段追加在后），`defaults` 等于全部字段键；操作列另计。用户可以隐藏不需要的列，刷新保留个人选择，显示全部/恢复默认均回到全字段。新增模块沿用该规则。

| 路由 | 默认/全部数据列数量 |
|---|---|
| `/policy/sources` | 19/19（表格列 16 + 省市区编码 3） |
| `/policy/base-tags` | 20/20 |
| `/policy/interpretations` | 31/31（表格列 30，含数据状态、场景同步时间；+ 租户标识 1） |
| `/codebook/policy-types` | 8/8 |
| `/codebook/scenarios` | 35/35 |
| `/codebook/area-codes` | 15/15 |
| `/policy/crawler-monitoring` | 8/8（只读，无编辑表单） |
| `/ai/models` | 21/21 |

ColumnPicker 按用户ID和route.path保存字段键（存储键 `zt:columns:v2:…`）；更早一版存储里的系统核心列默认自动迁移为全部，真实自定义选择保留。新模块无须传 legacyDefaults；六个业务表页保留该参数仅用于旧偏好迁移。

手机仍为摘要：titleKey主字段，加summaryKeys中最多3个已选其他字段；完整字段在详情读取。桌面全字段不意味着手机逐卡铺开35个字段。

## 4. 接入步骤

新增一个业务列表页 = 一份 `fields.ts` + 一个页面组件。参照 `frontend/src/modules/policy/sources/`（`SourceList.vue`，含地区编码跨字段校验）或 `policy/base-tags/`（`BaseTagList.vue`，最简单的完整示例）；字段多、表格只放少数列的参照 `codebook/scenarios/`。

1. 核对 API、中文字段定义、编辑字段、权限及导入导出规则。新增字段时同步 `fields.ts` 和后端契约。
2. 写 `fields.ts`，导出三样：
   - `TABLE_COLUMNS: DataColumn[]`：按业务字段顺序的表格列，宽度按下文「列宽配置」；
   - `SUMMARY_KEYS`：窄屏摘要字段；
   - `EDITOR_GROUPS: EditorGroup[]`：编辑抽屉的字段分组，必填、长度、提示都写在这里。
3. 页面组件按 `BaseTagList.vue` 的结构组装：`useListQuery` + `useListLoader` 负责查询与加载，`useFilterOptions` 提供筛选候选，`useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)` 给出列设置与表格共用的完整列，`useRecordEditor` + `RecordEditorDrawer` 负责新增编辑，`useExcelExport` + `ExportButton`、`ImportButton`、`AuditLogButton` 组成工具栏。页面只写本模块的接口调用、筛选字段和导入说明，不复制公共组件内部布局。
4. 新菜单依现有路由/发布/权限体系接入顶部一级模块和左侧子菜单，不能只添加一个不受权限约束的链接。
5. 按第6节验收，并确认用户访问的实际服务已更新。

列设置与表格之间的接口（摘自 `BaseTagList.vue`）：

```vue
<template #tools>
  <ColumnPicker
    v-model="selected"
    :columns="columns"
    :defaults="defaults"
  />
</template>
<!-- 放在 ListPage 默认插槽内 -->
<BusinessTable
  :items="items"
  :columns="columns"
  :selected="selected"
  :summary-keys="SUMMARY_KEYS"
  title-key="policy_name"
  :can-write="canWrite"
  :loading="loading"
  :filtered="resultFiltered"
  @reset="listQuery.resetFilters"
  @edit="editor.openEdit"
/>
<!-- 与 ListPage 并列 -->
<RecordEditorDrawer :editor="editor" :groups="EDITOR_GROUPS" />
```

`title-key` 必须是该模块真实主字段。组件不支持 secondary-key，不要重新加入它。DataColumn.prop不能用拼接的“名称+部门”取代字段键。

过长表头用 `label` 显示简明名称，`fullLabel` 留存原业务名称，不能直接改写API或Excel字段定义。表头和列设置保持同名，详情展示完整名。已采用：网站梳理和抓取的优先级→抓取优先级；数据类型及抓取规则长句→数据类型；目标客户当前政策影响客户群→目标客户；当前政策出台时间→出台日期；项目一级/二级产品名称→一级/二级产品；项目一/二/三级场景名称→一/二/三级场景。

### 列宽配置

`titleKey` 仅负责点击详情和手机标题，不决定列宽。不要在共享组件里把第一列强制设成宽列，也不要开启自动均分宽度。

| 字段 | 配置参考 | 规则 |
|---|---|---|
| 省份、状态、短编码 | `width: 100–120` | 默认/全部/仅一列均不拉伸；宽度须能容纳表头 |
| 省市区名称、政策类型名 | `width: 160` | 独立列，不与编码混排 |
| 完整时间戳 | `width: 190, time: true` | 容纳北京时间和秒数 |
| 20位行业场景编码 | `width: 220` | 不转数字、不丢前导零 |
| 长标题/名称 | `minWidth: 240–340, grow: 1或2` | 仅此类字段吸收空余宽度；需逐页核对 |
| 定义/描述 | `minWidth: 300–360, grow: 1` | 单行省略，悬停和详情可读完整内容 |

有 `width` 时该列固定；弹性列配置 `minWidth/grow`，未声明grow的列不分配余量。表格外框必须铺满内容区，与操作栏和分页右边缘对齐；不能用maxWidth限制表格总宽度。全列超过容器时在 ScrollPort 内横向滚动，操作列 CSS sticky 贴右侧。用户仅选择少量短字段时保留其紧凑宽度，允许表内空白。六个业务表表头通常40px、数据行44px；系统专用表保留已有操作密度。长内容单行省略，不挤高整行。系统用户/角色/审计同样走 ListPage + ScrollPort。不要写滚动提示文案，也不要用 Element Plus 悬浮条替代常显滑槽。

## 5. 更新页面

当前页面来自服务器上的 frontend 镜像。改了前端源码后，按 [部署与维护](部署与维护.md) 同步并重建 `frontend`，只刷新浏览器不会变。

本机 `pnpm dev` 只在脱离服务器单独看界面时使用，不能代替服务器上的镜像。不要为了改页面去启动 P6。

## 6. 验收与文档同步

- 检查一列一字段、默认即全字段、列设置数量正确、全部显示/默认恢复、刷新保留偏好；横滑到末列时操作列不遮挡数据。
- 检查筛选：每个下拉都能选多个值，多选结果是同字段「或」、跨字段「且」，导出带同样的多值条件；桌面一次看到全部条件；改条件未点查询出现「条件已改…」；查询后为「已筛选 N 项」；重置在无条件时禁用。
- 检查结果区底边/右侧常显滑槽；默认 20 条时若首屏不足 20 行，必须能上下滚完全页；触控板上下不串成左右。
- 检查侧栏底部账号：显示名 + 角色；菜单向上弹出，不恢复右上角账号芯片。登录左侧使用已确认的客群关系图，节点不充当模块入口；爬虫监测不与客群相连，右侧认证行为保留。
- 每个列表检查默认全字段和自定义列：首列宽度合理，恢复全列不跳位；横向滚动至末尾仍能操作。按 1920 / 1440 / 1280 / 1024 四档检查，另查 2560px 宽屏避免窄视口看似正常而宽屏表格只占半幅。手机端不检查。
- 检查查询、分页、返回恢复；首次空数据、无匹配、加载、请求错误/重试；编辑校验、保存成功、失败保留、取消/离开保护。
- 检查上传和下载都可用、反馈明确；模拟写入用例优先隔离/模拟接口，不拿真实数据随意测试。
- 检查 1024px 起各档桌面宽度、长文本、键盘焦点、列设置浮层、无整页横向溢出。系统二维表允许局部横向滚动。
- frontend目录运行 `pnpm run type-check`、`pnpm run lint`、`pnpm run test`、`pnpm run build`。UI行为修改需补做浏览器检查；纯文档修改核对源码、相对链接和历史口径即可，不宣称新跑了业务测试。
- 修改视觉值同步DESIGN.md；修改行为同步UX-CONTRACT.md；改组件API、默认列或服务入口同步本文件。文档只写现行做法，不把历史截图和未跑测试描述成当前验收。

## 带概览的监测列表

参照 `frontend/src/modules/policy/crawler-monitoring/CrawlerMonitoring.vue`（爬虫监测）。概览放在 `ListPage` 的 `summary` 插槽，整块是 `CrawlerOverview.vue`：一行六张同尺寸卡片（网站总数、正常、关注、停更、数据总量、近 7 天采集），1280px 及以下折成两行三张；卡片下一行左趋势图、右健康结构（3:2，1280px 及以下上下排），省份分布再单独占一整行（竖柱图与卡片可切换）。卡片保持正常尺寸，不能靠压缩卡片适应一屏。

- 图表一律用 `components/charts/BaseChart.vue`（传 `option`、中文 `label`、`height`，点击图形发 `select`）。option 由纯函数生成并写单测（参照同目录 `charts.ts`），配色用 `chartPalette()`；新图表类型先在 `components/charts/echarts.ts` 注册。

- 正常、关注、停更三张状态卡片是 `<button>`，点击把该状态加入已生效的状态筛选并立即刷新明细，再点一次移出；用 `listQuery.replaceApplied('status', toggleValue(...))`，不带上用户还没点查询的草稿。选中态用浅蓝底加描边并设 `aria-pressed`，不只靠颜色。
- 指标名称与统计口径一致，卡片底部一行写口径（如「7 天内有新数据入库」，天数取接口返回的阈值）。大数用「万/亿」缩写，完整数值放在悬停提示里。
- 同步时间放在概览标题区；同步失败、意外中断、运行中、首次未同步、超时未更新用独立的提示条展示。概览可收起，收起后集中看列表；概览请求失败只在概览区显示重试，不影响明细。
- `ListPage` 检测到 `summary` 插槽后解除一屏上限，结果高度为 `clamp(440px, calc(100dvh - 220px), 880px)`；页面自然纵向滚动，表格保留 `ScrollPort` 双向滚动。验收时滚动到结果区核对第一行可点击、分页可达、横向拖动后操作列不遮盖字段。

## 任务调度复用示例

`frontend/src/modules/system/scheduler/`：`SchedulerList.vue` 是系统配置型短列表，复用 ListPage（隐藏分页）、ColumnPicker、useUnsavedForm，设置计划用 480px 对话框；`SchedulerHistoryDrawer.vue` 是可分页的执行记录抽屉，状态与请求逻辑在 `useSchedulerHistory.ts`，状态文案和标签颜色在 `runStatus.ts`。列表和打开中的记录抽屉每 5 秒静默刷新，页面隐藏时暂停，后台轮询不反复显示加载遮罩。`/system/scheduler` 是页面路径，`/api/v1/policy/scheduled-jobs` 是服务接口，权限归属由资源目录决定，不按前端 URL 推断。配置表单必须携带版本号；失败保留填写值；执行成功指“已入队”，不把请求成功当成同步已完成。

## 工作台页面（AI提问）

`frontend/src/modules/ai/`：提示词模板、批量任务、多轮对话不是普通业务字段列表，不套 `ListPage`，内容放在白底细边框面板（`shared/ai.css` 的 `.ai-panel`）里；页面标题只给读屏（`.ai-sr-only`）。提示词模板是列表页 `prompts/PromptListPage.vue` 加编辑页 `prompts/PromptEditorPage.vue`（路由 `/ai/prompts/:id`，新建用 `new`，保存后 `router.replace` 成模板 ID，同一条路由不重建页面）。编辑页顶部的流程条 `FlowBar.vue` 和列表的两列状态都由 `prompts/templateStatus.ts` 的纯函数（`releaseState` / `sampleState` / `flowSteps`，有单测）算出，改判断先改它；右栏 `TestPanel.vue` 是「试发一条」（`TrialPanel.vue`）和「样本试跑」（`SampleRunPanel.vue`，运行中每 2 秒刷新，跑完状态行有「下载结果」，按试跑 ID 下载，权限看 `ai.prompts` 的导出档）两个页签。左栏的单一滚动靠 `PromptEditor` 的输入框不自己滚：textarea 绝对定位盖在同字体的高亮层上，高度由高亮层撑开，改字体、内边距要两层一起改。上线审核是 `ReleaseDrawer.vue`（草稿和线上一样时切成只看线上版本，`upToDate`），提示词差异用 `prompts/lineDiff.ts`（按行 LCS，折叠没变的行，有单测）。批量任务主页 `batch/BatchRunsPage.vue` 是筛选加任务表，新建是 `NewBatchTask.vue` 抽屉（只能选上线的模板，选好文件先调 `/ai/batch-runs/input-preview` 检查，发起是 `/ai/batch-runs` 的 multipart，其他参数放 query），详情是 `BatchRunDrawer.vue`；停止、重跑、删除、下载的确认文案在 `batch/runActions.ts`，列表和详情共用。逐行结果统一用 `shared/RunRows.vue`，一行多条结果的摆法在 `shared/runRowLayout.ts`（有单测）。多轮对话是占满内容区高度的单个对话面板，`AnswerTranscript` 用 `variant="chat"` 居中成阅读列。

- 提示词编辑器是 `prompts/PromptEditor.vue`：透明 textarea 叠在同字体的镜像层上，镜像层把变量渲染成 `<mark>` 做高亮，`@` 候选按光标位置弹出；变量的分段和状态判断是 `prompts/promptVariables.ts` 里的纯函数（有单测）。镜像层由渲染函数生成，样式要用 `:deep(mark...)` 才能命中。Ctrl/⌘ + Enter 试发，Ctrl/⌘ + S 保存。
- 类型、模型、码表、输出字段、测试样本和政策类的定时任务适配在 `prompts/PromptSettings.vue`，常驻在编辑器下方，不要再收进折叠区：它们决定结果长什么样。码表下拉里「上传的码表文件」在库里是空串，Element Plus 会把空串当未选，页面用哨兵值 `uploaded` 代替，不要改回空串。

- 流式回答统一用 `shared/useAnswerStream.ts`（底层 `api/eventStream.ts`：带令牌和 CSRF、401 续期重试一次、错误还原成中文提示），消息列表 `AnswerTranscript.vue`，用量和费用 `StreamStatsBar.vue`，模型选择 `ModelPicker.vue`（未配密钥的模型可见但不可选）。事件处理是 `shared/streamEvents.ts` 里的纯函数，加新事件先改它和单测。
- 下载走 `shared/downloads.ts`（底层 `downloadFile`），不放在 `api/ai.ts`：契约测试会逐个调用 api 目录导出的函数。
- 模板编辑用 `useUnsavedForm`：返回列表、离开页面前提示未保存的修改；有未保存的修改时不能样本试跑、不能上线。附件上传、删除、上线、试跑状态变化只更新模板信息，不动表单草稿。
- 批量任务列表有任务在排队或运行时每 2 秒刷新，全部结束后停止轮询。详情抽屉的逐行结果不跟着每次进度刷新：只列前 50 行，这几行都有结果后再跑也不变，所以只在还有没跑到的行（只看失败时是失败数变了）时重读，至少隔 10 秒；状态变化马上重读。

