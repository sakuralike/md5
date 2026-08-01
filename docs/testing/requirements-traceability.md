# 需求—模块—测试追踪矩阵

| 需求 | 模块 | 当前阶段测试 | 状态 |
|---|---|---|---|
| AUTH-01 | `modules/auth` | 注册成功、用户名/邮箱冲突、弱输入拒绝 | M1 已纳入 |
| AUTH-02 | `modules/auth` | 登录、刷新轮换、数据库仅存刷新摘要 | M1 已纳入 |
| AUTH-03 | `modules/auth` | 当前会话退出、全部会话退出、会话列表与撤销 | M1 部分完成 |
| AUTH-04 | `modules/admin` | 管理员 TOTP 与高风险二次验证 | M4 待实现 |
| AUTH-05 | `core/rate_limit` | 失败计数、渐进延迟、临时锁定 | M1 骨架，规则待完善 |
| AUTH-06 | `core/security` | Argon2id 哈希与错误密码拒绝 | M1 已纳入 |
| HASH-01～04 | Web 哈希 Worker | SHA-256/MD5 分块、取消、进度、格式校验 | M2 待实现 |
| SEARCH-01～06 | `modules/archives` | 精确匹配、匿名视图、揭示配额和审计 | M2 待实现 |
| SUB-01～06 | `modules/submissions` | 幂等、重复合并、授权版本、待结算积分 | M2 待实现 |
| VERIFY-01～07 | `modules/verification` | 独立证据、重放、隔离和状态时间线 | M3/M4 待实现 |
| 管理端需求 | `modules/admin` | RBAC、审核处置、审计查询 | M1 骨架/M4 完成 |

测试用例实现后，在对应行补充测试文件路径和验收证据链接。
