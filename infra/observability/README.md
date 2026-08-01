# 可观测性

M1 已统一 `request_id` 和 JSON 日志格式。M2/M3 接入业务模块时补充：

- Prometheus API 延迟、错误率、数据库连接池和 Redis 指标；
- Worker 队列积压、重试和失败指标；
- Web JS 错误与桌面崩溃率；
- 不含密码、令牌、完整文件名的结构化日志字段白名单。
