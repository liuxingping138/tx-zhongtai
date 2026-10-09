# 2026-10-09 审查修复与发布验收

结论：本轮审查与复核发现的修复已发布。入口为 **https://1.119.196.77**；旧 HTTP 8091 返回 308 并转向 HTTPS 443。所有操作保持其他项目端口/服务不变，没有提交或推送 Git。

## 修复及验证

| 项目 | 本次结果 |
| --- | --- |
| F01 刷新令牌重放 | 撤销及安全审计在拒绝响应前提交。SQLite 跨事务回归通过；真实 P6 验证新 refresh 和旧 access 均失效，重放审计持久化。 |
| F02 / R01–R03 上传与 Excel | 权限依赖先于 multipart；流式总字节限制；所有异常/取消/多文件/缺字段路径关闭临时文件。普通导入及地区解析共用 ZIP 解压、实际 XML 行列坐标和并发预算，拒绝虚假 dimension、稀疏行及超宽数据。单测及真实隔离网关检查通过。 |
| F03 PATCH | 六表独立 Patch 模型、exclude_unset、必填和版本校验。真实 HTTP 创建→部分更新→重新查询→过期版本拒绝→显式清空均通过。政策类型使用实际列表接口读取保存结果。 |
| F04 / D06 / R04 HTTPS | 采用未占用的 443；固定公网端口和跳转目标。为无 SNI 的 IP 请求配置默认受信证书，避免回落到 Traefik 自签证书。production、Secure Cookie、CSRF 来源和随机内部凭据均生效；保留原 JWT、数据库和爬虫连接凭据。 |
| F05 镜像 | 四服务 uv.lock + frozen 构建成功，导出依赖清单；四个镜像的公共包 24 个 Python 文件均与构建目录哈希一致。API/worker 共用同一镜像 ID。敏感文件已从构建上下文排除。 |
| F06 配置 | 生产环境容器内白名单实查生效。网关与服务上传限额的联动要求已写入手册。 |
| F07 / F08 门禁 | 迁移失败退出码回归、中文路径扫描均通过；扫描增加未忽略的未跟踪文件，避免本轮新增文件被漏扫。 |
| F09 P6 | 真实整套验收通过；修复“政策资源仍未发布”的过期断言，改为实际未发布客户资源；P6 使用独立 JWT，补齐 worker 隔离配置。 |
| F10 / R05 恢复 | 本次业务四库备份校验通过，恢复到 P6 四库成功。四个应用账号分别完成临时 Alembic 升级、回退和 check，验证实际恢复后的 owner 与迁移能力。 |
| D01–D05 / D08 文档 | 当前入口、开发/部署流程、权限/租约/范围说明、OpenAPI 已同步；四份 OpenAPI 与应用一致，保留历史报告原貌。 |

## 测试结果

- `make test-unit`：后端 321 passed，前端 68 passed，合计 **389 passed、11 skipped**。
- 其中 9 项数据库调度测试已另行启用，在独立 `scheduler_test` 全部通过。修复超时测试将远端数据库提交硬塞进 50ms 的时序假设，先持久化待清理批次再验证超时处理。
- 另 2 项码表 skip 为不适用筛选映射/未入库 Excel fixture，未计为通过。
- `make check`：ruff、mypy、前端类型/构建/lint、范围和密钥扫描、迁移门禁回归及 OpenAPI 对比通过。
- Playwright：**44 passed**。原有爬虫测试依赖真实历史数据，新增 `tests/p6/seed_crawler.py` 为隔离库提供固定快照；`make test-e2e` 会先建立该 fixture，不读取真实 MySQL、不放宽断言。
- P6 认证/权限/重放/故障恢复验收通过，见 `p6-output.txt`。
- 六表真实 PATCH 验证通过：`tests/p6/business_patch.py`。
- 地区解析超宽拒绝、未认证上传拒绝、无 Content-Length 超限上传拒绝通过：`upload-output.txt`。
- 四库真实恢复及后续迁移验证通过：`restore-output.txt`。
- 证书签发、严格链校验、IP SAN、重定向、续期 dry-run 通过。证书本次有效至 2026-10-16 01:22:31（北京时间），由 systemd 定时检查续期；见 `renewal-output.txt`。

## 发布后状态

- 11 个容器 running，7 个带健康检查的容器 healthy。
- HTTPS 首页 200，`/api/v1/auth/csrf` 200 且 Cookie 含 Secure；未认证业务列表 401。
- 四服务环境为 production；IAM `cookie_secure=true`、access TTL 28800 秒；政策和码表 `import_max_bytes=20971520`、`export_max_rows=100000`。
- 四库 `alembic upgrade head` / `alembic check` 通过，无新增 schema 迁移。
- `tx-zhongtai-cert-renew.timer` active；续期 service 本次执行成功，每日两次检查。公网访问只做无业务写入的检查，真实登录/刷新/保存场景在隔离栈验收。
- 镜像 ID 见 `images.json`；依赖清单见 `requirements-*.txt`；源代码保留在当前未提交工作区。

## 一次备份与回滚

按用户最后确认，**只做一次服务器备份，不安装每日备份、自动清理任务或异机备份**。手册中的长期策略为可选说明，不代表已启用。

- 业务备份：`/home/txkj/tx-zhongtai-backups/20261009T022257Z`（四库 dump、dbname、SHA256SUMS、COMPLETE）。
- 发布前源码、私有配置及镜像映射：`/home/txkj/tx-zhongtai-releases/pre-20261009`，受保护目录。
- 回滚命令：`sudo bash /home/txkj/tx-zhongtai-releases/pre-20261009/rollback.sh`。恢复旧代码/配置/镜像及 HTTP 入口，不恢复数据库、不覆盖发布后的业务数据。
- P6 容器、隔离数据卷、恢复副本与测试密钥在验收结束后清理；保留原业务备份。

构建仍有 Element Plus 分块体积告警，以及现有依赖弃用提示；检查与测试未因此失败。本记录不表示做过渗透、压力或在线漏洞库全量扫描。

## 用户确认后的备份清理（2026-10-09）

用户确认当前版本可用，并要求不再保留旧版本备份。已删除本次旧四库备份 `20261009T022257Z`、`pre-20261009` 回滚目录及 8 个专用回滚镜像标签。上文备份/回滚位置为发布时的历史记录，**现已不存在，原回滚命令不可再使用**。当前 11 个运行容器及其镜像 ID 保持不变，业务数据卷未改动。

清理时整台服务器共 44 个容器（38 运行、6 停止），本项目 11 个全部运行。宿主机端口为 HTTPS 443、HTTP 跳转 8091、PostgreSQL 5433；本次新增的是 443，其余两项原已存在。
