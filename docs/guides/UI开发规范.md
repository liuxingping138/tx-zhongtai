# UI 开发与复用指南

怎么用公共组件搭页面、怎么验收。界面规则（长什么样、怎么交互、哪些决定不能推翻）见 [DESIGN.md](../../DESIGN.md)，这里不重复。

## 1. 导航接入

新增页面登记路由和 `router/menu.ts`，在 `layouts/workspace.ts` 配用途说明和独立图标（Element Plus Icons、17px、继承菜单颜色）。不在菜单里的详情页填 `meta.menuPath`，侧栏高亮挂到所属列表。新菜单走现有的路由、发布和权限体系，不能只加一个不受权限约束的链接。

`AdminLayout.vue` 是唯一的导航外壳；基础色和宽高 token 在 `styles/theme.css`，外壳和列表的样式适配在 `styles/workspace.css`，不新增页面专属色板。

重新部署后，开着的旧页面切路由会因旧分包文件不存在而失败；`router/chunkReload.ts` 在 `router.onError` 里整页刷新到目标地址一次（会话存储防循环），不要删。

## 2. 公共组件

路径相对 `frontend/src/`。

| 能力 | 复用位置 | 页面负责 |
|---|---|---|
| 页面结构、总数、分页、加载失败 | `components/ListPage.vue` | title/hint、total/page/pageSize/loading/error，retry/change 处理；结果区必须用 ScrollPort；概览走 `summary` 插槽（筛选之前，不参与拉伸）；筛选多的（操作日志）用 `expandedResults` 变体加高结果区 |
| 结果区滚动 | `components/ScrollPort.vue` | 常显横/纵滑槽；两指分轴；默认每页 20 条时未露出的行必须能上下滚到。不要用 Element Plus 悬浮条替代 |
| 查询 | `components/FilterBar.vue`、`FilterSelect.vue`、`FilterKeyword.vue` | query 与 applied；advanced 只作字段分组，桌面不折叠。`FilterSelect` 一律多选，query 里筛选字段默认值是 `[]`（不是 `''`），重置也赋 `[]`；状态卡片这类「点一下筛选、再点取消」的入口用 `toggleValue`。几百万行的名称、标题字段用 `FilterKeyword`（同样以 `string[]` 做 v-model；回车交给 FilterBar 的表单提交，组件里不要再绑 `keyup.enter`，否则一次回车查两次、还绕过输入法组合判断），后端照旧 `ilike_any`，并给该列建 pg_trgm 的 GIN 索引；不要再放进 `*_OPTION_COLUMNS` 去重取候选 |
| 筛选项候选值 | `composables/useFilterOptions.ts` | `v-bind="filters.bind('字段')"`；候选少的字段整份预发、本地过滤，候选多的自动转服务端搜索。不要再自己 reactive 一份 options |
| 查询与 URL 恢复 | `composables/useListQuery.ts` | `useListQuery(query, load, 私有字段?)`，人名等个人信息放私有字段，不写 URL；FilterBar 直接接 `@search="listQuery.search"`（回第一页、生效草稿、加载）和 `@reset="listQuery.resetFilters"`（筛选恢复初始值，每页条数不变）。状态卡片这类单列切换用 `replaceApplied` + `toggleValue` |
| 列表加载 | `composables/useListLoader.ts` | 传 `requested/commitPage`（来自 useListQuery）、`fetch`、`errorText`；返回 items/total/loading/loadError/resultFiltered/load。只采用最后一次请求的结果，不要在页面里再写请求序号 |
| 业务表格、详情 | `components/BusinessTable.vue` | items、完整 columns、selected、titleKey、可选 summaryKeys、canWrite/loading/filtered，edit/reset。详情抽屉在字段后追加内容用 `#detail-extra`，底部动作用 `#detail-actions="{ row, close }"`，不要另造平行抽屉。批量操作传 `selectable`，用 `useTableSelection`：`:ref="selection.bindTable"`、`@selection-change="checked = $event"`，操作完 `selection.clear()`；选一个选项的批量操作用 `BatchChoiceDialog`（选项带后果说明，跳过的原因弹窗列出） |
| 表格列 + 编辑字段合成完整列 | `composables/useDetailColumns.ts` | `useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)` 返回 `columns/defaults/selected`：编辑表单里有、表格里没有的字段追加到列设置和详情，ColumnPicker 与 BusinessTable 共用这一份 |
| 显示列与浏览器记忆 | `components/ColumnPicker.vue`、`components/columnSelection.ts` | 与表格共享 selected，传完整 columns 和 defaults。按用户和 route.path 存字段键（`zt:columns:v2:…`），同时记住当时页面有哪些列，之后新加的列默认显示，不会被当成用户隐藏的列。新模块不传 legacyDefaults，六个老业务表留着它只为迁移旧偏好 |
| 字段列类型 | `components/dataColumns.ts` | prop 与 API 字段对应；label 简明、fullLabel 保留原名；可选 width/minWidth/grow/wrap/time/link |
| 列顺序与宽度计算 | `components/dataColumnLayout.ts` | layoutDataColumns 固定短字段、让长字段吸收余量；不按首列特殊处理 |
| 分组业务表单 | `components/GroupedFields.vue` | 完整字段 groups、表单 model、submitError，保存前 validate；字段可设 `choices`（下拉单选）、`date`（日期选择器，值为 YYYY-MM-DD）或 `disabled`（只读，如编辑时不能改的编号） |
| 业务记录新增/编辑 | `components/RecordEditorDrawer.vue` + `composables/useRecordEditor.ts` | `useRecordEditor({ noun, groups, defaults?, create, update, check?, refresh })`，`update` 自己带上 `version`；列表行 `@edit="editor.openEdit"`、新增按钮 `editor.openCreate`。抽屉内置分组表单、必填与跨字段校验（`check`）、409 冲突保留草稿并提示、未保存离开确认，页面不自己拼抽屉 |
| 系统表单校验 | `composables/useFieldValidation.ts` | 字段错误、提交验证，不覆盖业务规则 |
| 未保存保护 | `composables/useUnsavedForm.ts` | visible、表单快照、saving；接 close/beforeClose。业务记录抽屉已由 useRecordEditor 接好，系统表单单独用 |
| 上传入口 | `components/ImportButton.vue` | `hint` 写去重口径和失败时整批退回还是逐行跳过；`upload` 自己调导入接口并返回 false。当前角色上传必定失败时传 `blocked="原因"`（信源、基础标签上传要靠省市区编码表补编码，没 `codebook.area_codes` 查看权就传），按钮禁用、悬停显示原因 |
| 上传状态与结果 | `components/ExcelImportProgress.vue`、`ExcelImportResult.vue` | 原模块导入接口及结果，不复制业务去重逻辑；结果文件不是校验报告时（如用户导入的初始密码）用 `report_note` 换掉默认说明 |
| 下载入口 | `components/ExportButton.vue` + `composables/useExcelExport.ts` | `useExcelExport({ path, filename, filters: () => filtersForExport(listQuery.applied) })` 给出 `exporting/onExport`；按钮 `:allowed="auth.canExport(资源)"`，没有导出档时保留但禁用并悬停说明。按钮文字可用默认插槽改写 |
| Excel 下载底层 | `api/download.ts` | `downloadFile` 负责 401 续期和统一中文错误；页面一般经 useExcelExport 调用，不要用裸 fetch。导出传 applied 不传 query |
| 操作记录入口 | `components/AuditLogButton.vue` | `module` 填资源编码，点击跳到操作日志并按该模块筛选；没有操作日志查看权限时自动隐藏 |
| 图表 | `components/charts/BaseChart.vue`、`echarts.ts` | 传 `option`、中文 `label`、`height`，点击图形发 `select`。option 由纯函数生成并写单测（参照 `modules/policy/crawler-monitoring/charts.ts`），配色用 `chartPalette()`；新图表类型先在 `echarts.ts` 注册。ECharts 按需注册、随页面懒加载，不进公共 vendor |
| 权限展示 | `permissions/catalog.ts`、`permissions/matrix.ts`、`modules/system/roles/PermissionTable.vue` | 按菜单分组，名称与菜单一致，一项一档。有导出动作才出现「导出」，有写操作才出现「管理」。说明从资源树推导，不在页面里手写模块清单。勾选联动、整组勾选、锁定、搜索等纯逻辑在 `matrix.ts`（有单测），组件只渲染。新增模块只需在 iam 目录登记动作并给导出动作标 `EXPORT` |
| 账号菜单 | `layouts/UserAccountMenu.vue` | 侧栏底部；显示名 + `/me.roles` |
| 浮层焦点 | `layouts/AdminLayout.vue` | 打开时把焦点送进浮层、关闭后送回触发按钮；落回 body 会让键盘用户从头 Tab |
| 键盘焦点描边 | `styles/workspace.css` | 全局描边只给链接、按钮、复选框和单选框。能打字的输入框鼠标点一下也算 `:focus-visible`，不要给 `input` 加全局 outline：Element Plus 输入框靠外框变色表示聚焦，再描一圈就是框里套框 |
| 时间 | `utils/time.ts` | 一律按北京时间显示 |
| 密码规则 | `utils/passwordPolicy.ts` | 与 iam 的 `validate_password_policy` 同一套（至少 8 位，同时有字母和数字），改一边要改另一边 |
| 登录页 | `views/LoginView.vue`、`assets/login/customer-hub.webp` | 左侧客群关系图（依据 `docs/design/登录页视觉方向.png`），800px 及以下隐藏图、保留简介；图中文字或关系改了要同时换图和替代文字 |

系统用户、角色、审计等专门二维表复用 ListPage，但不强行迁移为业务记录表；原有专门操作和权限语义必须保留。

## 3. 接入步骤

新增一个业务列表页 = 一份 `fields.ts` + 一个页面组件。参照 `modules/policy/sources/`（`SourceList.vue`，含地区编码跨字段校验）或 `policy/base-tags/`（`BaseTagList.vue`，最简单的完整示例）；字段多、表格只放少数列的参照 `codebook/scenarios/`。

1. 核对 API、中文字段定义、编辑字段、权限及导入导出规则。新增字段时同步 `fields.ts` 和后端契约。
2. 写 `fields.ts`，导出三样：
   - `TABLE_COLUMNS: DataColumn[]`：按业务字段顺序的表格列，宽度按下文「列宽配置」；
   - `SUMMARY_KEYS`：767px 以下摘要卡片显示的字段（最多 3 个），手机不验收，照常给就行；
   - `EDITOR_GROUPS: EditorGroup[]`：编辑抽屉的字段分组，必填、长度、提示都写在这里。
3. 页面组件按 `BaseTagList.vue` 的结构组装：`useListQuery` + `useListLoader` 负责查询与加载，`useFilterOptions` 提供筛选候选，`useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)` 给出列设置与表格共用的完整列，`useRecordEditor` + `RecordEditorDrawer` 负责新增编辑，`useExcelExport` + `ExportButton`、`ImportButton`、`AuditLogButton` 组成工具栏。页面只写本模块的接口调用、筛选字段和导入说明，不复制公共组件内部布局。政策两张表的详情里用 `modules/policy/shared/PolicyContent.vue` 放在 `#detail-extra` 槽位显示正文（传 `load`，按行 ID 加 `key`），段落和折叠规则在 `policyContent.ts`（有单测）。
4. 按第 1 节接入导航。
5. 按第 5 节验收，并确认用户访问的实际服务已更新。

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

`title-key` 必须是该模块真实主字段。组件不支持 secondary-key，不要重新加入它；DataColumn.prop 不能用拼接的「名称+部门」取代字段键。过长表头用 `label` 显示简名、`fullLabel` 存原名，不能改 API 或 Excel 字段定义。

### 列宽配置

`titleKey` 只负责点击详情和手机标题，不决定列宽。

| 字段 | 配置参考 | 规则 |
|---|---|---|
| 省份、状态、短编码 | `width: 100–120` | 默认/全部/仅一列均不拉伸；宽度须能容纳表头 |
| 省市区名称、政策类型名 | `width: 160` | 独立列，不与编码混排 |
| 完整时间戳 | `width: 190, time: true` | 容纳北京时间和秒数 |
| 20 位行业场景编码 | `width: 220` | 不转数字、不丢前导零 |
| 长标题/名称 | `minWidth: 240–340, grow: 1 或 2` | 仅此类字段吸收空余宽度；需逐页核对 |
| 定义/描述 | `minWidth: 300–360, grow: 1` | 单行省略，悬停和详情可读完整内容 |

有 `width` 时该列固定；弹性列配 `minWidth/grow`，没声明 grow 的列不分配余量。不要在共享组件里把第一列设成宽列，不要开启自动均分，不能用 maxWidth 限制表格总宽度。操作列用 CSS sticky 贴右侧，不用 Element Plus 的 `fixed`。业务表表头通常 40px、数据行 44px；系统专用表保留已有操作密度。

## 4. 更新页面

当前页面来自服务器上的 frontend 镜像。改了前端源码后，按 [部署与维护](部署与维护.md) 同步并重建 `frontend`，只刷新浏览器不会变。

本机 `pnpm dev` 只在脱离服务器单独看界面时使用，不能代替服务器上的镜像。不要为了改页面去启动 P6。

## 5. 验收与文档同步

按 [DESIGN.md](../../DESIGN.md) 的列表页规则逐条看一遍，另外重点查这些容易出问题的地方：

- 1920 / 1440 / 1280 / 1024 四档和 2560 宽屏：1024 不整页横向溢出、不退化成摘要卡片、上传下载入口还在；宽屏表格不只占半幅
- 横滑到末列时操作列不遮挡数据；默认 20 条首屏放不下时能上下滚完；触控板上下不串成左右
- 列设置：默认全字段、数量正确、显示全部 / 恢复默认、刷新保留偏好，恢复全列时首列不跳位
- 筛选：多选结果同字段「或」、跨字段「且」，导出带同样的多值条件
- 查询、分页、浏览器返回恢复；首次空数据、无匹配、加载、请求错误和重试
- 编辑校验、保存成功、失败保留、取消和离开保护；上传和下载都可用、反馈明确
- 写入用例优先隔离或模拟接口，不拿真实数据随意测试

frontend 目录运行 `pnpm run type-check`、`pnpm run lint`、`pnpm run test`、`pnpm run build`。UI 行为修改要补做浏览器检查；纯文档修改核对源码和相对链接即可，不宣称新跑了业务测试。

改了界面规则同步 DESIGN.md；改了组件用法、接入步骤同步本文。文档只写现行做法。

## 带概览的监测列表

参照 `modules/policy/crawler-monitoring/CrawlerMonitoring.vue`（爬虫监测），概览整块是 `CrawlerOverview.vue`，放在 `ListPage` 的 `summary` 插槽。

- 状态卡片是 `<button>`，点击把该状态加入已生效的状态筛选并立即刷新明细，再点一次移出；用 `listQuery.replaceApplied('status', toggleValue(...))`，不带上用户还没点查询的草稿。选中态设 `aria-pressed`
- 卡片底部一行写统计口径（如「7 天内有新数据入库」，天数取接口返回的阈值）
- 同步时间放在概览标题区；同步失败、意外中断、运行中、首次未同步、超时未更新用独立的提示条。概览可收起；概览请求失败只在概览区显示重试，不影响明细
- `ListPage` 检测到 `summary` 插槽后解除一屏上限，结果高度为 `clamp(440px, calc(100dvh - 220px), 880px)`；页面自然纵向滚动，表格保留 `ScrollPort` 双向滚动

## 任务调度

`modules/system/scheduler/`：`SchedulerList.vue` 汇总各服务的任务（`api/scheduler.ts` 的 `SCHEDULER_SERVICES`），复用 ListPage（隐藏分页）和 ColumnPicker；设置是右侧抽屉 `JobSettingsDrawer.vue`（`useUnsavedForm`），执行记录是可分页抽屉 `SchedulerHistoryDrawer.vue`，状态与请求逻辑在 `useSchedulerHistory.ts`，状态文案和标签颜色在 `runStatus.ts`；各任务自己的显示在 `aiTagging.ts`、`crawlerConfig.ts`、`sessionCleanup.ts`。列表和打开中的记录抽屉每 5 秒静默刷新，页面隐藏时暂停，后台轮询不反复显示加载遮罩。`/system/scheduler` 是页面路径，接口在各服务下（如 `/api/v1/policy/scheduled-jobs`），权限归属由资源目录决定，不按前端 URL 推断。配置表单必须携带版本号；失败保留填写值；执行成功指「已入队」，不把请求成功当成任务已完成。

## 工作台页面（AI提问）

`modules/ai/`：提示词模板、批量任务、多轮对话不是普通业务字段列表，不套 `ListPage`，内容放在白底细边框面板（`shared/ai.css` 的 `.ai-panel`）里；页面标题只给读屏（`.ai-sr-only`）。模型配置是例外，沿用 `ListPage` + `BusinessTable` + `RecordEditorDrawer`。

提示词模板是列表页 `prompts/PromptListPage.vue` 加编辑页 `prompts/PromptEditorPage.vue`（路由 `/ai/prompts/:id`，新建用 `new`，保存后 `router.replace` 成模板 ID，同一条路由不重建页面）。编辑页顶部的流程条 `FlowBar.vue` 和列表的两列状态都由 `prompts/templateStatus.ts` 的纯函数（`releaseState` / `sampleState` / `flowSteps`，有单测）算出，改判断先改它；右栏 `TestPanel.vue` 是「试发一条」（`TrialPanel.vue`）和「样本试跑」（`SampleRunPanel.vue`，运行中每 2 秒刷新，跑完状态行有「下载结果」，按试跑 ID 下载，权限看 `ai.prompts` 的导出档）两个页签。上线审核是 `ReleaseDrawer.vue`（草稿和线上一样时切成只看线上版本，`upToDate`），提示词差异用 `prompts/lineDiff.ts`（按行 LCS，折叠没变的行，有单测）。

批量任务主页 `batch/BatchRunsPage.vue` 是筛选加任务表，新建是 `NewBatchTask.vue` 抽屉（只能选上线的模板，「下载数据模板」调 `/ai/batch-runs/input-template` 拿只有表头的空白表，选好文件先调 `/ai/batch-runs/input-preview` 检查，发起是 `/ai/batch-runs` 的 multipart，其他参数放 query），详情是 `BatchRunDrawer.vue`；停止、重跑、删除、下载的确认文案在 `batch/runActions.ts`，列表和详情共用。逐行结果统一用 `shared/RunRows.vue`，一行多条结果的摆法在 `shared/runRowLayout.ts`（有单测）。多轮对话是占满内容区高度的单个对话面板，`AnswerTranscript` 用 `variant="chat"` 居中成阅读列。

- 提示词编辑器是 `prompts/PromptEditor.vue`：透明 textarea 叠在同字体的镜像层上，镜像层把变量渲染成 `<mark>` 做高亮，`@` 候选按光标位置弹出；变量的分段和状态判断是 `prompts/promptVariables.ts` 里的纯函数（有单测）。镜像层由渲染函数生成，样式要用 `:deep(mark...)` 才能命中。左栏只有一条滚动条，靠的是输入框不自己滚、高度由镜像层撑开，改字体、内边距要两层一起改。Ctrl/⌘ + Enter 试发，Ctrl/⌘ + S 保存。
- 类型、模型、码表、输出字段、测试样本和政策类的定时任务适配在 `prompts/PromptSettings.vue`，常驻在编辑器下方、不自己滚动，不要再收进折叠区：它们决定结果长什么样。输出字段标签框最多三行，再多在框里滚动。码表下拉里「上传的码表文件」在库里是空串，Element Plus 会把空串当未选，页面用哨兵值 `uploaded` 代替，不要改回空串。
- 定时任务适配的检查规则在 `prompts/taskFit.ts`，和后端 `app/aitag/domain/contract.py` 是同一套，两边改要一起改。
- 流式回答统一用 `shared/useAnswerStream.ts`（底层 `api/eventStream.ts`：带令牌和 CSRF、401 续期重试一次、错误还原成中文提示），消息列表 `AnswerTranscript.vue`，用量和费用 `StreamStatsBar.vue`，模型选择 `ModelPicker.vue`（未配密钥的模型可见但不可选）。事件处理是 `shared/streamEvents.ts` 里的纯函数，加新事件先改它和单测。
- 下载走 `shared/downloads.ts`（底层 `downloadFile`），不放在 `api/ai.ts`：契约测试会逐个调用 api 目录导出的函数。
- 模板编辑用 `useUnsavedForm`：返回列表、离开页面前提示未保存的修改；有未保存的修改时不能样本试跑、不能上线。附件上传、删除、上线、试跑状态变化只更新模板信息，不动表单草稿。
- 批量任务列表有任务在排队或运行时每 2 秒刷新，全部结束后停止轮询。详情抽屉的逐行结果不跟着每次进度刷新：只列前 50 行，这几行都有结果后再跑也不变，所以只在还有没跑到的行（只看失败时是失败数变了）时重读，至少隔 10 秒；状态变化马上重读。
- 费用账单的图表系列用 `modules/ai/billing/billing.ts` 里校验过的 8 色分类色板，颜色按名字固定，筛选不重新上色，超过 8 种的并成「其他」。
