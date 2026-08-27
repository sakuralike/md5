import type {
  DesktopRelease,
  DesktopReleaseChannel,
  DesktopReleaseCreateRequest,
  DesktopReleaseListResponse,
  DesktopArchitecture,
} from "@password-detective/api-contract";
import { createSHA256 } from "hash-wasm";
import { apiRequest } from "./api";

const VERSION_PATTERN = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?(?:-[0-9A-Za-z.-]+)?$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const ALLOWED_ARTIFACT_PATTERN = /\.(msix|msixbundle|exe)$/i;

type ParsedVersion = { numeric: number[]; prerelease: Array<number | string> | null };

function parseVersion(value: string): ParsedVersion | null {
  const match = VERSION_PATTERN.exec(value);
  if (!match) return null;
  const numeric = [Number(match[1]), Number(match[2]), Number(match[3]), Number(match[4] ?? 0)];
  const suffix = value.includes("-") ? value.slice(value.indexOf("-") + 1) : "";
  return {
    numeric,
    prerelease: suffix
      ? suffix.split(".").map((part) => (/^\d+$/.test(part) ? Number(part) : part.toLowerCase()))
      : null,
  };
}

function compareVersions(left: ParsedVersion, right: ParsedVersion): number {
  for (let index = 0; index < left.numeric.length; index += 1) {
    const difference = left.numeric[index]! - right.numeric[index]!;
    if (difference !== 0) return Math.sign(difference);
  }
  if (left.prerelease === null) return right.prerelease === null ? 0 : 1;
  if (right.prerelease === null) return -1;
  const count = Math.max(left.prerelease.length, right.prerelease.length);
  for (let index = 0; index < count; index += 1) {
    const leftPart = left.prerelease[index];
    const rightPart = right.prerelease[index];
    if (leftPart === undefined) return -1;
    if (rightPart === undefined) return 1;
    if (leftPart === rightPart) continue;
    if (typeof leftPart === "number" && typeof rightPart === "string") return -1;
    if (typeof leftPart === "string" && typeof rightPart === "number") return 1;
    return leftPart < rightPart ? -1 : 1;
  }
  return 0;
}

export interface DesktopReleaseDraftInput {
  channel: DesktopReleaseChannel;
  architecture: DesktopArchitecture;
  version: string;
  minimumSupportedVersion: string;
  mandatory: boolean;
  releaseNotes: string;
  artifactSha256: string;
  distributionAuthorized: boolean;
  legalDeclaration: string;
}

export interface ArtifactDescriptor {
  name: string;
  size: number;
  type: string;
}

export async function calculateArtifactSha256(artifact: Blob): Promise<string> {
  const bytes = await artifact.arrayBuffer();
  const subtle = globalThis.crypto?.subtle;
  if (subtle?.digest) {
    try {
      const digest = await subtle.digest("SHA-256", bytes);
      return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
    } catch {
      // Fall through to the pure WebAssembly implementation for non-secure contexts.
    }
  }
  const hasher = await createSHA256();
  hasher.init();
  hasher.update(new Uint8Array(bytes));
  return hasher.digest("hex");
}

export function buildDesktopReleasePayload(
  input: DesktopReleaseDraftInput,
  artifact: ArtifactDescriptor,
): DesktopReleaseCreateRequest {
  const version = input.version.trim();
  const minimumSupportedVersion = input.minimumSupportedVersion.trim();
  const artifactSha256 = input.artifactSha256.trim().toLowerCase();
  const legalDeclaration = input.legalDeclaration.trim();

  const parsedVersion = parseVersion(version);
  const parsedMinimum = parseVersion(minimumSupportedVersion);
  if (!parsedVersion || !parsedMinimum) {
    throw new Error("版本号必须使用 1.2.3 或 1.2.3-beta.1 格式");
  }
  if (compareVersions(parsedMinimum, parsedVersion) > 0) {
    throw new Error("最低受支持版本不能高于发布版本");
  }
  if (
    !artifact.name ||
    artifact.name.includes("/") ||
    artifact.name.includes("\\") ||
    !ALLOWED_ARTIFACT_PATTERN.test(artifact.name)
  ) {
    throw new Error("升级制品必须是无路径的 .msix、.msixbundle 或 .exe 文件名");
  }
  if (!Number.isSafeInteger(artifact.size) || artifact.size <= 0) {
    throw new Error("升级制品大小无效");
  }
  if (!SHA256_PATTERN.test(artifactSha256)) {
    throw new Error("SHA-256 必须是 64 位十六进制摘要");
  }
  if (!input.distributionAuthorized) {
    throw new Error("必须确认拥有升级制品的合法分发授权");
  }
  if (legalDeclaration.length < 20) {
    throw new Error("合法性声明至少需要 20 个字符");
  }

  return {
    channel: input.channel,
    platform: "windows",
    architecture: input.architecture,
    version,
    minimum_supported_version: minimumSupportedVersion,
    mandatory: input.mandatory,
    release_notes: input.releaseNotes.trim(),
    artifact_filename: artifact.name,
    artifact_sha256: artifactSha256,
    artifact_size_bytes: artifact.size,
    content_type: artifact.type || "application/octet-stream",
    distribution_authorized: input.distributionAuthorized,
    legal_declaration: legalDeclaration,
  };
}

export function validateArtifactForRelease(release: DesktopRelease, artifact: ArtifactDescriptor): void {
  if (artifact.name !== release.artifact_filename) {
    throw new Error(`文件名必须与发布记录一致：${release.artifact_filename}`);
  }
  if (artifact.size !== release.artifact_size_bytes) {
    throw new Error(`文件大小必须与发布记录一致：${release.artifact_size_bytes} 字节`);
  }
}

export function formatArtifactSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "未知";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GiB`;
}

export async function listDesktopReleases(token: string): Promise<DesktopRelease[]> {
  const response = await apiRequest<DesktopReleaseListResponse>(
    "/admin/desktop-releases",
    {},
    token,
  );
  return response.items;
}

export function createDesktopRelease(
  payload: DesktopReleaseCreateRequest,
  token: string,
): Promise<DesktopRelease> {
  return apiRequest<DesktopRelease>(
    "/admin/desktop-releases",
    { method: "POST", body: JSON.stringify(payload) },
    token,
  );
}

export function uploadDesktopReleaseArtifact(
  releaseId: string,
  artifact: File,
  token: string,
): Promise<DesktopRelease> {
  return apiRequest<DesktopRelease>(
    `/admin/desktop-releases/${encodeURIComponent(releaseId)}/artifact`,
    {
      method: "PUT",
      body: artifact,
      headers: { "Content-Type": "application/octet-stream" },
    },
    token,
  );
}

export function publishDesktopRelease(releaseId: string, token: string): Promise<DesktopRelease> {
  return apiRequest<DesktopRelease>(
    `/admin/desktop-releases/${encodeURIComponent(releaseId)}/publish`,
    { method: "POST" },
    token,
  );
}

export function withdrawDesktopRelease(releaseId: string, token: string): Promise<DesktopRelease> {
  return apiRequest<DesktopRelease>(
    `/admin/desktop-releases/${encodeURIComponent(releaseId)}/withdraw`,
    { method: "POST" },
    token,
  );
}
