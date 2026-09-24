# UI 开发与复用指南

现行版本：2026-09-24。适用于已发布模块及未来客户、招投标、爬虫等模块。以用户最终确认、业务字段定义、[DESIGN.md](../../DESIGN.md)、[UX-CONTRACT.md](../../UX-CONTRACT.md) 为依据。审查目录里的图片记录设计过程，不替代现行规范。

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

## 导航接入（2026-09-24）

顶部只展示当前账号可见的一级模块，左侧只展示当前模块的子菜单。根地址进入首个可见业务模块，无菜单沿用空权限页，不提供工作台。新增页面需登记路由及 `router/menu.ts`，并在 `layouts/workspace.ts` 配置用途说明和独立语义图标；统一 Element Plus Icons、17px、继承菜单颜色，禁止按父模块复用同一个图标。详情页用 `meta.menuPath` 关联所属列表。标志使用 `assets/brand/telelands-logo.svg`，不重绘或改变比例。

顶栏76px，品牌/侧栏共用216px（1100px及以下200px）。账号固定左下角。基础色与宽高 token 由 theme.css 管理；外壳/列表适配由 workspace.css 管理，不新增页面专属基础色板。不存在设计预览分支；旧预览 URL 会清理参数并进入正式界面。

## 2. 公共组件所有权

路径均相对仓库根目录。

| 能力 | 复用位置 | 页面负责 |
|---|---|---|
| 页面结构、总数、分页、加载失败 | `frontend/src/components/ListPage.vue` | title/hint、total/page/pageSize/loading/error，retry/change处理；结果区必须用 ScrollPort；概览区走 `summary` 插槽（筛选之前，不参与拉伸） |
| 结果区滚动 | `frontend/src/components/ScrollPort.vue` | 常显横/纵滑槽；两指分轴；默认每页 20 条时未露出的行必须能上下滚到 |
| 查询 | `frontend/src/components/FilterBar.vue`、`FilterSelect.vue` | query 与 applied；桌面展开全部字段，advanced 只作字段分组不再桌面折叠。`FilterSelect` 一律多选，query 里筛选字段默认值是 `[]`（不是 `''`），重置也赋 `[]`；状态卡片这类「点一下筛选、再点取消」的入口用 `toggleValue` |
| 业务表格/详情/手机摘要 | `frontend/src/components/BusinessTable.vue` | items、完整columns、selected、titleKey、可选summaryKeys、canWrite/loading/filtered，edit/reset |
| 账号菜单 | `frontend/src/layouts/UserAccountMenu.vue` | 侧栏底部；显示名 + `/me.roles` |
| 浮层焦点 | `frontend/src/layouts/AdminLayout.vue` | 打开时把焦点送进浮层、关闭后送回触发按钮；落回 body 会让键盘用户从头 Tab |
| 显示列与浏览器记忆 | `frontend/src/components/ColumnPicker.vue` | 与表格共享 selected；完整columns与defaults |
| 字段列类型 | `frontend/src/components/dataColumns.ts` | prop与API字段对应；label简明、fullLabel保留原名；可选width/minWidth/grow/wrap/time/link |
| 列顺序与宽度计算 | `frontend/src/components/dataColumnLayout.ts` | layoutDataColumns固定短字段、让长字段吸收余量；不按首列特殊处理 |
| 分组业务表单 | `frontend/src/components/GroupedFields.vue` | 完整字段groups、表单model、submitError，保存前validate |
| 系统字段验证 | `frontend/src/composables/useFieldValidation.ts` | 字段错误、提交验证，不覆盖业务规则 |
| 未保存保护 | `frontend/src/composables/useUnsavedForm.ts` | visible、表单快照、saving；接close/beforeClose |
| Excel 下载 | `frontend/src/api/download.ts` | `downloadFile(路径, 中文文件名, filtersForExport(listQuery.applied))`；导出按已生效筛选走，传 applied 不传 query；不要用裸 fetch，否则绕开 401 自动续期和统一中文错误提示 |
| 权限展示 | `frontend/src/permissions/catalog.ts` | 模块分组、每个模块可选档位（有导出动作才有「导出」列，有写操作才有「管理」列）、「管理」包含的操作说明都从资源树推导，不在页面里手写模块清单；新增模块只需在 iam 目录登记动作并给导出动作标 `EXPORT` |
| 导出按钮 | 各列表页 | 用 `auth.canExport(资源)` 判断；没有导出权限时按钮保留但禁用，悬停说明原因（工具栏入口必须保留） |
| 详情子页 | `router/routes.ts` 的 `meta.menuPath` | 不在菜单里的详情页填所属列表路径，面包屑与侧栏高亮自动挂到列表下 |
| 筛选项候选值 | `frontend/src/composables/useFilterOptions.ts` | `v-bind="filters.bind('字段')"`；候选少的字段整份预发、本地过滤，候选多的自动转服务端搜索。不要再自己 reactive 一份 options |
| URL查询恢复 | `frontend/src/composables/useListQuery.ts` | query、load、私有字段列表 |
| 上传状态与结果 | `frontend/src/components/ExcelImportProgress.vue`、`ExcelImportResult.vue` | 原模块导入接口及结果，不复制业务去重逻辑 |
| 导航/基础色/字体/间距 | `frontend/src/layouts/AdminLayout.vue`、`layouts/workspace.ts`、`frontend/src/styles/theme.css`、`styles/workspace.css` | 路由、发布配置、资源权限；账号放侧栏底部，不复制导航或另建色板 |
| 登录品牌区/认证 | `frontend/src/views/LoginView.vue`、`frontend/src/assets/login/customer-hub.webp` | 左侧客群关系图；爬虫监测独立无连线；800px及以下隐藏图并保留简介；右侧沿用认证表单 |

系统用户、角色、审计等专门二维表目前复用 ListPage，但不强行迁移为业务记录表；原有专门操作和权限语义必须保留。

## 3. 当前默认列清单

默认即完整字段集合，`defaultColumns = columns.map(col => col.prop)`；操作列另计。用户可以隐藏不需要的列，刷新保留个人选择，显示全部/恢复默认均回到全字段。新增模块沿用该规则。

| 路由 | 默认/全部数据列数量 |
|---|---|
| `/policy/sources` | 16/16 |
| `/policy/base-tags` | 20/20 |
| `/policy/interpretations` | 26/26 |
| `/codebook/policy-types` | 7/7 |
| `/codebook/scenarios` | 35/35 |
| `/codebook/area-codes` | 15/15 |

ColumnPicker 按用户ID和route.path保存字段键，使用v2存储键；旧v1系统核心列默认自动迁移为全部，真实自定义选择保留。新模块无须传 legacyDefaults；现有六页保留该参数仅用于旧偏好迁移。

手机仍为摘要：titleKey主字段，加summaryKeys中最多3个已选其他字段；完整字段在详情读取。桌面全字段不意味着手机逐卡铺开35个字段。

## 4. 接入步骤

1. 核对 API、中文字段定义、编辑字段、权限及导入导出规则。新增字段时同步完整 columns、编辑groups和后端契约。
2. 选择最接近的业务列表作为参照，如 `frontend/src/modules/codebook/policy-types/PolicyTypeList.vue`；复用公共组件，不复制其组件内部布局。
3. 按业务字段顺序定义完整 `DataColumn[]`，用全部字段键生成 `defaultColumns`，并初始化 `selectedColumns`。ColumnPicker 与 BusinessTable 必须引用同一个完整字段集合；表格根据此顺序过滤已选字段。
4. 接入 ListPage 的 filters/actions/tools 插槽；查询重置page=1，分页更新查询；请求序列保护过期响应，错误保留在原页可重试。
5. 接入表单错误、未保存保护、busy防重复、成功返回列表；服务端冲突保留草稿，不自动覆盖。
6. 新菜单依现有路由/发布/权限体系接入顶部一级模块和左侧子菜单，不能只添加一个不受权限约束的链接。
7. 按第6节验收，并确认用户访问的实际服务已更新。

下面展示列设置与表格之间的真实接口。变量由页面依据上述步骤定义；不是脱离API即可运行的完整业务页：

```vue
<template #tools>
  <ColumnPicker
    v-model="selectedColumns"
    :columns="columns"
    :defaults="defaultColumns"
  />
</template>
<!-- 放在 ListPage 默认插槽内 -->
<BusinessTable
  :items="items"
  :columns="columns"
  :selected="selectedColumns"
  title-key="type_name"
  :can-write="canWrite"
  :loading="loading"
  :filtered="resultFiltered"
  @edit="openEdit"
  @reset="onResetFilters"
/>
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

## 5. 本地开发和更新页面

| 入口 | 页面来源 | 源码修改后 |
|---|---|---|
| `http://127.0.0.1:5173` | Vite开发服务，API代理到网关 | 正常自动热更新；未运行时在frontend目录执行 `pnpm dev --host 127.0.0.1` |
| `http://localhost:8080` | Docker frontend里的构建产物，经网关访问 | 必须重建frontend镜像并替换容器；单纯刷新或restart旧容器不会更新源码 |

在仓库根目录更新8080前端：

```sh
docker compose -f deploy/compose/docker-compose.yml --env-file .env up -d --build --no-deps frontend
```

只修改前端时使用上述单服务命令，不必重建数据库和全部后端。仅执行本机 `pnpm build` 不会把 dist 自动放入 Docker。不要把开发环境更新变成启动P6隔离栈。更新后验证8080的页面和静态资源，不把5173验证结果当成8080已更新。

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
- 修改视觉值同步DESIGN.md；修改行为同步UX-CONTRACT.md；改组件API、默认列或服务入口同步本文件。在开发进度记录结果，不把历史截图和未跑测试描述成当前验收。

当前实现与历史验证结果见 [实施记录](../archive/ui-review-2026-09-20/IMPLEMENTATION.md)。Playwright CLI授权、官方designmd lint网络可用性等本轮遗留验证项保留在该记录中，不能用“规范已写好”替代验证完成。

## 带概览的监测列表

遵循 2026-09-22 用户确认：上方卡片保持正常尺寸，不能靠压缩卡片适应一屏。`ListPage` 检测 `summary` 插槽后解除一屏上限，结果高度采用 `clamp(440px, calc(100dvh - 220px), 880px)`；页面自然纵向滚动，表格保留 `ScrollPort` 双向滚动。1440×900 下结果区应为 680px，1024×768 下为 548px；收起概览后可集中看列表。验收时滚动到结果区核对第一行可点击、分页可达、横向拖动后操作列不遮盖字段。

指标名称必须与统计口径一致。状态分布按名称、数量、比例对齐，有已选反馈；图表使用实际容器宽度，禁止固定宽 viewBox 把文字压小。同步时间放在概览标题区，失败或过期提示独立展示。
