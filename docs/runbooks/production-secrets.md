# 生产文件型密钥与加密备份运行手册

## 1. 决策

密码侦探社生产环境不把外部 KMS 作为上线前置条件，采用以下基线：

- Docker Secrets 文件注入；
- 应用现有 AES-GCM 候选秘密密钥环；
- 应用签名、候选秘密、去重、MySQL、Redis 和通知凭据相互独立；
- 宿主机秘密目录最小权限；
- 离线口令保护的认证加密备份；
- 版本化轮换，旧版本在数据迁移和回滚窗口结束前保留。

外部 KMS 仅在多服务器、多运维人员、强审计或合规要求出现后重新评估。本手册中的文件型方案是当前正式生产基线，不是临时开发默认值。

## 2. 安全边界

- 生产秘密目录固定放在项目仓库之外，建议 `/opt/password-detective-secrets`。
- 目录权限为 `700`，秘密文件权限为 `600`；禁止符号链接。
- 真实秘密不得进入 `.env`、Compose YAML、镜像、Git、日志、工单或证据包。
- Docker 将秘密挂载到 `/run/secrets`；API 镜像入口以 root 复制到容器临时文件系统 `/run/password-detective-secrets`，设置为应用用户 `0400` 后立即通过 `su-exec` 降权运行。
- MySQL 使用镜像原生 `MYSQL_PASSWORD_FILE`/`MYSQL_ROOT_PASSWORD_FILE`；Redis 在容器临时配置中加载口令，不把口令写入 Compose 渲染结果。
- 备份口令不得与加密备份、服务器登录密钥或生产秘密目录存放在同一位置。
- 本方案不能防御已经取得宿主机 root 权限的攻击者；发现 root、部署账号或宿主机镜像泄露时，必须按全部生产秘密泄露处理。

## 3. 本地合同门禁

以下命令只生成合成秘密并验证配置，不接触生产服务器：

```powershell
pnpm production-secrets:contract
./scripts/check.ps1 -SkipInstall -IncludeProductionSecrets
```

合同门禁检查：

1. 秘密初始化与权限约束；
2. Docker Compose 双文件合并成功；
3. API、Worker、Scheduler 仅收到 `*_FILE` 路径；
4. Compose 渲染结果不包含生成的秘密值；
5. MySQL、Redis 均使用文件型密码；
6. API 容器复制秘密后降权到 `app` 用户。

## 4. 首次初始化

### 4.1 准备工具镜像

在服务器项目目录执行：

```bash
docker build -f infra/docker/api.Dockerfile -t password-detective-api-tools:local .
sudo install -d -m 700 -o root -g root /opt/password-detective-secrets
```

### 4.2 生成独立生产秘密

```bash
docker run --rm --user 0:0 \
  -v /opt/password-detective-secrets:/secrets \
  -v "$PWD/scripts/manage_production_secrets.py:/tool.py:ro" \
  password-detective-api-tools:local \
  python /tool.py init --directory /secrets --candidate-version v1
```

工具生成以下受管文件：

| 文件 | 用途 |
|---|---|
| `app_secret_key` | 应用令牌与安全上下文主秘密 |
| `candidate_secret_key_version` | 当前候选秘密写入版本 |
| `candidate_secret_keyring` | AES-GCM 候选秘密版本密钥环 |
| `candidate_secret_dedup_key` | 稳定 HMAC 去重秘密；正常轮换中不得改变 |
| `direct_message_key_version` | 当前私信正文加密写入版本 |
| `direct_message_keyring` | 独立 AES-GCM 私信密钥环；不得复用应用主秘密或候选秘密密钥 |
| `mysql_password` / `mysql_root_password` | MySQL 应用和 root 密码 |
| `redis_password` | Redis 认证密码 |
| `database_url` / `redis_url` | 包含编码后凭据的应用连接地址 |
| `notification_webhook_secret` | Webhook 签名秘密；未启用时为空文件 |
| `notification_smtp_password` | SMTP 认证秘密；未启用时为空文件 |

初始化命令拒绝覆盖任何已存在的受管文件。不得使用删除目录后重建的方式“修复”生产秘密。

### 4.3 验证

```bash
docker run --rm --user 0:0 \
  -v /opt/password-detective-secrets:/secrets:ro \
  -v "$PWD/scripts/manage_production_secrets.py:/tool.py:ro" \
  password-detective-api-tools:local \
  python /tool.py verify --directory /secrets
```

只有输出 `status: valid` 才可继续。工具输出版本、文件数量和状态，不输出秘密值。

## 5. 启动生产秘密 Compose

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.production-secrets.yml \
  --env-file infra/production/production-secrets.env.example \
  config >/tmp/password-detective-compose.rendered.yml

docker compose \
  -f docker-compose.yml \
  -f docker-compose.production-secrets.yml \
  --env-file infra/production/production-secrets.env.example \
  up -d --build
```

当前不处理域名和 HTTPS；非秘密端口、CORS 与通知后端可在复制后的生产参数文件中调整。真实密码不得写入该参数文件。

启动后至少验证：

```bash
curl --fail http://127.0.0.1:8000/api/v1/health/ready
docker compose -f docker-compose.yml -f docker-compose.production-secrets.yml ps
```

禁止通过 `docker inspect`、进程参数或日志输出秘密值进行“验证”。

## 6. 加密备份

备份采用 Scrypt 派生密钥和 Fernet 认证加密，能够同时检测密文篡改和错误口令。备份口令至少 16 个字符，建议使用独立随机长口令并离线保管。

```bash
# /mnt/offline/backup-passphrase 只在操作期间挂载，文件权限 600。
docker run --rm --user 0:0 \
  -v /opt/password-detective-secrets:/secrets:ro \
  -v /mnt/offline:/offline \
  -v /var/backups/password-detective:/backups \
  -v "$PWD/scripts/manage_production_secrets.py:/tool.py:ro" \
  password-detective-api-tools:local \
  python /tool.py backup \
    --directory /secrets \
    --output /backups/production-secrets-$(date -u +%Y%m%dT%H%M%SZ).pdsb \
    --passphrase-file /offline/backup-passphrase
```

备份完成后：

- 将 `.pdsb` 复制到异地受控位置；
- 保存 SHA-256，但不要把口令与备份放在一起；
- 每季度至少做一次恢复演练；
- 不把解密后的秘密目录打包上传。

## 7. 恢复演练

恢复必须先写入隔离目录，不直接覆盖生产目录：

```bash
sudo install -d -m 700 -o root -g root /opt/password-detective-secrets-restore-test

docker run --rm --user 0:0 \
  -v /opt/password-detective-secrets-restore-test:/restore \
  -v /mnt/offline:/offline:ro \
  -v /var/backups/password-detective:/backups:ro \
  -v "$PWD/scripts/manage_production_secrets.py:/tool.py:ro" \
  password-detective-api-tools:local \
  python /tool.py restore \
    --input /backups/<备份文件>.pdsb \
    --directory /restore \
    --passphrase-file /offline/backup-passphrase
```

恢复成功后再次执行 `verify`，并核对当前候选密钥版本。演练目录验证结束后按受控流程销毁，不得长期留在生产服务器。

## 8. 候选秘密密钥轮换

建议周期为 90 天；发生疑似泄露时立即轮换。去重密钥不进行常规同步轮换，否则会破坏历史候选去重一致性。

### 8.1 备份并加入新版本

```bash
docker run --rm --user 0:0 \
  -v /opt/password-detective-secrets:/secrets \
  -v /mnt/offline:/offline:ro \
  -v /var/backups/password-detective:/backups \
  -v "$PWD/scripts/manage_production_secrets.py:/tool.py:ro" \
  password-detective-api-tools:local \
  python /tool.py rotate-candidate \
    --directory /secrets \
    --new-version v2 \
    --backup-output /backups/before-candidate-v2.pdsb \
    --passphrase-file /offline/backup-passphrase
```

该命令先创建认证加密备份，再将新版本加入密钥环并切换当前写入版本；旧版本不会被删除。

### 8.2 重启应用进程

```bash
docker compose -f docker-compose.yml -f docker-compose.production-secrets.yml \
  --env-file infra/production/production-secrets.env.example \
  up -d --no-deps --force-recreate api worker scheduler
```

### 8.3 数据重加密

生产镜像不包含仓库 `scripts/`。正式操作把轮换脚本只读挂载到一次性 API 工具容器；第一条命令默认为 dry-run：

```bash
docker compose -f docker-compose.yml -f docker-compose.production-secrets.yml \
  --env-file infra/production/production-secrets.env.example \
  run --rm -v "$PWD/scripts/rotate_candidate_secrets.py:/rotation.py:ro" api \
  python /rotation.py --target-version v2

# 审核 dry-run 报告后执行：
docker compose -f docker-compose.yml -f docker-compose.production-secrets.yml \
  --env-file infra/production/production-secrets.env.example \
  run --rm -v "$PWD/scripts/rotate_candidate_secrets.py:/rotation.py:ro" api \
  python /rotation.py --target-version v2 --apply
```

完成后执行健康检查、揭示业务抽样和审计检查。旧版本密钥至少保留一个完整备份/回滚周期；删除旧版本必须另开变更，不由轮换工具自动执行。

## 9. 应急吊销

出现秘密泄露迹象时：

1. 隔离受影响主机和部署账号；
2. 保存必要的脱敏审计证据，不复制秘密值；
3. 全量轮换应用签名、数据库、Redis、通知和候选秘密密钥；
4. 撤销活跃会话；
5. 重新加密候选秘密并验证历史版本读取；
6. 重新生成加密备份；
7. 只有在确认宿主机可信后恢复服务。

仅轮换候选 AES-GCM 密钥不足以处理宿主机 root 泄露。
