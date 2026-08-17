# 安全与供应链门禁

## 目标

WP4 首批门禁把生产依赖漏洞、API 静态安全扫描和软件物料清单纳入本地及 GitHub Actions。它提供可重复、可下载的工程证据，但不替代镜像扫描、DAST、秘密扫描、人工渗透测试、制品签名或生产来源证明。

## 本地执行

首次执行前安装 API 安全工具和前端依赖：

```powershell
$env:PYTHONUTF8 = "1"
./apps/api/.venv/Scripts/python.exe -m pip install -e ".\apps\api[dev,security]"
pnpm install --frozen-lockfile
```

运行独立安全门禁：

```powershell
pnpm security:audit
```

或把安全门禁并入统一检查：

```powershell
./scripts/check.ps1 -SkipInstall -IncludeSecurity
```

默认输出位于 `.local/security/`，不会提交 Git。

## 门禁内容

| 门禁 | 范围 | 阻断规则 | 证据 |
|---|---|---|---|
| Python 生产依赖审计 | `apps/api/pyproject.toml` 的默认依赖及其传递依赖 | `pip-audit --strict` 发现已知漏洞或审计失败 | `api-dependency-audit.json` |
| Node 生产依赖审计 | pnpm 工作区生产依赖 | `pnpm audit --prod --audit-level high` 发现高危或严重漏洞 | `pnpm-audit.json` |
| API SAST | `apps/api/src` | Bandit 中高置信度的中危或高危结果 | `bandit-report.json` |
| API SBOM | Python 生产依赖解析结果 | 必须是含组件的 CycloneDX JSON | `api-sbom.cdx.json` |
| 仓库 SBOM | GitHub Actions 检出的仓库、锁文件和已安装依赖 | 必须是含组件的 CycloneDX JSON | `repository-sbom.cdx.json` |
| 证据完整性 | 上述 JSON 证据 | 文件缺失、JSON 无法解析、SBOM 格式错误或阻断结果存在 | `SHA256SUMS` |

`verify_security_artifacts.py` 对审计结构、阻断计数、Bandit 结果和 CycloneDX 组件进行二次校验。校验器使用合成夹具执行 4 项单元测试。

## GitHub Actions 证据

`security-supply-chain` 作业执行以下步骤：

1. 安装固定版本的 `pip-audit` 与 Bandit。
2. 执行 Python/Node 生产依赖审计和 API SAST。
3. 生成 API 与仓库级 CycloneDX SBOM。
4. 校验证据并生成 SHA-256 清单。
5. 以 `security-evidence-<commit-sha>` 名称保留 30 天；失败时也上传已经生成的部分报告。

仓库 SBOM 与上传动作使用完整提交 SHA 固定第三方 Action。功能提交 `dffdffc` 对应 GitHub Actions `31322842317`，八个作业全部通过；下载后的五份 JSON 证据再次通过本地校验。

## 首轮修复

- pnpm 工作区通过 `pnpm-workspace.yaml` 覆盖将受影响的 `nanoid` `<3.3.18` 收口到 `3.3.18`。
- API 将 `cryptography` 下限提高到 50.0.0，并限制在 51 之前。
- 测试工具将 pytest 下限提高到 9.0.3，并验证现有 API 回归保持通过。

## 尚未关闭

- API、Web、Admin 容器镜像 CVE 扫描与基础镜像更新策略。
- Git 历史和工作树秘密扫描。
- DAST、对象级越权、CSRF/XSS、批量资源消耗专项安全测试。
- SBOM 签名、SLSA/来源证明、长期制品仓库和发布版本绑定。
- 安全豁免登记、责任人、到期时间和复核流程。


## 后续门禁衔接

WP4 第 2 次迭代已将最终容器镜像、仓库 Secret 和限期风险接受接入 CI。扫描对象、阻断规则、登记格式和首批远端证据见 [发布镜像、Secret 与风险接受门禁](./release-security-gates.md)。DAST、人工安全测试、恢复、性能和目标环境仍为独立未关闭项。
