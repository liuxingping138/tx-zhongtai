# 当前验收：登录页客群关系图 — 2026-09-20

范围：用户选择第1张设计后，只更新登录左侧的完整平台介绍。随后用户明确爬虫监测独立于客群，因此删除该节点的连线、增加“独立运行”。右侧表单、认证状态和业务模块均沿用原实现。

## 本次比较证据

- Source visual truth：`docs/ui-review-2026-09-20/login/selected-direction.png`，1672 × 941；比较时等比例归一为1280 × 720（原图比例存在不足1px的舍入差）。
- 实际页面：`http://127.0.0.1:8080/login`；最终部署截图 `docs/ui-review-2026-09-20/login/after-8080.jpg`，1280 × 720。桌面 CSS 视口1280 × 720，DPR 1，无整页溢出。
- 调整前：`docs/ui-review-2026-09-20/login/before.jpg`；开发版最终：`docs/ui-review-2026-09-20/login/after-desktop.jpg`。均为1280 × 720，未登录、空表单、无提示的同一状态。
- 小屏桌面：`docs/ui-review-2026-09-20/login/after-compact.jpg`，CSS/图像均1024 × 768，无整页溢出、六个节点完整可见。
- 手机：`docs/ui-review-2026-09-20/login/after-mobile.jpg`。CSS视口390 × 844，截图工具输出375 × 812的缩放图；页面宽375px（为既有常显滚动条预留15px），文档高约897px，自然纵向滚动。没有手机选稿，不进行手机像素复刻比较。
- 完整选稿和开发版截图已在同一个比较输入中展示并检查两次。全幅原尺寸下标题、图示标签、表单和页脚均可读，无需另外裁切比较区域。线上构建另核对图像已加载、`mix-blend-mode: lighten` 已生效及静态资源指纹。

## 本次问题与迭代

1. 首轮实现调整了图形尺寸和标题间距，避免原图外留白使关系图显得偏小、与正文间隔过大。
2. [P2，已修复] 第一轮同尺寸视觉比较发现插图背景形成深色矩形，破坏了选稿的连续背景。证据：`login/iteration-1.jpg`。对插图使用受限于左侧的混合与边缘遮罩，保留真实图像资源；修复后证据：`login/after-desktop.jpg`。
3. 第二轮同尺寸比较未发现待处理的P0/P1/P2问题。原有背景色与右侧表单保留，是范围要求；爬虫监测无连线属于用户明确的业务修正。最终8080容器再次重建并核对。

## 五项视觉验收

- 字体：继续使用项目中文系统字体；左侧标题两行，桌面约42px，小屏桌面约33px，手机28px；右侧字号和层级未改。
- 间距与布局：保留原有双栏比例，中心客群与两侧六节点形成主要识别点；800px及以下隐藏图示、保留包含六类能力的文字说明。
- 色彩：沿用深蓝左侧和浅色表单；插图蓝色线条与白色标签融入既有背景。品牌图形沿用原实现，不改变全局色板。
- 图像：使用单独生成的1774 × 887 WebP（约76KiB），保留节点文字与图标，没有以截图替代整页。标题、介绍和表单均为真实HTML；图片预留比例，中文alt完整说明关联与独立模块。
- 文案：客户、招投标、政策、场景、码表管理均可识别，爬虫监测明确“独立运行”；不宣称未来模块已发布、不添加可点击的无功能入口。

## 本次验证与边界

- `pnpm run type-check`、`pnpm run lint`、`pnpm run test`（5文件/19测试）、`pnpm run build`通过；最后的背景融合样式修改后再次通过Lint和Docker内的类型检查/生产构建。
- 官方 `npx -p @google/design.md designmd lint DESIGN.md` 通过，0错误、5个既有token引用警告。
- Premium全项目strict audit原始结果保存在 `docs/ui-review-2026-09-20/login/premium-audit.json`：退出码1，唯一项为既有 `UserAccountMenu.vue:50` 的 `affordance.actionless-button`。该按钮由父级Element Plus Dropdown的click trigger驱动；已在8080实际打开菜单并看到“个人设置/退出登录”，确认是静态分析误报。没有为了消除误报加入空click处理器，也不声称原始strict命令通过。
- 浏览器检查：空提交显示两个字段错误并聚焦用户名；密码显示/隐藏支持点击和空格键；虚构账号登录显示“用户名或密码错误”、保留输入并恢复可操作；无真实账号凭据被更改。测试后重新加载恢复空表单。
- 8080小屏桌面控制台检查无error/warn。本次不修改认证逻辑，未重跑真实凭据登录成功、首次改密及限速/断网矩阵；没有为左侧静态介绍添加镜像实现的测试。
- 已重建本地Docker frontend，最终图片地址 `/assets/customer-hub-BDewtZ-g.webp`，桌面渲染和页面尺寸已核对。localhost原有登录会话保留，使用同一8080服务的127.0.0.1入口展示未登录预览。

实现检查：左侧结构与语义完成；桌面/手机已检查；认证表单代码保留；三份规范同步；实际8080构建已更新。无待处理P0/P1/P2设计问题。

final result: passed

---

# 历史验收：业务工作台 — 2026-09-20

Source visual truth: `docs/ui-review-2026-09-20/concept-revised-toolbar.png`.
Implementation: `http://127.0.0.1:5173/policy/base-tags`.
Final screenshot: `docs/ui-review-2026-09-20/after-policy-final.jpg`.

## Comparison evidence

Source PNG: 1487 × 1058. Final browser JPEG: 1487 × 1058. CSS viewport: 1487 × 1058, 1 image pixel per CSS pixel. No density rescaling used. Both are light theme, expanded policy navigation, unfiltered first page. Source contains illustrative simplified record values; implementation uses the real 1,870 records. Compare layout and workflow hierarchy, not illustrative field values. Source and implementation were emitted together in the same comparison input.

Mobile before/after were also emitted together: `07-mobile.png` and `after-mobile-final.jpg`, both 390 × 844. The former has a historical .png suffix but contains JPEG bytes. Final mobile DOM measurement: body scrollWidth 390, innerWidth 390.

Full-view images were readable at source size, including action labels, first record, table heading and pager. A separate focused crop was unnecessary for this non-pixel-clone layout refactor; these regions were inspected in the same full-resolution comparison. No new photographic/illustrative asset is part of the implementation.

## Findings and accepted adaptations

No actionable P0/P1/P2 visual difference remains in the reviewed sample.

- Typography: shared Chinese system font stack, 24px heading, 14px data and 12–13px secondary labels. Real long titles have two-line access, with full text in the details drawer. Mock typography is a visual reference, not an identifiable licensed font to copy.
- Spacing/layout: compact heading → one-row primary filters → count/actions → results → pager preserves the approved hierarchy. Runtime sidebar retains the existing 220px geometry, rather than copying the generated mock's wider sidebar. Primary data area is consequently wider. Mobile hides secondary filters until expanded; first result begins about y445 versus y707 before.
- Colors/tokens: navy navigation, white results, light blue-gray canvas and one blue action color map to theme.css. Borders and restrained surfaces preserve the selected direction. Boolean values remain text 是/否, with neutral treatment rather than invented process status.
- Image/assets: existing project brand mark retained; maintained Element Plus icons used for ordinary UI actions. No image-as-page or custom replacement illustration introduced.
- Copy/content: uploads AND downloads remain visible. Real region names, policy classifications and timestamps retained rather than replaced with the mock's examples. Full field names retain the business meaning. Existing menu order follows published configuration. No mock sequence number was introduced as a business identifier.
- P3: a future dedicated phone session can refine long metadata labels; currently they wrap without losing data or hiding controls.

## Comparison history

1. Initial implementation inspection showed long desktop results pushing pagination beyond the useful workspace. Fixed BusinessTable desktop height with internal scrolling and kept pagination outside the table. Loading/error result regions have a reserved minimum height. Post-fix evidence: `after-policy-final.jpg`.
2. During responsive implementation, separate hidden desktop/mobile trees risked duplicated empty-state controls. Replaced CSS-only duplication with a media-query conditional render. Post-fix evidence: `after-mobile-final.jpg`; phone presents one summary list, no whole-page horizontal overflow.
3. Final same-size source/implementation comparison found no additional actionable P0/P1/P2 visual changes. Mobile capture taken again after viewport rendering settled; intermediate capture discarded from the final evidence.

## Interactions and boundaries

Verified in the built-in browser: business page navigation, opening create form, required-error text and first-invalid focus, cancel with no changes, primary search and no-result state, URL query retention across navigation/back, reset, adding/restoring a displayed column, full mobile detail, and successful export response/“下载已开始” feedback. Console error/warning log check returned no entries during the reviewed interactions.

The browser download event watcher did not return a file event; HTTP export and success feedback were verified, filesystem delivery was not independently verified. No real records were created, edited, purged, or imported for this check. Mocked Playwright mutation/error-path suite remains pending the explicit CLI permission required by the Product Design skill. Official DESIGN.md lint was attempted twice but blocked by npm registry DNS/timeout. These remain validation gaps, not a claim of completed end-to-end release certification.

## Checklist

- [x] Match reviewed composition and preserve upload/download.
- [x] Check real long content, full-value access, phone layout and field errors.
- [x] Static type/lint/unit/build and Premium strict audit.
- [ ] Run mocked browser mutation/failure-path regression suite after permission.
- [ ] Re-run official designmd lint when npm registry is reachable.

final result: passed

## 用户反馈后的列设置迭代

最新列宽与长表头验收见[逐页复查](docs/ui-review-2026-09-20/column-widths/REVIEW.md)。六个业务列表均检查默认/全部，另检查三个系统列表；移除主字段320px特例、固定短字段、稳定字段顺序、精简长表头。该版在宽屏上的视觉效果被用户否定，已由默认全字段方案替代；当前记录见[全宽修订](docs/ui-review-2026-09-20/full-width/REVIEW.md)。

[P2] 原先仅齿轮图标的列设置入口不易发现，缺少一键恢复全字段展示。用户反馈后改为“列设置 已选/全部”文字按钮，增加“显示全部列”和“恢复默认列”，并保存本浏览器偏好。证据：`docs/ui-review-2026-09-20/after-column-settings.jpg`；已核对行业场景35/35个数据列、36个表头（包括操作）。本次变化是用户明确要求的样板修订，优先于原图的图标按钮。

用户进一步明确所有列表必须一列一个字段，已删除共享表格的辅助字段混排能力。最终第一列证据：`docs/ui-review-2026-09-20/after-policy-single-field.jpg`。此要求覆盖早期样板中的标题/部门双行设计。

## 最终入口与文档同步

2026-09-20 已重建Docker frontend并从用户实际使用的 `http://localhost:8080/codebook/scenarios` 验证最新运行状态。证据：`docs/ui-review-2026-09-20/deployed-8080-final.jpg`。文字列设置4/35、显示全部列、恢复默认列已可见；首格为单独的“IDC”，不含编码副文本。上文早期图是比较历史，后续实现必须遵循 DESIGN.md / UX-CONTRACT.md / docs/UI开发规范.md 的最终规则。


## 默认全字段修订（现行）

用户明确确认默认全部字段、个人通过列设置隐藏。旧核心列默认及表格总宽上限已撤回。六个业务列表和三个系统列表已复查，重点补充2560px宽屏与1280px桌面；44px业务行、单行长文本、完整详情与390px手机摘要均有实测。[当前截图和验证记录](docs/ui-review-2026-09-20/full-width/REVIEW.md)。

同日续订：账号在侧栏底部（显示名 + `/me.roles`），登录页不改；桌面筛选一次展开、点查询生效；结果区 `ScrollPort` 常显横/纵滑槽，默认 20 条必须能上下滚完全页。现行条文以 DESIGN.md / UX-CONTRACT.md / docs/UI开发规范.md 为准。
