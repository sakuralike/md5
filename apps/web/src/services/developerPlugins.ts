import type { DesktopPluginCapability, DesktopPluginProjectDetail, DesktopPluginVersion } from "@password-detective/api-contract";
import { apiRequest } from "./api";

function key(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

export interface SigningKeyRecord {
  id: string;
  key_id: string;
  fingerprint: string;
  status: string;
}

export async function listDeveloperPlugins(token: string): Promise<DesktopPluginProjectDetail[]> {
  const response = await apiRequest<{ items: DesktopPluginProjectDetail[] }>("/developer/plugins?page=1&page_size=100", {}, token);
  return response.items;
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
  payload: { key_id: string; public_key_base64: string; reauth_token: string },
): Promise<SigningKeyRecord> {
  return apiRequest(
    "/developer/plugins/signing-keys",
    { method: "POST", headers: { "Idempotency-Key": key("plugin-key") }, body: JSON.stringify(payload) },
    token,
  );
}

export function createPluginVersion(
  token: string,
  pluginId: string,
  payload: { semver: string; signing_key_id: string; requested_capabilities: DesktopPluginCapability[] },
) {
  return apiRequest<DesktopPluginVersion>(
    `/developer/plugins/${encodeURIComponent(pluginId)}/versions`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key("plugin-version") },
      body: JSON.stringify({ ...payload, release_notes: "开发者中心上传", source_review_mode: "binary_only" }),
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
