import { ApiError, type ApiErrorBody } from "@password-detective/api-contract";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  accessToken?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Request-ID", `web_${crypto.randomUUID()}`);
  if (options.body) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const response = await fetch(`${baseUrl}${path}`, { credentials: "include", ...options, headers });
  if (!response.ok) {
    const fallback: ApiErrorBody = {
      code: "network.unexpected_response",
      message: "服务暂时不可用，请稍后重试",
      details: {},
      request_id: response.headers.get("X-Request-ID"),
    };
    let body = fallback;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // 保持不含内部响应正文的安全错误。
    }
    throw new ApiError(response.status, body);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
export async function apiFileRequest(
  path: string,
  options: RequestInit = {},
  accessToken?: string,
): Promise<{ blob: Blob; filename: string }> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  headers.set("Content-Type", "application/json");
  headers.set("X-Request-ID", `web_${crypto.randomUUID()}`);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${baseUrl}${path}`, { credentials: "include", ...options, headers });
  if (!response.ok) {
    let message = "文件下载失败，请稍后重试";
    try {
      const body = (await response.json()) as ApiErrorBody;
      message = body.message;
    } catch {
      // 下载失败时不暴露非结构化响应正文。
    }
    throw new Error(message);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? "privacy-export.json";
  return { blob: await response.blob(), filename };
}
