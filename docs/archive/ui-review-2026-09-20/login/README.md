# 登录左侧：客群关系图

2026-09-20用户选择第1张设计，并明确爬虫监测独立于客群。完整产品范围为客户、招投标、政策、场景、爬虫监测和码表管理；已发布模块和权限保持原规则。

- `selected-direction.png`：用户选择的完整设计参考。爬虫监测连线由后续用户修正覆盖。
- `before.jpg`：本次调整前的登录页。
- `iteration-1.jpg`：背景融合修复前的桌面画面。
- `after-desktop.jpg`：最终开发版1280 × 720画面。
- `after-8080.jpg`：最终Docker 8080部署的1280 × 720画面。
- `after-compact.jpg`：1024 × 768小屏桌面。
- `after-mobile.jpg`：390 × 844手机视口（浏览器输出图像375 × 812）。
- `invalid-credentials-mobile.jpg`：虚构账号的登录失败状态。
- `premium-audit.json`：全项目静态审查原始结果；既有Dropdown触发按钮的误报已手动验证，详见[本次QA](../../design-qa.md)。

运行时资源是 `frontend/src/assets/login/customer-hub.webp`，由选稿生成独立图示后转为WebP。节点及文字属于插图，未来变更节点关系时同时更新图片、alt及平台简介。不要把图中的节点改成不受权限控制的路由。

复用依据：[设计规范](../../../../DESIGN.md)、[交互契约](../../../../UX-CONTRACT.md)、[UI开发指南](../../../UI开发规范.md)。
