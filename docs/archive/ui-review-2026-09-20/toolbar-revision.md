# 工具栏样板修订

> 历史方案归档，不能作为后续实现标准。当前规范见 [DESIGN.md](../../../DESIGN.md)、[UX-CONTRACT.md](../../../UX-CONTRACT.md) 和 [复用指南](../../UI开发规范.md)。标题下混排部门/编码与仅齿轮列设置均已被用户否定；以后必须一列一字段，提供文字列设置和显示全部列。

状态：视觉效果待用户确认，未改动业务页面。

根据用户反馈压缩标题区与筛选区，将新增、上传 Excel、下载 Excel、操作记录移到表格上方，和记录总数同一行，全部直接可见。保留蓝色侧栏作为本次布局展示基底，不视为用户已经选定整体导航方向。

修订图：concept-revised-toolbar.png。采用内置 ImageGen 编辑，参考图 concept-1.png。示例内容仅用于排版，实施使用现有真实字段与数据。

完整生成提示词：

```text
Edit the attached Chinese enterprise application UI mockup. Produce ONE revised screen, not multiple variants. Keep the left navy sidebar, brand "业务数据运营平台", overall quiet blue visual identity, table data hierarchy and app shell. Target desktop 1440x1024, current date 2026-09-20. This is a design mock with sample data.
User specifically requests reducing space wasted by top Excel action row. MANDATORY changes:
1. Remove ALL actions from beside the page title. Title "政策基础标签表" and one short subtitle only, a compact 70px area below the 56px topbar, no huge whitespace or boxed title card.
2. Compact filters into ONE horizontal row: labels ABOVE controls, 政策名称 keyword field 290px, 省份 150px, 政策类型 175px, 更多筛选 100px (boolean conditions hidden here), 查询 64px and 重置 text button aligned with input baseline. Entire filter area no more than 94px tall. No second button row. Preserve generous horizontal readability, 14px text.
3. Immediately above table header put ONE 52px table toolbar: LEFT "共 1,870 条记录"; RIGHT compact buttons "＋ 新增", upload icon + "上传 Excel", download icon + "下载 Excel", history icon + "操作记录", and small column-settings icon. All four text-labelled actions must be directly visible in this toolbar. Do NOT use 导入 Excel wording. Do NOT hide upload or download in 更多. 新增 only filled primary #2c68bb, upload/download/history quiet white or ghost buttons with dark clear text and light borders. Height 32px, compact padding, 8px gaps. NO separate tall action panel.
4. Begin table at approximately y=300 so data dominates. One white contiguous workspace, no cards within cards, minimal shadows and horizontal separators. Columns: 政策名称 with department secondary line, 地区, 政策类型, 出台时间, 是否解读, 操作. Policy title wide enough to read; 10–11 rows. Preserve key source titles and record dates (do not introduce new business fields). 地区 examples use 全国 for national policies. Boolean "是否解读" values are 是/否, never 待处理 or 已完成. Row action 查看 / 编辑. No selectable checkbox or invented bulk features.
5. Footer single pagination row with 20条/页 and page1 of94. A quiet "设计样板 · 示例数据" note.
Palette #203955 navy, #2c68bb blue, #20324c ink, #697386 secondary, #f3f6fa background, #e3e9f1 lines. PingFang SC-like text 14px body and 22px semibold title. Icon family coherent thin outline. 6px control radius. No browser chrome, no device frame, no charts or KPI cards, no extra unused actions. Current sidebar workbench, policy and its source/base tag/interpretation children, codebook and system only; unpublished customer/tender stay hidden. Make the new compact action placement visually unmistakable. Keep everything crisp, professional, legible and aligned.
```



用户已确认采用本版标准，进入实现阶段；运行时规范见项目根目录 DESIGN.md 与 UX-CONTRACT.md。
