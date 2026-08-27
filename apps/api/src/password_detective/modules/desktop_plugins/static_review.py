from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from password_detective.core.errors import AppError
from password_detective.db.models.desktop_plugin import (
    DesktopPlugin,
    DesktopPluginArtifact,
    DesktopPluginFindingSeverity,
    DesktopPluginReviewStage,
    DesktopPluginSigningKey,
    DesktopPluginVersion,
)
from password_detective.modules.desktop_plugins.package_verifier import verify_plugin_package
from password_detective.modules.desktop_plugins.storage import DesktopPluginStorage

STATIC_REVIEW_POLICY_VERSION = "desktop-plugin-static-review-v1"
_MAX_SCAN_FILE_BYTES = 16 * 1024 * 1024
_MAX_SBOM_BYTES = 4 * 1024 * 1024
_TEXT_SUFFIXES = {
    ".cs",
    ".go",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".rs",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_STATIC_STAGES = (
    DesktopPluginReviewStage.STRUCTURE,
    DesktopPluginReviewStage.SIGNATURE,
    DesktopPluginReviewStage.SBOM,
    DesktopPluginReviewStage.VULNERABILITY,
    DesktopPluginReviewStage.LICENSE,
    DesktopPluginReviewStage.SECRET,
    DesktopPluginReviewStage.STATIC_BEHAVIOR,
    DesktopPluginReviewStage.PE_ANALYSIS,
)
_DENIED_LICENSES = {"AGPL-3.0", "AGPL-3.0-only", "SSPL-1.0"}
_KNOWN_VULNERABILITIES = {
    ("log4j-core", "2.14.1"): ("CVE-2021-44228", "critical"),
    ("lodash", "4.17.20"): ("CVE-2021-23337", "high"),
}
_SECRET_PATTERNS = (
    ("PD-SECRET-001", re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "私钥材料"),
    ("PD-SECRET-002", re.compile(rb"AKIA[0-9A-Z]{16}"), "云访问密钥"),
    ("PD-SECRET-003", re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"), "代码托管访问令牌"),
)


class StaticReviewInfrastructureError(RuntimeError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True)
class StaticFinding:
    stage: DesktopPluginReviewStage
    rule_id: str
    severity: DesktopPluginFindingSeverity
    title: str
    detail: str
    file_path: str | None = None
    evidence: dict = field(default_factory=dict)
    blocked: bool = False
    developer_visible: bool = True


@dataclass(frozen=True)
class StaticReviewResult:
    findings: tuple[StaticFinding, ...]
    summary: dict
    evidence: dict

    @property
    def blocked(self) -> bool:
        return any(finding.blocked for finding in self.findings)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo, maximum: int) -> bytes:
    if info.file_size > maximum:
        raise ValueError("entry_too_large")
    with archive.open(info, "r") as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise ValueError("entry_too_large")
    return value


def _finding(
    stage: DesktopPluginReviewStage,
    rule_id: str,
    severity: DesktopPluginFindingSeverity,
    title: str,
    detail: str,
    *,
    file_path: str | None = None,
    evidence: dict | None = None,
    blocked: bool = False,
) -> StaticFinding:
    return StaticFinding(
        stage=stage,
        rule_id=rule_id,
        severity=severity,
        title=title,
        detail=detail,
        file_path=file_path,
        evidence=evidence or {},
        blocked=blocked,
    )


def _license_ids(component: dict) -> set[str]:
    values: set[str] = set()
    for entry in component.get("licenses", []):
        if not isinstance(entry, dict):
            continue
        license_value = entry.get("license")
        if isinstance(license_value, dict) and isinstance(license_value.get("id"), str):
            values.add(license_value["id"])
        elif isinstance(entry.get("expression"), str):
            values.add(entry["expression"])
    return values


def _scan_sbom(
    archive: zipfile.ZipFile, entries: dict[str, zipfile.ZipInfo]
) -> tuple[list[StaticFinding], dict]:
    findings: list[StaticFinding] = []
    sbom_path = next((path for path in ("sbom.cdx.json", "sbom.json") if path in entries), None)
    if sbom_path is None:
        findings.append(
            _finding(
                DesktopPluginReviewStage.SBOM,
                "PD-SBOM-001",
                DesktopPluginFindingSeverity.HIGH,
                "缺少 CycloneDX SBOM",
                "插件包必须提供可解析的 CycloneDX JSON 软件物料清单。",
                blocked=True,
            )
        )
        return findings, {"present": False, "components": 0}
    try:
        sbom = json.loads(_read_entry(archive, entries[sbom_path], _MAX_SBOM_BYTES))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        findings.append(
            _finding(
                DesktopPluginReviewStage.SBOM,
                "PD-SBOM-002",
                DesktopPluginFindingSeverity.HIGH,
                "SBOM 无法解析",
                "CycloneDX SBOM 必须是大小受限的有效 UTF-8 JSON。",
                file_path=sbom_path,
                blocked=True,
            )
        )
        return findings, {"present": True, "valid": False, "components": 0}
    if not isinstance(sbom, dict) or sbom.get("bomFormat") != "CycloneDX" or not isinstance(
        sbom.get("components"), list
    ):
        findings.append(
            _finding(
                DesktopPluginReviewStage.SBOM,
                "PD-SBOM-003",
                DesktopPluginFindingSeverity.HIGH,
                "SBOM 合同不兼容",
                "SBOM 必须声明 bomFormat=\"CycloneDX\" 并包含 components 数组。",
                file_path=sbom_path,
                blocked=True,
            )
        )
        return findings, {"present": True, "valid": False, "components": 0}

    components = [item for item in sbom["components"] if isinstance(item, dict)]
    for component in components:
        name = component.get("name")
        version = component.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            findings.append(
                _finding(
                    DesktopPluginReviewStage.SBOM,
                    "PD-SBOM-004",
                    DesktopPluginFindingSeverity.MEDIUM,
                    "SBOM 组件缺少名称或版本",
                    "每个组件必须提供用于漏洞匹配的名称和版本。",
                    file_path=sbom_path,
                    blocked=True,
                )
            )
            continue
        advisory = _KNOWN_VULNERABILITIES.get((name.lower(), version))
        if advisory:
            advisory_id, severity = advisory
            findings.append(
                _finding(
                    DesktopPluginReviewStage.VULNERABILITY,
                    "PD-VULN-001",
                    DesktopPluginFindingSeverity(severity),
                    "命中已知高危依赖",
                    "组件命中审核策略中的高危漏洞快照，升级或移除后重新提交。",
                    file_path=sbom_path,
                    evidence={"component": name, "version": version, "advisory_id": advisory_id},
                    blocked=True,
                )
            )
        licenses = _license_ids(component)
        if not licenses:
            findings.append(
                _finding(
                    DesktopPluginReviewStage.LICENSE,
                    "PD-LICENSE-001",
                    DesktopPluginFindingSeverity.LOW,
                    "组件未声明许可证",
                    "组件缺少标准许可证标识，人工审核时需要确认分发合规性。",
                    file_path=sbom_path,
                    evidence={"component": name, "version": version},
                )
            )
        denied = sorted(licenses & _DENIED_LICENSES)
        if denied:
            findings.append(
                _finding(
                    DesktopPluginReviewStage.LICENSE,
                    "PD-LICENSE-002",
                    DesktopPluginFindingSeverity.HIGH,
                    "许可证不符合市场分发策略",
                    "组件许可证要求与当前插件市场分发政策不兼容。",
                    file_path=sbom_path,
                    evidence={"component": name, "licenses": denied},
                    blocked=True,
                )
            )
    return findings, {"present": True, "valid": True, "components": len(components)}


def _scan_entries(
    archive: zipfile.ZipFile,
    entries: dict[str, zipfile.ZipInfo],
    requested_capabilities: set[str],
) -> list[StaticFinding]:
    findings: list[StaticFinding] = []
    seen: set[tuple[str, str]] = set()
    for path, info in entries.items():
        if info.is_dir() or info.file_size > _MAX_SCAN_FILE_BYTES:
            continue
        try:
            content = _read_entry(archive, info, _MAX_SCAN_FILE_BYTES)
        except ValueError:
            continue
        for rule_id, pattern, label in _SECRET_PATTERNS:
            if pattern.search(content) and (rule_id, path) not in seen:
                seen.add((rule_id, path))
                findings.append(
                    _finding(
                        DesktopPluginReviewStage.SECRET,
                        rule_id,
                        DesktopPluginFindingSeverity.CRITICAL,
                        "插件包包含疑似秘密材料",
                        f"检测到{label}特征；报告不会回显命中值。",
                        file_path=path,
                        evidence={"pattern": label},
                        blocked=True,
                    )
                )
        lowered = content.lower()
        behavior_rules = (
            (b"currentversion\\run", "PD-STATIC-001", "检测到持久化注册表路径", True),
            (b"credreadw", "PD-STATIC-002", "检测到凭据读取 API", True),
            (b"cryptunprotectdata", "PD-STATIC-003", "检测到系统凭据解密 API", True),
            (b"powershell.exe", "PD-STATIC-004", "检测到 PowerShell 进程派生", True),
            (b"invoke-expression", "PD-STATIC-005", "检测到动态脚本执行", True),
        )
        for marker, rule_id, title, blocked in behavior_rules:
            if marker in lowered and (rule_id, path) not in seen:
                seen.add((rule_id, path))
                findings.append(
                    _finding(
                        DesktopPluginReviewStage.STATIC_BEHAVIOR,
                        rule_id,
                        (
                            DesktopPluginFindingSeverity.CRITICAL
                            if blocked
                            else DesktopPluginFindingSeverity.HIGH
                        ),
                        title,
                        "静态规则命中禁止行为；审核证据仅保留规则和文件位置。",
                        file_path=path,
                        blocked=blocked,
                    )
                )
        if (
            (b"winhttpopen" in lowered or re.search(rb"https?://", lowered))
            and "network:internet" not in requested_capabilities
            and ("PD-STATIC-006", path) not in seen
        ):
            seen.add(("PD-STATIC-006", path))
            findings.append(
                _finding(
                    DesktopPluginReviewStage.STATIC_BEHAVIOR,
                    "PD-STATIC-006",
                    DesktopPluginFindingSeverity.HIGH,
                    "检测到未声明网络访问",
                    "插件未申请 network:internet，但制品包含网络访问指标。",
                    file_path=path,
                    blocked=True,
                )
            )
        if Path(path).suffix.lower() in _TEXT_SUFFIXES:
            source_rules = (
                (b"process.start(", "PD-SEMGREP-001", "源码调用进程启动 API"),
                (b"os.system(", "PD-SEMGREP-002", "源码调用系统命令 API"),
                (b"subprocess.popen(", "PD-SEMGREP-003", "源码派生子进程"),
            )
            for marker, rule_id, title in source_rules:
                if marker in lowered and (rule_id, path) not in seen:
                    seen.add((rule_id, path))
                    findings.append(
                        _finding(
                            DesktopPluginReviewStage.STATIC_BEHAVIOR,
                            rule_id,
                            DesktopPluginFindingSeverity.HIGH,
                            title,
                            "源码语义规则命中禁止的进程派生行为。",
                            file_path=path,
                            blocked=True,
                        )
                    )
        if (
            path.lower().startswith("bin/")
            and path.lower().endswith(".exe")
            and not content.startswith(b"MZ")
        ):
            findings.append(
                _finding(
                    DesktopPluginReviewStage.PE_ANALYSIS,
                    "PD-PE-001",
                    DesktopPluginFindingSeverity.HIGH,
                    "Windows 入口不是 PE 文件",
                    "Windows 可执行入口必须包含有效的 MZ 文件头。",
                    file_path=path,
                    blocked=True,
                )
            )
    return findings


def inspect_version_artifacts(
    *,
    storage: DesktopPluginStorage,
    plugin: DesktopPlugin,
    version: DesktopPluginVersion,
    signing_key: DesktopPluginSigningKey,
    artifacts: list[DesktopPluginArtifact],
    max_expanded_bytes: int,
) -> StaticReviewResult:
    findings: list[StaticFinding] = []
    artifact_evidence: list[dict] = []
    stage_evidence: dict[str, dict] = {}
    for artifact in artifacts:
        if not artifact.storage_key:
            raise StaticReviewInfrastructureError(
                "desktop_plugin.review_artifact_key_missing", "审核制品暂不可用。"
            )
        path = storage.quarantine_path(artifact.storage_key)
        if not path.is_file():
            raise StaticReviewInfrastructureError(
                "desktop_plugin.review_artifact_missing", "审核制品暂不可用。"
            )
        actual_sha256 = _sha256(path)
        artifact_evidence.append(
            {
                "artifact_id": artifact.id,
                "architecture": artifact.architecture,
                "expected_sha256": artifact.sha256,
                "actual_sha256": actual_sha256,
                "size_bytes": path.stat().st_size,
            }
        )
        if actual_sha256 != artifact.sha256:
            findings.append(
                _finding(
                    DesktopPluginReviewStage.STRUCTURE,
                    "PD-INTEGRITY-001",
                    DesktopPluginFindingSeverity.CRITICAL,
                    "隔离制品摘要发生变化",
                    "冻结后的制品 SHA-256 与数据库快照不一致。",
                    file_path=artifact.artifact_filename,
                    blocked=True,
                )
            )
            continue
        try:
            verify_plugin_package(
                path,
                architecture=artifact.architecture,
                project_slug=plugin.slug,
                semver=version.semver,
                signing_key_id=signing_key.key_id,
                public_key_base64=signing_key.public_key_base64,
                protocol_min=version.protocol_min,
                protocol_max=version.protocol_max,
                host_min=version.host_min,
                host_max=version.host_max,
                requested_capabilities=list(version.requested_capabilities),
                source_review_mode=version.source_review_mode,
                max_expanded_bytes=max_expanded_bytes,
            )
        except AppError as exc:
            findings.append(
                _finding(
                    DesktopPluginReviewStage.SIGNATURE,
                    "PD-SIGNATURE-001",
                    DesktopPluginFindingSeverity.CRITICAL,
                    "开发者签名复核失败",
                    "自动审核无法重新验证冻结制品的开发者签名。",
                    file_path=artifact.artifact_filename,
                    evidence={"error_code": exc.code},
                    blocked=True,
                )
            )
            continue
        try:
            with zipfile.ZipFile(path, "r") as archive:
                entries = {info.filename.rstrip("/"): info for info in archive.infolist()}
                sbom_findings, sbom_summary = _scan_sbom(archive, entries)
                findings.extend(sbom_findings)
                findings.extend(
                    _scan_entries(archive, entries, set(version.requested_capabilities))
                )
                stage_evidence[artifact.architecture] = {
                    "entries": len(entries),
                    "sbom": sbom_summary,
                }
        except zipfile.BadZipFile:
            findings.append(
                _finding(
                    DesktopPluginReviewStage.STRUCTURE,
                    "PD-STRUCTURE-001",
                    DesktopPluginFindingSeverity.CRITICAL,
                    "冻结制品结构损坏",
                    "自动审核无法读取冻结后的插件 ZIP。",
                    file_path=artifact.artifact_filename,
                    blocked=True,
                )
            )

    unique_findings: dict[tuple[str, str | None, str], StaticFinding] = {}
    for finding in findings:
        unique_findings[(finding.rule_id, finding.file_path, finding.title)] = finding
    normalized = tuple(unique_findings.values())
    stages = {
        stage.value: {
            "status": "failed"
            if any(item.stage == stage and item.blocked for item in normalized)
            else "warning"
            if any(item.stage == stage for item in normalized)
            else "passed"
        }
        for stage in _STATIC_STAGES
    }
    summary = {
        "policy_version": STATIC_REVIEW_POLICY_VERSION,
        "blocked": any(item.blocked for item in normalized),
        "finding_count": len(normalized),
        "blocking_finding_count": sum(1 for item in normalized if item.blocked),
        "stages": stages,
    }
    evidence = {
        "policy_version": STATIC_REVIEW_POLICY_VERSION,
        "plugin_id": plugin.id,
        "version_id": version.id,
        "manifest_sha256": version.manifest_sha256,
        "artifacts": artifact_evidence,
        "stage_evidence": stage_evidence,
        "findings": [
            {
                "stage": item.stage.value,
                "rule_id": item.rule_id,
                "severity": item.severity.value,
                "file_path": item.file_path,
                "blocked": item.blocked,
                "evidence": item.evidence,
            }
            for item in normalized
        ],
    }
    return StaticReviewResult(findings=normalized, summary=summary, evidence=evidence)
