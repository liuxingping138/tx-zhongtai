# 2026-09-24 正式 UI 采用记录

用户确认「ok 没问题 直接按照这 ui 吧」，将已确认的样板合并为正式应用界面。

## 最终实现

- 唯一导航外壳为 `frontend/src/layouts/AdminLayout.vue`：腾信睿德官网 SVG 标志、白色顶部一级模块、左侧当前模块子菜单、左下角账号菜单。
- `layouts/workspace.ts` 根据当前账号可见菜单组织导航，统一用途说明及语义图标；模块查找复用相同入口，未来模块继续受发布与权限控制。
- 已删除 `design-preview/`、旧 `AdminNavigation.vue` 和 `HomeView.vue`，没有并存的预览外壳或工作台页面。旧预览 URL 清理参数，保留其余查询/锚点；根地址通过原认证/改密守卫后进入第一个可见业务模块，没有模块时进入空权限页。
- 列表不再展示重复大标题/泛化说明，保留辅助技术所需 h1；监测页概览、详情/编辑对象名称和个人设置标题保留。
- 已确认的基础色及尺寸变量归入 `styles/theme.css` 的 `.workspace-shell`；外壳/共享列表适配由 `styles/workspace.css` 维护。登录继续使用既有独立样式。
- 一列一字段、默认全列、列设置、Excel 上传下载、数据读写及权限规则继续沿用公共组件。未更改接口、数据库或采集回填。
- `DESIGN.md`、`UX-CONTRACT.md`、`docs/guides/UI开发规范.md` 同步为正式规范。

## 验证

- 本地 `pnpm build`（包含类型检查）、`pnpm lint` 通过；增加路由测试后再次 `pnpm type-check`、`pnpm lint`、`pnpm test` 通过，12 个文件 / 66 项测试。
- 新增 7 项路由回归：仅码表菜单的默认落点、没有可用菜单、业务模块优先于系统、旧预览查询清理、强制改密、未登录跳转和无权直达拒绝。测试使用内存路由和模拟身份，浏览器使用现有管理员会话验证实际页面；未创建新权限测试账号。
- 使用 `docker compose -f deploy/compose/docker-compose.yml --env-file .env up -d --build --no-deps frontend` 重建本地前端镜像；Docker 内构建成功，frontend 容器已重建。当前 8080 提供正式新版，不需要预览参数。
- 实际 8080 浏览器检查：旧预览根地址自动进入信源、品牌原图正常加载、无预览工具、系统模块/角色列表切换、角色详情标题及顶部/侧栏高亮、账号菜单与个人设置。数据加载正常，未执行修改密码、退出、权限写入或业务数据写入。
- 正式版1024×800个人设置无页面横向溢出，品牌区/侧栏均200px；模块查找 Enter 跳转用户管理成功，最终列表加载完成（2条记录），浏览器未捕获 error 日志。
- 1280×720 下信源结果区约304px高，主区 clientHeight/scrollHeight 均644px，无多余外层滚动或页面横向溢出。品牌与侧栏宽度均216px。正式截图 `release-8080-sources.png`；先前样板四档验收截图和过程在 `preview-history.md`。
- 构建仍有已有 Element Plus chunk 大于500kB的提示，不影响构建。Premium strict 静态报告 `premium-audit.json` 唯一提示为 UserAccountMenu trigger 无显式 click：真实行为由 Element Plus Dropdown 插槽绑定，实际已确认点击展开并进入个人设置，判为静态误报。未为此重复绑定事件。
- 验证范围为本次外壳/路由/样式变更，没有将未重跑的导入导出、全部后端业务或手机测试宣称为通过。

## 文件与历史

正式规范以上述三份维护文档为准；本目录是证据与设计过程归档。`preview-history.md` 保留探索过程；原型参考、前后截图及 Logo 来源记录继续保留。本次实现按项目 Git 规范提交；提交与推送记录以仓库历史为准。
