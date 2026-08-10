# WP4 第 9 次开发迭代：Alertmanager 通知闭环与安全演练

- 日期：2026-08-10
- 工作包：WP4 / M5 安全、恢复、性能与可观测性准入
- 本轮目标：在既有 Prometheus 告警规则基础上补齐 Alertmanager 路由、合成通知接收网关、重复告警抑制、恢复通知和敏感字段持久化脱敏。

## 1. 本轮交付

### 1.1 Alertmanager 路由

- 新增 `infra/monitoring/alertmanager/alertmanager.yml`。
- Prometheus 通过 `alertmanager:9093` 转发告警。
- 路由只按 `alertname`、`service`、`severity`、`environment` 四个低基数字段分组。
- `group_wait=2s`、`group_interval=5s`、`repeat_interval=4h`，相同告警在重复周期内不重复通知。
- Webhook 启用 `send_resolved`，恢复状态必须进入同一通知闭环。

### 1.2 合成通知网关

新增 `scripts/alertmanager_receiver.py`，仅用于本地和 CI 合成演练：

- 提供 `/health`、`/alerts`、`/events` 三个接口；
- 只保存 Alertmanager 通知中的必要字段，不保存 HTTP 请求头或原始请求正文；
- 对密码、秘密、令牌、邮箱、指纹、请求号和用户标识等字段统一写入 `[REDACTED]`；
- 每次通知生成独立 `delivery_id`，便于核对 firing 与 resolved 两次交付；
- 最大请求正文限制为 1 MiB，异常请求不进入证据集合。

该网关不属于生产通知提供商，不替代正式邮件、Webhook、PagerDuty 或值班平台。

### 1.3 告警通知演练

新增 `scripts/alertmanager-drill.ps1`：

1. 使用隔离 Compose 项目和非默认端口启动 Alertmanager 与合成通知网关；
2. 连续提交两次标签完全相同的 firing 告警；
3. 验证只产生一次 firing 通知；
4. 提交相同告警的结束时间，验证产生一次 resolved 通知；
5. 验证合成敏感标记未出现在持久化证据中，并存在 `[REDACTED]`；
6. 输出机器可读报告，完成后清理容器、网络和卷。

`scripts/verify_alertmanager_evidence.py` 对 firing、去重、resolved、脱敏和 delivery ID 进行独立校验并生成 SHA-256。

## 2. 自动化门禁

- `verify_monitoring_config.py` 升级为 `monitoring-config-v2`，增加 Alertmanager 路由、低基数分组、resolved 通知、内部接收器和通知网关源码检查。
- `promtool check config` 继续校验 Prometheus 与 7 条告警规则。
- 官方 `amtool check-config` 校验 Alertmanager 配置。
- 新增通知网关脱敏和 Alertmanager 配置测试。
- `scripts/check.ps1 -SkipInstall -IncludeMonitoring` 依次执行配置检查、Alertmanager 演练、证据检查和 Worker 积压演练。
- GitHub Actions `monitoring` 作业上传监控配置、Alertmanager 演练和 Worker 积压三组证据。
- 首次远端演练发现 Alpine BusyBox `wget` 对 `localhost` 优先使用 IPv6，而合成接收器仅监听 IPv4；健康检查已固定使用 `127.0.0.1`，避免伪不健康。

## 3. 安全边界

- 所有演练告警、端口、标签和秘密标记均为合成数据。
- Alertmanager 到合成网关的 HTTP 链路只位于隔离 Compose 网络；生产环境必须使用认证、TLS 和经批准的秘密管理。
- 告警规则仍禁止对象级、高基数或敏感标签。
- 合成网关的脱敏证明只覆盖通知证据持久化，不证明正式第三方通知服务的传输与保留策略。

## 4. 剩余风险与下一轮入口

本轮关闭 Alertmanager 工程配置、重复通知抑制、恢复通知和证据脱敏缺口，但以下事项仍未关闭：

- 正式值班平台、邮件或企业 Webhook 的认证、TLS、轮换和回执；
- 告警确认、升级、静默、误报处置和跨班次值守演练；
- MySQL/Redis/Worker 多实例长时混合压测与容量报告；
- 候选秘密旧密钥读取、密钥轮换及回滚演练；
- 预生产、业务/UAT 和运维签字。

下一轮进入 WP4/M5 完成度复核前的密钥轮换与多实例稳定性缺口选择，优先处理候选秘密密钥轮换演练。
