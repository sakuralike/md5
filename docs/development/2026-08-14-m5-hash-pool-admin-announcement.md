# 2026-08-14 M5 总哈希池、用户审批与公告体验开发记录

## 本轮目标

修复桌面端公告读取契约，补齐总哈希池管理视图、用户审批手动创建用户和等级权益归属，并在 Web 端增加右下角公告弹窗。

## 已完成

- API 新增 `GET /api/v1/admin/hash-pool`，以 `verified` 候选为唯一数据源，提供算法筛选、指纹/候选/归档查询、分页和池概览；响应不包含候选密码。
- Admin 新增“总哈希池”导航与页面；用户审批页新增手动创建普通用户、可信贡献者和审核员的表单，并记录 `admin.user.created` 审计；“用户等级与权益”移入用户审批页。
- Web 新增公告服务与 `AnnouncementPopup`，右下角显示已发布公告，支持图片、HTTP(S) 操作链接、关闭持久化和修订后重新出现；HTML 正文按纯文本展示，避免脚本注入。
- Windows 客户端公告请求加入 `no-cache/no-store` 和刷新参数；根域名自动补全 `/api/v1/`，默认地址改为当前可访问的 Web/API 代理，从而修复公告区显示“暂无公告”的主要配置问题。

## 验证证据

- API：`apps/api/tests/test_m5_hash_pool.py`、`apps/api/tests/test_n2_admin_users.py` 定向测试通过；Ruff 定向检查通过。
- Admin：lint、typecheck、36 个测试文件/80 个测试通过。
- Web：lint、typecheck、32 个测试文件/54 个测试通过。
- Windows：`dotnet test apps/desktop-windows.tests/PasswordDetective.Desktop.Tests.csproj --no-restore`，29 个测试通过。

## 当前剩余工作审计

本轮只完成代码切片，不能据此宣布生产完成。后续优先级如下：

1. 运行统一门禁并修复跨应用回归；完成真实浏览器公告弹窗、Admin 总哈希池和用户审批旅程。
2. 重新打包桌面端 Release，验证无 `windir`、Windows 10/11、公告点击刷新、图片点击外链以及 ZIP/7z/RAR/TAR/GZ/TGZ/BZ/BZ2。
3. 完成真实 MySQL/Redis HA、邮件摘要真实投递、Redis Pub/Sub 多实例、SSE 长连接容量和恢复演练。
4. 使用同一提交完成远端推送、Staging 迁移/服务重启、Web/Admin/API 公网冒烟和回滚证据；Staging 通过不等同于生产放行。
