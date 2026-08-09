# WP4 第 1 次开发迭代：安全审计与 SBOM 门禁

- 日期：2026-08-09
- 工作包：WP4 M5 安全、恢复、性能与可观测性准入
- 范围：建立 Python/Node 生产依赖审计、API SAST、CycloneDX SBOM、证据结构校验和提交级制品摘要；修复首次审计暴露的依赖风险。

## 交付

- 新增 `scripts/security-gate.ps1`，统一运行安全脚本 Ruff、4 项校验器单测、Bandit、`pip-audit`、`pnpm audit`、API CycloneDX SBOM 和 SHA-256 清单。
- 新增 `scripts/verify_security_artifacts.py`，拒绝缺失/损坏报告、Python 已知漏洞、Node 高危/严重漏洞、中高置信度 Bandit 中高危结果以及无组件的非 CycloneDX 文件。
- `scripts/check.ps1` 增加 `-IncludeSecurity`；根 `package.json` 增加 `pnpm security:audit`。
- GitHub Actions 新增 `security-supply-chain` 作业，生成仓库级 CycloneDX SBOM，并以 `security-evidence-<commit-sha>` 上传 30 天证据。
- 新增的 Anchore SBOM 和 Artifact 上传动作使用完整提交 SHA 固定，避免新供应链门禁继续依赖可移动标签。
- 修复 `nanoid` 生产依赖高危审计结果；将 API `cryptography` 升级到 50.x 安全基线，并将 pytest 下限提高到 9.0.3。

## 本地验证

- `pnpm audit --prod --audit-level high --json`：高危 0、严重 0。
- `pnpm security:audit`：通过；生成并校验 API 依赖报告、API CycloneDX SBOM、Bandit 报告、pnpm 审计报告和 SHA-256 清单。
- `./scripts/check.ps1 -SkipInstall -IncludeSecurity`：通过；覆盖 API Ruff/pytest/覆盖率/迁移、前端 lint/typecheck/test/build、Desktop Release build/test 及安全门禁。
- 安全证据校验器：4/4 单元测试通过。
- `git diff --check` 与 CI YAML 解析：通过。

## 远端验证

- 功能提交：`dffdffc`。
- GitHub Actions `31322842317`：API、Frontend、Desktop、Container Images、Security Supply Chain 及 Chromium、Firefox、WebKit 三个 E2E 作业全部通过。
- 远端制品 `security-evidence-dffdffc57cdb7258aee40aade8061edc3455b17d` 已实际下载；API 审计、API SBOM、Bandit、pnpm 审计和仓库 SBOM五份 JSON 证据再次通过本地结构与阻断规则校验。

## 状态边界

- 本轮只关闭首批源码/依赖/SBOM 自动化，不宣称 WP4 安全准入全部完成。
- 当前 SBOM 是 CI 源码和已安装依赖快照，并以提交 SHA 命名和 SHA-256 清单关联；尚未签名，也不是生产制品来源证明。
- 容器镜像扫描、秘密扫描、DAST、人工安全测试、安全豁免治理、恢复演练、性能基线、指标出口和目标 Compose 回归仍未关闭。
- 下一轮优先增加容器镜像扫描与秘密扫描，并形成高危阻断和限期豁免结构。
