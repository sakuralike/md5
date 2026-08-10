# 候选秘密密钥轮换运行手册

## 1. 适用范围

本手册用于 `password_candidates` 候选秘密的应用层加密密钥轮换和回滚。命令不会修改数据库结构，也不会轮换账号密码哈希、JWT 密钥、通知凭据或桌面安装密钥。

## 2. 配置模型

| 变量 | 用途 | 轮换要求 |
| --- | --- | --- |
| `CANDIDATE_SECRET_KEY_VERSION` | 当前写入版本 | 必须存在于非空 keyring 中 |
| `CANDIDATE_SECRET_KEYRING` | JSON 格式版本到密钥映射 | 正向轮换和回滚窗口内同时保留新旧版本 |
| `CANDIDATE_SECRET_DEDUP_KEY` | 稳定 HMAC 去重密钥 | 正向轮换和回滚期间绝对不可改变 |

所有示例均为合成占位符。生产值必须从受控 Secret/KMS 注入，不得写入 Git、命令历史、工单正文或证据文件。

```dotenv
CANDIDATE_SECRET_KEY_VERSION=v2
CANDIDATE_SECRET_KEYRING={"v1":"<secret-manager:legacy>","v2":"<secret-manager:current>"}
CANDIDATE_SECRET_DEDUP_KEY=<secret-manager:stable-dedup>
```

## 3. 正向轮换

1. 冻结密钥配置变更，确认数据库备份可恢复，并记录变更单和回滚负责人。
2. 在 Secret/KMS 创建新版本，保留旧版本，保持去重密钥不变。
3. 部署应用：当前版本设为新版本，keyring 同时包含新旧版本。
4. 对健康、查询、贡献和揭示路径做合成冒烟，确认新写入记录使用新版本、旧记录仍可读。
5. 默认 dry-run：

```powershell
apps/api/.venv/Scripts/python.exe scripts/rotate_candidate_secrets.py `
  --target-version v2 `
  --source-version v1 `
  --report .local/candidate-secret-rotation/dry-run.json
```

6. 核对 `scanned`、`rotated`、`skipped`、`source_versions` 和 `target_version`，确认没有异常版本。
7. 在受控变更窗口执行 apply：

```powershell
apps/api/.venv/Scripts/python.exe scripts/rotate_candidate_secrets.py `
  --apply `
  --target-version v2 `
  --source-version v1 `
  --report .local/candidate-secret-rotation/apply.json
```

8. 再次 dry-run；预期 v1 来源的 `rotated=0`。执行查询、贡献、揭示和桌面验证冒烟。
9. 保留旧密钥至回滚窗口结束。确认旧版本库存为零、备份有效、监控无异常后，按双人审批移除旧版本。

## 4. 回滚

若新密钥写入后出现可读性、性能或依赖异常：

1. 不改变 `CANDIDATE_SECRET_DEDUP_KEY`。
2. 将旧版本重新设置为当前版本，keyring 继续保留新旧两个版本。
3. 先执行以旧版本为目标的 dry-run，核对来源分布。
4. 执行 apply，将新版本密文重新加密为旧版本。
5. 验证新旧期间写入的候选均可读取，去重冲突数量没有变化。
6. 回滚完成前不得删除新密钥；确认库存新版本为零后再按审批流程处置。

## 5. 失败处理

- `archive.secret_unavailable`：缺少对应版本或密文认证失败。停止轮换，核对 Secret/KMS 版本和备份，不得尝试跳过错误记录。
- `archive.secret_dedup_mismatch`：稳定去重密钥不一致或库存数据损坏。事务会停止；恢复正确去重密钥后重新 dry-run。
- 目标版本保护失败：命令参数与应用当前版本不一致。不得绕过，先修正部署配置。
- 进程中断：单次事务未提交时数据库回滚；重新执行 dry-run，依据版本分布确认状态。

## 6. 演练与证据

```powershell
pnpm candidate-secrets:drill
```

或纳入统一检查：

```powershell
./scripts/check.ps1 -SkipInstall -IncludeKeyRotation
```

证据目录为 `.local/candidate-secret-rotation-wp4-iteration-10/`。报告只允许保存计数、版本和布尔检查，不允许保存候选 ID、密文、nonce、去重标签、明文或密钥。
