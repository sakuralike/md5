import type { DesktopRelease } from "@password-detective/api-contract";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  buildDesktopReleasePayload,
  formatArtifactSize,
  uploadDesktopReleaseArtifact,
  validateArtifactForRelease,
} from "./desktopReleases";

const baseInput = {
  channel: "stable" as const,
  architecture: "x64" as const,
  version: "1.2.3",
  minimumSupportedVersion: "1.0.0",
  mandatory: false,
  releaseNotes: "合成发布说明",
  artifactSha256: "A".repeat(64),
  codeSignatureStatus: "test_signed" as const,
  signerSubject: "",
  signerThumbprint: "",
};

const artifact = {
  name: "password-detective-1.2.3.msix",
  size: 8_388_608,
  type: "application/msix",
};

function release(overrides: Partial<DesktopRelease> = {}): DesktopRelease {
  return {
    id: "release_synthetic",
    channel: "stable",
    platform: "windows",
    architecture: "x64",
    version: "1.2.3",
    minimum_supported_version: "1.0.0",
    status: "draft",
    mandatory: false,
    release_notes: "合成发布说明",
    artifact_filename: artifact.name,
    artifact_sha256: "a".repeat(64),
    artifact_size_bytes: artifact.size,
    content_type: artifact.type,
    artifact_uploaded: false,
    code_signature_status: "test_signed",
    signer_subject: null,
    signer_thumbprint: null,
    download_count: 0,
    created_at: "2026-08-02T00:00:00Z",
    updated_at: "2026-08-02T00:00:00Z",
    published_at: null,
    withdrawn_at: null,
    ...overrides,
  };
}

describe("desktop release administration", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("normalizes a release draft into the backend contract", () => {
    const payload = buildDesktopReleasePayload(
      { ...baseInput, version: " 1.2.3 ", minimumSupportedVersion: " 1.0.0 " },
      artifact,
    );

    expect(payload).toMatchObject({
      platform: "windows",
      version: "1.2.3",
      minimum_supported_version: "1.0.0",
      artifact_filename: artifact.name,
      artifact_size_bytes: artifact.size,
      artifact_sha256: "a".repeat(64),
      signer_subject: null,
      signer_thumbprint: null,
    });
  });

  it("rejects unsafe or inconsistent release metadata", () => {
    expect(() =>
      buildDesktopReleasePayload(
        { ...baseInput, minimumSupportedVersion: "2.0.0" },
        artifact,
      ),
    ).toThrow("最低受支持版本不能高于发布版本");
    expect(() =>
      buildDesktopReleasePayload({ ...baseInput, artifactSha256: "not-a-digest" }, artifact),
    ).toThrow("SHA-256");
    expect(() =>
      buildDesktopReleasePayload(
        { ...baseInput, codeSignatureStatus: "verified" },
        artifact,
      ),
    ).toThrow("已验证签名");
    expect(() =>
      buildDesktopReleasePayload(baseInput, { ...artifact, name: "archive.zip" }),
    ).toThrow(".msix");
    expect(() =>
      buildDesktopReleasePayload(baseInput, { ...artifact, name: "nested/setup.msix" }),
    ).toThrow("无路径");
  });

  it("checks retry files against immutable draft metadata", () => {
    expect(() => validateArtifactForRelease(release(), artifact)).not.toThrow();
    expect(() =>
      validateArtifactForRelease(release(), { ...artifact, name: "other.msix" }),
    ).toThrow("文件名");
    expect(() =>
      validateArtifactForRelease(release(), { ...artifact, size: artifact.size + 1 }),
    ).toThrow("文件大小");
    expect(formatArtifactSize(artifact.size)).toBe("8.0 MiB");
  });

  it("uploads the artifact as an octet stream with MFA access token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(release({ artifact_uploaded: true })), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });
    const file = new File(["synthetic artifact"], artifact.name, { type: artifact.type });

    await uploadDesktopReleaseArtifact("release/synthetic", file, "mfa-access-token");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(url).toContain("/admin/desktop-releases/release%2Fsynthetic/artifact");
    expect(init.method).toBe("PUT");
    expect(init.body).toBe(file);
    expect(headers.get("Content-Type")).toBe("application/octet-stream");
    expect(headers.get("Authorization")).toBe("Bearer mfa-access-token");
  });
});
