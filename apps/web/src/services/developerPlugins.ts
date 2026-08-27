import type { DesktopPluginCapability, DesktopPluginProject, DesktopPluginProjectDetail, DesktopPluginStaticReviewReport, DesktopPluginVersion } from "@password-detective/api-contract";
import { apiRequest } from "./api";

function key(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

export interface SigningKeyRecord {
  id: string;
  key_id: string;
  public_key_base64: string;
  fingerprint: string;
  status: string;
  private_key_base64: string | null;
}

export async function listDeveloperPlugins(token: string): Promise<DesktopPluginProjectDetail[]> {
  const response = await apiRequest<{ items: DesktopPluginProject[] }>("/developer/plugins?page=1&page_size=100", {}, token);
  return Promise.all(response.items.map((item) => apiRequest<DesktopPluginProjectDetail>(
    `/developer/plugins/${encodeURIComponent(item.id)}`, {}, token,
  )));
}

export function getPluginReviewReport(token: string, versionId: string): Promise<DesktopPluginStaticReviewReport> {
  return apiRequest(
    `/developer/plugin-versions/${encodeURIComponent(versionId)}/review-report`,
    {},
    token,
  );
}

export function createDeveloperPlugin(token: string, payload: Record<string, unknown>) {
  return apiRequest<DesktopPluginProjectDetail>(
    "/developer/plugins",
    { method: "POST", headers: { "Idempotency-Key": key("plugin-project") }, body: JSON.stringify(payload) },
    token,
  );
}

export async function registerPluginSigningKey(
  token: string,
  payload: { key_id?: string; public_key_base64?: string; reauth_token: string },
): Promise<SigningKeyRecord> {
  return apiRequest(
    "/developer/plugins/signing-keys",
    { method: "POST", headers: { "Idempotency-Key": key("plugin-key") }, body: JSON.stringify(payload) },
    token,
  );
}

export async function listPluginSigningKeys(token: string): Promise<SigningKeyRecord[]> {
  const response = await apiRequest<{ items: SigningKeyRecord[] }>(
    "/developer/plugins/signing-keys",
    {},
    token,
  );
  return response.items;
}

export function createPluginVersion(
  token: string,
  pluginId: string,
  payload: {
    semver: string;
    signing_key_id: string;
    requested_capabilities: DesktopPluginCapability[];
    release_notes: string;
  },
) {
  return apiRequest<DesktopPluginVersion>(
    `/developer/plugins/${encodeURIComponent(pluginId)}/versions`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key("plugin-version") },
      body: JSON.stringify({ ...payload, source_review_mode: "source" }),
    },
    token,
  );
}

export async function uploadPluginPackage(token: string, versionId: string, file: File) {
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer())))
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
  const session = await apiRequest<{ upload_url: string }>(
    `/developer/plugin-versions/${encodeURIComponent(versionId)}/upload-session`,
    { method: "POST", body: JSON.stringify({ architecture: "windows-x64", artifact_filename: "plugin.pdpkg", size_bytes: file.size, sha256: digest }) },
    token,
  );
  const uploaded = await fetch(session.upload_url, { method: "PUT", body: file });
  if (!uploaded.ok) throw new Error("插件包上传失败");
}

export function finalizePluginVersion(token: string, version: DesktopPluginVersion) {
  return apiRequest<DesktopPluginVersion>(
    `/developer/plugin-versions/${encodeURIComponent(version.id)}/finalize`,
    { method: "POST", headers: { "Idempotency-Key": key("plugin-finalize") }, body: JSON.stringify({ version: version.version }) },
    token,
  );
}

export function submitPluginVersion(token: string, version: DesktopPluginVersion) {
  return apiRequest<DesktopPluginVersion>(
    `/developer/plugin-versions/${encodeURIComponent(version.id)}/submit`,
    { method: "POST", headers: { "Idempotency-Key": key("plugin-submit") }, body: JSON.stringify({ version: version.version }) },
    token,
  );
}

export function withdrawPluginVersion(token: string, version: DesktopPluginVersion) {
  return apiRequest<DesktopPluginVersion>(
    `/developer/plugin-versions/${encodeURIComponent(version.id)}/withdraw`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key("plugin-withdraw") },
      body: JSON.stringify({ version: version.version }),
    },
    token,
  );
}
