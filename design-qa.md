# Design QA — 2026-09-20

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

用户明确确认默认全部字段、个人通过列设置隐藏。旧核心列默认及表格总宽上限已撤回。六个业务列表和三个系统列表已复查，重点补充2560px宽屏与1280px桌面；44px业务行、单行长文本、完整详情与390px手机摘要均有实测。[当前截图和验证记录](docs/ui-review-2026-09-20/full-width/REVIEW.md)。技术核验完成不等于用户已经接受视觉效果。
